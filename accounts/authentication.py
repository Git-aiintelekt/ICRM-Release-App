from rest_framework import authentication

from .models import AppUser
from .tokens import read_token


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
        return (user, token)

    def authenticate_header(self, request):
        return "Bearer"
