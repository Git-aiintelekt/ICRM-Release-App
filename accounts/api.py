"""/api/auth/* (sign in, sign up, password reset) and /api/admin/users (who is admin / may see Jira)."""
import logging
import threading

from django.conf import settings
from django.contrib.auth import login as django_login
from django.contrib.auth import logout as django_logout
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Count, Max
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response

from audit import models as audit
from audit.models import AuditLog
from audit.service import record
from config.api import (IsAdmin, IsSignedIn, LoginThrottle, PasswordResetThrottle, RegisterThrottle, bad_request,
                        not_found)
from config.mail import delivery_mode

from .backends import EmailOrUsernameBackend
from .models import ADMIN_GROUP_ID, JIRA_VIEWER_GROUP_ID, AppUser, AppUserSecurityGroup
from .tokens import create_reset_token, create_token, read_reset_token, revoke_all_tokens, revoke_token

log = logging.getLogger(__name__)

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


def user_json(user: AppUser) -> dict:
    groups = user.active_groups()
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "displayName": user.display_name,
        "isAdmin": ADMIN_GROUP_ID in groups,
        "canViewJira": bool(groups & {ADMIN_GROUP_ID, JIRA_VIEWER_GROUP_ID}),
    }


def _start_session(request, user: AppUser) -> dict:
    # The Django session lets the same person open Django Admin without signing in again.
    django_login(request._request, user, backend="accounts.backends.EmailOrUsernameBackend")
    return {"token": create_token(user.id), "user": user_json(user)}


class CredentialsSerializer(serializers.Serializer):
    # Email for normal accounts; older accounts without an email (e.g. "admin") use their username.
    email = serializers.CharField(min_length=1, max_length=191, trim_whitespace=False)
    password = serializers.CharField(min_length=1, max_length=200, trim_whitespace=False)


class RegisterSerializer(serializers.Serializer):
    email = serializers.RegexField(EMAIL_PATTERN, max_length=191)
    password = serializers.CharField(min_length=8, max_length=200, trim_whitespace=False)
    display_name = serializers.CharField(max_length=150, required=False, allow_null=True, allow_blank=True)


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.CharField(min_length=1, max_length=191)


class ResetPasswordSerializer(serializers.Serializer):
    token = serializers.CharField(min_length=1, max_length=1000)
    password = serializers.CharField(min_length=8, max_length=200, trim_whitespace=False)


def _valid(serializer_class, request):
    serializer = serializer_class(data=request.data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def _registration_domains_text() -> str:
    return ", ".join(f"@{d}" for d in settings.REGISTRATION_EMAIL_DOMAINS)


@api_view(["GET"])
def auth_options(request):
    """What the sign-in page offers: whether self sign-up is open, and for which email domains."""
    return Response({"registrationOpen": settings.ALLOW_REGISTRATION,
                     "registrationDomains": settings.REGISTRATION_EMAIL_DOMAINS})


@api_view(["POST"])
@throttle_classes([RegisterThrottle])
def register(request):
    if not settings.ALLOW_REGISTRATION:
        return Response({"detail": "Sign-up is closed. Ask an administrator for an account."},
                        status=status.HTTP_403_FORBIDDEN)
    body = _valid(RegisterSerializer, request)
    email = body["email"].strip().lower()
    domains = settings.REGISTRATION_EMAIL_DOMAINS
    if domains and email.rpartition("@")[2] not in domains:
        raise bad_request(f"Sign-up is limited to {_registration_domains_text()} email addresses.")
    if AppUser.objects.filter(email=email).exists() or AppUser.objects.filter(username=email).exists():
        return Response({"detail": "An account with that email already exists."}, status=status.HTTP_409_CONFLICT)
    # New accounts use their email as the username and get no admin or Jira access; an admin grants it.
    with transaction.atomic():
        user = AppUser.objects.create_user(email, body["password"], email=email,
                                           display_name=(body.get("display_name") or "").strip() or None)
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        record(request, audit.REGISTER, user)
    return Response(_start_session(request, user), status=status.HTTP_201_CREATED)


def _failures_key(identifier: str) -> str:
    return f"login-failures:{identifier}"


def _find_user(identifier: str) -> AppUser | None:
    return AppUser.objects.filter(email=identifier).first() or AppUser.objects.filter(username=identifier).first()


@api_view(["POST"])
@throttle_classes([LoginThrottle])
def login(request):
    body = _valid(CredentialsSerializer, request)
    identifier = body["email"].strip().lower()
    failures_key = _failures_key(identifier)
    if cache.get(failures_key, 0) >= settings.LOGIN_LOCKOUT_ATTEMPTS:
        record(request, audit.LOGIN_FAILED, _find_user(identifier), username=identifier,
               details="locked: too many failed sign-ins")
        minutes = max(1, settings.LOGIN_LOCKOUT_SECONDS // 60)
        return Response({"detail": f"Too many failed sign-ins. Try again in {minutes} minutes, or reset your password."},
                        status=status.HTTP_429_TOO_MANY_REQUESTS)
    user = EmailOrUsernameBackend().authenticate(request._request, username=identifier, password=body["password"])
    if user is None:
        # The window starts at the first failure; later failures don't extend it.
        if not cache.add(failures_key, 1, settings.LOGIN_LOCKOUT_SECONDS):
            try:
                cache.incr(failures_key)
            except ValueError:  # expired between add() and incr()
                cache.add(failures_key, 1, settings.LOGIN_LOCKOUT_SECONDS)
        found = _find_user(identifier)
        reason = "unknown user" if found is None else "account disabled" if not found.is_active else "wrong password"
        record(request, audit.LOGIN_FAILED, found, username=identifier, details=reason)
        return Response({"detail": "Incorrect email or password."}, status=status.HTTP_401_UNAUTHORIZED)
    cache.delete(failures_key)
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    record(request, audit.LOGIN, user)
    return Response(_start_session(request, user))


@api_view(["POST"])
def logout(request):
    """Signs out this device: its token stops working at once, not only when it expires."""
    if isinstance(request.auth, str):
        revoke_token(request.auth)
    django_logout(request._request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsSignedIn])
def logout_everywhere(request):
    """Ends every sign-in of this user, on every device (e.g. after a lost laptop)."""
    revoke_all_tokens(request.user.id)
    record(request, audit.LOGOUT_EVERYWHERE, request.user)
    django_logout(request._request)
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["GET"])
@permission_classes([IsSignedIn])
def me(request):
    return Response(user_json(request.user))


def _send_reset_mail(address: str, text: str) -> None:
    """Runs in a background thread: a failure can't reach the user, so it goes to the server log."""
    try:
        send_mail("Reset your iCRM Releases password", text, None, [address], fail_silently=False)
        log.info("Password reset email handed to the %s mail backend.", delivery_mode())
    except Exception as exc:  # noqa: BLE001 - any failure here would otherwise vanish with the thread
        log.error("Password reset email could not be sent: %s: %s", type(exc).__name__, exc)


@api_view(["POST"])
@throttle_classes([PasswordResetThrottle])
def forgot_password(request):
    email = _valid(ForgotPasswordSerializer, request)["email"].strip().lower()
    user = AppUser.objects.filter(email=email).first()
    if user is not None and user.is_active:
        link = f"{settings.APP_BASE_URL}/reset-password?token={create_reset_token(user)}"
        minutes = settings.PASSWORD_RESET_TTL_SECONDS // 60
        text = (
            f"Hello {user.display_name or user.email},\n\n"
            "Someone asked to reset the password for your iCRM Releases account.\n"
            f"Choose a new password here (the link works once, for {minutes} minutes):\n\n"
            f"{link}\n\n"
            "If you didn't ask for this, ignore this email; your password stays the same.\n"
        )
        # In the background, so a slow mail server doesn't delay the reply or reveal that the account exists.
        threading.Thread(target=_send_reset_mail, daemon=True, args=(user.email, text)).start()
    record(request, audit.PASSWORD_RESET_REQUEST, user, username=email,
           details=None if user is not None and user.is_active else "no enabled account with that email")
    # Same answer whether or not the account exists, so this can't be used to find out who has one.
    return Response({"message": "If an account uses that email, we've sent it a link to reset the password."},
                    status=status.HTTP_202_ACCEPTED)


@api_view(["POST"])
@throttle_classes([PasswordResetThrottle])
def reset_password(request):
    body = _valid(ResetPasswordSerializer, request)
    user = read_reset_token(body["token"])
    if user is None:
        raise bad_request("This reset link is invalid, expired or already used. Ask for a new one.")
    user.set_password(body["password"])  # the save ends every earlier sign-in (AppUser.save)
    user.last_login = timezone.now()
    user.save(update_fields=["password", "last_login"])
    for identifier in {user.email, user.username} - {None}:
        cache.delete(_failures_key(identifier))
    record(request, audit.PASSWORD_RESET, user)
    return Response(_start_session(request, user))


# ---- Admin: users and access ----

def _jira_view_stats() -> dict[int, tuple[int, object]]:
    rows = (
        AuditLog.objects.filter(action=audit.JIRA_ISSUE_VIEW, user_id__isnull=False)
        .values("user_id").annotate(n=Count("id"), last=Max("created_at"))
    )
    return {row["user_id"]: (row["n"], row["last"]) for row in rows}


def _iso(value):
    return value.isoformat() if value else None


def admin_user_json(user: AppUser, stats: dict) -> dict:
    groups = user.active_groups()
    count, last = stats.get(user.id, (0, None))
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "displayName": user.display_name,
        "isEnabled": user.is_active,
        "isAdmin": ADMIN_GROUP_ID in groups,
        "canViewJira": bool(groups & {ADMIN_GROUP_ID, JIRA_VIEWER_GROUP_ID}),
        "createdAt": _iso(user.created_at),
        "lastLoginAt": _iso(user.last_login),
        "jiraViewCount": count,
        "lastJiraViewAt": _iso(last),
    }


def _other_active_admins(user_id: int) -> int:
    now = timezone.now()
    return (
        AppUserSecurityGroup.objects.filter(group_id=ADMIN_GROUP_ID, from_date__lte=now, user__is_active=True)
        .exclude(thru_date__lte=now).exclude(user_id=user_id).values("user_id").distinct().count()
    )


class UpdateUserAccessSerializer(serializers.Serializer):
    is_admin = serializers.BooleanField(required=False, allow_null=True)
    can_view_jira = serializers.BooleanField(required=False, allow_null=True)
    is_enabled = serializers.BooleanField(required=False, allow_null=True)


@api_view(["GET"])
@permission_classes([IsAdmin])
def list_users(request):
    stats = _jira_view_stats()
    return Response([admin_user_json(u, stats) for u in AppUser.objects.order_by("username")])


@api_view(["PATCH"])
@permission_classes([IsAdmin])
def update_user(request, user_id):
    body = _valid(UpdateUserAccessSerializer, request)
    user = AppUser.objects.filter(pk=user_id).first()
    if user is None:
        raise not_found("User not found.")
    is_admin, can_view_jira, is_enabled = body.get("is_admin"), body.get("can_view_jira"), body.get("is_enabled")
    removing_admin = is_admin is False or is_enabled is False
    if removing_admin and user.is_admin and _other_active_admins(user.id) == 0:
        raise bad_request("At least one enabled admin must remain.")
    if user.id == request.user.id and removing_admin:
        raise bad_request("You can't remove your own admin access or disable yourself.")

    changes = []
    with transaction.atomic():
        if is_admin is not None and user.set_group(ADMIN_GROUP_ID, is_admin):
            changes.append(f"{'granted' if is_admin else 'revoked'} admin")
        if can_view_jira is not None and user.set_group(JIRA_VIEWER_GROUP_ID, can_view_jira):
            changes.append(f"{'granted' if can_view_jira else 'revoked'} Jira access")
        if is_enabled is not None and is_enabled != user.is_active:
            user.is_active = is_enabled
            user.save(update_fields=["is_active"])
            if not is_enabled:
                revoke_all_tokens(user.id)  # stays signed out if the account is enabled again
            changes.append("enabled account" if is_enabled else "disabled account")
        if changes:
            record(request, audit.ACCESS_CHANGE, request.user, target=user.username, details=", ".join(changes))
    return Response(admin_user_json(user, _jira_view_stats()))
