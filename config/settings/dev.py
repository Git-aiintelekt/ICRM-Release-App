"""Local development: DEBUG on, localhost only. Email follows EMAIL_MODE in .env (base.py)."""
from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, env_list

DEBUG = True
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1")
# The Vite dev server (npm run dev) proxies /api and /admin here.
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "http://localhost:5173")
SECRET_KEY = SECRET_KEY or "dev-only-insecure-key"
