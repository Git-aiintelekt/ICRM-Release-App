"""WSGI entry point. Production: .venv\Scripts\waitress-serve --port=8000 config.wsgi:application"""
import os
from pathlib import Path

from dotenv import load_dotenv
from django.core.wsgi import get_wsgi_application

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.prod")

application = get_wsgi_application()
