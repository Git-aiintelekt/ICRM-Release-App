"""Settings shared by every environment. dev.py and prod.py import this and adjust it.

All secrets and per-server values come from the environment (.env locally); see .env.example.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"


def env(name, default=None):
    return os.environ.get(name, default)


def env_list(name, default=""):
    return [value.strip() for value in env(name, default).split(",") if value.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "accounts",
    "audit",
    "releases",
    "jira",
    "frontend_app",
    "integrations",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---- Content Security Policy: only this site's own scripts, styles, images and API ----
# Report-only by default: browsers log what the policy would block (developer tools console) but block nothing.
# Once the React app and Django Admin show no reports, set CSP_ENFORCE=true to enforce it.
from django.utils.csp import CSP  # noqa: E402

_CSP_POLICY = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE],  # React style={{…}} attributes
    "img-src": [CSP.SELF, "data:", "blob:"],
    "font-src": [CSP.SELF, "data:"],
    "connect-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "form-action": [CSP.SELF],
}
if env("CSP_ENFORCE", "false").lower() == "true":
    SECURE_CSP = _CSP_POLICY
else:
    SECURE_CSP_REPORT_ONLY = _CSP_POLICY

# ---- Database: the existing react_database, on MySQL 5.5 (see config/db_backends/mysql55) ----

DATABASES = {
    "default": {
        "ENGINE": "config.db_backends.mysql55",
        "NAME": env("DB_NAME", "react_database"),
        "USER": env("DB_USER", "root"),
        "PASSWORD": env("DB_PASSWORD", ""),
        "HOST": env("DB_HOST", "localhost"),
        "PORT": env("DB_PORT", "3306"),
        # The tables are utf8 (3-byte); utf8mb4 would not fit 5.5's index length limit.
        "OPTIONS": {"charset": "utf8"},
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# ---- Users: the existing app_user table ----

AUTH_USER_MODEL = "accounts.AppUser"
AUTHENTICATION_BACKENDS = ["accounts.backends.EmailOrUsernameBackend"]
# Same PBKDF2 format as python-backend, so existing passwords keep working in both.
PASSWORD_HASHERS = ["accounts.hashers.LegacyPBKDF2Hasher"]
LOGIN_URL = "admin:login"

APP_SECRET_KEY = env("APP_SECRET_KEY") or SECRET_KEY
TOKEN_TTL_SECONDS = int(env("TOKEN_TTL_SECONDS", str(8 * 60 * 60)))
PASSWORD_RESET_TTL_SECONDS = int(env("PASSWORD_RESET_TTL_SECONDS", str(30 * 60)))
APP_BASE_URL = env("APP_BASE_URL", "http://localhost:8000").rstrip("/")

# ---- API ----

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["accounts.authentication.BearerTokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_PARSER_CLASSES": [
        "config.api.CamelCaseJSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "config.api.exception_handler",
    "UNAUTHENTICATED_USER": None,
    # Per client IP, on the sign-in and public release notes endpoints only (config/api.py). Counted in the default cache.
    "DEFAULT_THROTTLE_RATES": {
        "login": env("THROTTLE_LOGIN", "10/min"),
        "register": env("THROTTLE_REGISTER", "5/hour"),
        "password_reset": env("THROTTLE_PASSWORD_RESET", "5/hour"),
        "public_read": env("THROTTLE_PUBLIC", "60/min"),
    },
    # 0 = use the connection's address and ignore X-Forwarded-For (which a client can fake). Behind one
    # proxy (IIS / nginx) set NUM_PROXIES=1 so the real client address is used.
    "NUM_PROXIES": int(env("NUM_PROXIES", "0")),
}
# Failed sign-ins per account: after LOGIN_LOCKOUT_ATTEMPTS failures within LOGIN_LOCKOUT_SECONDS,
# that account's sign-in is refused until the window passes (whatever the IP).
LOGIN_LOCKOUT_ATTEMPTS = int(env("LOGIN_LOCKOUT_ATTEMPTS", "5"))
LOGIN_LOCKOUT_SECONDS = int(env("LOGIN_LOCKOUT_SECONDS", str(15 * 60)))
# Self sign-up: off with ALLOW_REGISTRATION=false. REGISTRATION_EMAIL_DOMAINS limits it to these email
# domains (comma-separated); set it empty to allow any domain. Existing accounts are not affected.
ALLOW_REGISTRATION = env("ALLOW_REGISTRATION", "true").lower() == "true"
REGISTRATION_EMAIL_DOMAINS = [d.lower().lstrip("@") for d in env_list("REGISTRATION_EMAIL_DOMAINS", "aiintelekt.com")]
# The public release notes page (/public/release-notes and /api/public/...): off unless PUBLIC_RELEASE_NOTES=true.
PUBLIC_RELEASE_NOTES = env("PUBLIC_RELEASE_NOTES", "false").lower() == "true"
# The .docx upload carries screenshots as data: URLs inside JSON.
DATA_UPLOAD_MAX_MEMORY_SIZE = 60 * 1024 * 1024

# ---- Files ----

UPLOAD_DIR = Path(env("UPLOAD_DIR", BASE_DIR / "media"))
IMAGE_DIR = UPLOAD_DIR / "release-images"

# Django Admin (/admin/) is switched off unless ENABLE_DJANGO_ADMIN=true.
# The React app's own /api/admin/... endpoints are not affected.
ENABLE_DJANGO_ADMIN = env("ENABLE_DJANGO_ADMIN", "false").lower() == "true"

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# The React build (npm run build in frontend/) is served from the site root.
WHITENOISE_ROOT = FRONTEND_DIR / "dist"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# ---- Email (password reset, release notes): EMAIL_MODE = file | smtp | console, see config/email_config.py. ----
# Each server's own .env decides; production's is owned by the infrastructure team (README: "Email").

from django.core.exceptions import ImproperlyConfigured  # noqa: E402

from config.email_config import EmailConfigError, email_settings  # noqa: E402

try:
    globals().update(email_settings(os.environ, BASE_DIR))  # EMAIL_MODE, EMAIL_BACKEND, EMAIL_HOST, ...
except EmailConfigError as exc:
    raise ImproperlyConfigured(str(exc)) from None

# ---- Live Jira Cloud and Bitbucket Cloud (integrations/). Credentials stay on the server: ----
# ---- no endpoint returns them, and an integration with missing values reports "not configured". ----

JIRA_BASE_URL = env("JIRA_BASE_URL", "").rstrip("/")
# A token made with "Create API token with scopes" is only accepted through the Atlassian API gateway
# (https://api.atlassian.com/ex/jira/<cloud id>); on the site URL Jira treats it as anonymous. The cloud ID is at
# https://<site>.atlassian.net/_edge/tenant_info. Leave it empty for a classic (unscoped) API token.
JIRA_CLOUD_ID = env("JIRA_CLOUD_ID", "").strip()
JIRA_EMAIL = env("JIRA_EMAIL", "")
JIRA_API_TOKEN = env("JIRA_API_TOKEN", "")
JIRA_PROJECT_KEYS = [key.upper() for key in env_list("JIRA_PROJECT_KEYS", "CS,IBP,CT,CP")]
JIRA_BUG_ISSUE_TYPES = env_list("JIRA_BUG_ISSUE_TYPES", "Bug")
# Both are in Jira's "Done" status category; they are counted separately because the workflows differ.
JIRA_RESOLVED_STATUSES = env_list("JIRA_RESOLVED_STATUSES", "Resolved")
JIRA_CLOSED_STATUSES = env_list("JIRA_CLOSED_STATUSES", "Closed,Done")
# Optional "app version=Jira fix version|another fix version;..." pairs for release-wise summaries.
# Without it, summaries are listed by the fix version names Jira actually has.
JIRA_FIX_VERSION_MAP = env("JIRA_FIX_VERSION_MAP", "")

BITBUCKET_API_URL = env("BITBUCKET_API_URL", "https://api.bitbucket.org/2.0").rstrip("/")
BITBUCKET_WORKSPACE = env("BITBUCKET_WORKSPACE", "")
BITBUCKET_REPOSITORIES = env_list("BITBUCKET_REPOSITORIES", "icrm-base-framework-master,icrm-b2b-master")
# Either an Atlassian API token with Bitbucket read scopes (BITBUCKET_EMAIL + BITBUCKET_API_TOKEN),
# or a repository/workspace access token (BITBUCKET_ACCESS_TOKEN).
BITBUCKET_EMAIL = env("BITBUCKET_EMAIL", "")
BITBUCKET_API_TOKEN = env("BITBUCKET_API_TOKEN", "")
BITBUCKET_ACCESS_TOKEN = env("BITBUCKET_ACCESS_TOKEN", "")

INTEGRATION_TIMEOUT_SECONDS = int(env("INTEGRATION_TIMEOUT_SECONDS", "15"))
INTEGRATION_CACHE_SECONDS = int(env("INTEGRATION_CACHE_SECONDS", "300"))

# In-process cache for Jira/Bitbucket responses (waitress runs one process, so every thread shares it).
CACHES = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "release-notes"},
}

# ---- Locale: the database stores local times, like python-backend ----

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = False

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
