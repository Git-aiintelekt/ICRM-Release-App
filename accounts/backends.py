from django.contrib.auth.backends import ModelBackend

from .models import AppUser


class EmailOrUsernameBackend(ModelBackend):
    """Sign in with email; accounts without one (e.g. "releasemanager") use their username."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        identifier = (username or kwargs.get("email") or "").strip().lower()
        if not identifier or password is None:
            return None
        user = AppUser.objects.filter(email=identifier).first() or AppUser.objects.filter(username=identifier).first()
        if user is None:
            AppUser().set_password(password)  # same work as a real check, so timing doesn't reveal accounts
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    def get_user(self, user_id):
        user = AppUser.objects.filter(pk=user_id).first()
        return user if user and self.user_can_authenticate(user) else None
