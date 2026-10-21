"""Staging/production: no DEBUG, secrets required, https cookies. Run with waitress, never runserver."""
from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env

DEBUG = False
if not SECRET_KEY or not env("APP_SECRET_KEY"):
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY and APP_SECRET_KEY in the environment (.env).")

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
# Behind an https proxy (IIS / nginx): trust its X-Forwarded-Proto header.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Set these in .env once the site is served only over https (see README: "Staging / production").
SECURE_SSL_REDIRECT = env("SECURE_SSL_REDIRECT", "false").lower() == "true"
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "0"))
