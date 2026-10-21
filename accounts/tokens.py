"""Signed tokens in the python-backend format, so sign-ins and reset links work in both apps.

Sign-in token:  base64url({"sub": id, "exp": ts, "iat": ts, "jti": id}) . base64url(HMAC-SHA256(APP_SECRET_KEY))
                python-backend ignores iat/jti. Here a token is refused once signed out (its jti in revoked_token)
                or when issued before the user's cutoff (user_token_cutoff: password change, account disabled).
                A token without iat (issued by python-backend) counts as issued at 0.
Reset token:    same shape, signed with a key derived for password resets (never valid as a sign-in token),
                and carrying a fingerprint of the password hash, so it stops working once the password changes.
"""
import base64
import hashlib
import hmac
import json
import secrets
import time

from django.conf import settings

from .models import AppUser, RevokedToken, UserTokenCutoff


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _session_key() -> bytes:
    return settings.APP_SECRET_KEY.encode()


def _reset_key() -> bytes:
    return hmac.new(_session_key(), b"password-reset", hashlib.sha256).digest()


def _sign(payload: dict, key: bytes) -> str:
    body = _b64(json.dumps(payload).encode())
    return f"{body}.{_b64(hmac.new(key, body.encode(), hashlib.sha256).digest())}"


def _read(token: str, key: bytes) -> dict | None:
    try:
        body, signature = token.split(".")
        expected = _b64(hmac.new(key, body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected):
            return None
        data = json.loads(_unb64(body))
        return data if data["exp"] >= time.time() else None
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def create_token(user_id: int) -> str:
    now = time.time()
    payload = {"sub": user_id, "exp": int(now) + settings.TOKEN_TTL_SECONDS, "iat": now, "jti": secrets.token_hex(16)}
    return _sign(payload, _session_key())


def _cutoff(user_id: int) -> float:
    return UserTokenCutoff.objects.filter(pk=user_id).values_list("not_before", flat=True).first() or 0.0


def _jti_revoked(jti: str) -> bool:
    return RevokedToken.objects.filter(pk=jti).exists()


def read_token(token: str) -> int | None:
    data = _read(token, _session_key())
    try:
        user_id = int(data["sub"]) if data else None
        issued = float(data.get("iat", 0)) if data else 0.0
    except (KeyError, TypeError, ValueError):
        return None
    if user_id is None:
        return None
    jti = data.get("jti")
    if (isinstance(jti, str) and _jti_revoked(jti)) or issued < _cutoff(user_id):
        return None
    return user_id


def revoke_token(token: str) -> bool:
    """Signs out this one token (its device). False if it isn't a valid sign-in token or has no jti."""
    data = _read(token, _session_key())
    jti = data.get("jti") if data else None
    if not isinstance(jti, str):
        return False
    now = time.time()
    RevokedToken.objects.filter(expires_at__lt=now).delete()  # expired tokens are refused anyway
    RevokedToken.objects.update_or_create(pk=jti[:32], defaults={"expires_at": float(data["exp"])})
    return True


def revoke_all_tokens(user_id: int) -> None:
    """Every sign-in token of this user issued until now stops working (all devices)."""
    UserTokenCutoff.objects.update_or_create(pk=user_id, defaults={"not_before": time.time()})


def _fingerprint(user: AppUser) -> str:
    return hashlib.sha256(user.password.encode()).hexdigest()[:16]


def create_reset_token(user: AppUser) -> str:
    exp = int(time.time()) + settings.PASSWORD_RESET_TTL_SECONDS
    return _sign({"sub": user.id, "exp": exp, "pwd": _fingerprint(user)}, _reset_key())


def read_reset_token(token: str) -> AppUser | None:
    data = _read(token, _reset_key())
    if not data:
        return None
    try:
        user = AppUser.objects.filter(pk=int(data["sub"])).first()
    except (KeyError, TypeError, ValueError):
        return None
    if user is None or not user.is_active:
        return None
    if not hmac.compare_digest(str(data.get("pwd", "")), _fingerprint(user)):
        return None
    return user
