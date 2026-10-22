from rest_framework import authentication, exceptions

from .models import AppUser
from .tokens import read_token

# What a user who must change their password may still call.
PASSWORD_CHANGE_PATHS = {"/api/auth/me", "/api/auth/change-password", "/api/auth/logout", "/api/auth/logout-all"}


class BearerTokenAuthentication(authentication.BaseAuthentication):
    """Authorization: Bearer <token>, the sign-in token the React app keeps in localStorage."""

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode(errors="ignore")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None
        user_id = read_token(token.strip())
        user = AppUser.objects.filter(pk=user_id).first() if user_id else None
        if user is None or not user.is_active:
            return None  # treated as signed out; the permission check answers 401
        if request.path not in PASSWORD_CHANGE_PATHS and user.must_change_password:
            raise exceptions.PermissionDenied("Change your password to continue.")
        return (user, token)

    def authenticate_header(self, request):
        return "Bearer"
