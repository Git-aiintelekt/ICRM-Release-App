"""Jira / Bitbucket connection settings: entered by an admin on Settings → Integrations, or else taken from .env.

A value saved in the app (table integration_credential) wins over the .env value of the same name; clearing it in
the app falls back to .env again. Values are encrypted with a key derived from APP_SECRET_KEY, and secrets (the
tokens) are never sent back to the browser. If APP_SECRET_KEY changes, saved values can't be read any more: they
are skipped (the .env value is used) until an admin enters them again.
"""
import base64
import hashlib
import logging
import threading
import time

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import IntegrationCredential

log = logging.getLogger(__name__)

# (setting name, label, secret). The order is the order of the form.
FIELDS = [
    ("JIRA_BASE_URL", "Jira site URL", False),
    ("JIRA_EMAIL", "Jira account email", False),
    ("JIRA_API_TOKEN", "Jira API token", True),
    ("BITBUCKET_WORKSPACE", "Bitbucket workspace", False),
    ("BITBUCKET_EMAIL", "Bitbucket account email", False),
    ("BITBUCKET_API_TOKEN", "Bitbucket API token", True),
    ("BITBUCKET_ACCESS_TOKEN", "Bitbucket access token (instead of email + API token)", True),
]
NAMES = [name for name, _, _ in FIELDS]
SECRETS = {name for name, _, secret in FIELDS if secret}

# Saved values are read from the database at most this often per process; a save clears it at once.
RELOAD_SECONDS = 60
_lock = threading.Lock()
_loaded: dict = {"at": 0.0, "values": {}}


def _fernet() -> Fernet:
    secret = settings.APP_SECRET_KEY or settings.SECRET_KEY
    key = hashlib.sha256(f"integration-credentials:{secret}".encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def stored() -> dict[str, str]:
    """The values saved in the app, decrypted."""
    with _lock:
        if time.monotonic() - _loaded["at"] < RELOAD_SECONDS:
            return _loaded["values"]
        values, fernet = {}, _fernet()
        for row in IntegrationCredential.objects.all():
            try:
                values[row.name] = fernet.decrypt(row.encrypted_value.encode()).decode()
            except InvalidToken:
                log.warning("Saved %s can't be decrypted (APP_SECRET_KEY changed?); using .env instead.", row.name)
        _loaded.update(at=time.monotonic(), values=values)
        return values


def forget() -> None:
    with _lock:
        _loaded["at"] = 0.0


def get(name: str) -> str:
    value = stored().get(name) or getattr(settings, name)
    return value.rstrip("/") if name == "JIRA_BASE_URL" else value


def source(name: str) -> str | None:
    """Where the value in use comes from: "app", "env", or None when it isn't set anywhere."""
    if stored().get(name):
        return "app"
    return "env" if getattr(settings, name) else None


def save(changes: dict[str, str | None], user) -> list[str]:
    """Save (a non-empty string) or remove (None or "") app values. Returns the names that changed."""
    fernet, changed = _fernet(), []
    with transaction.atomic():
        for name, value in changes.items():
            if value:
                IntegrationCredential.objects.update_or_create(
                    name=name, defaults={"encrypted_value": fernet.encrypt(value.encode()).decode(),
                                         "updated_by": user, "updated_at": timezone.now()})
                changed.append(name)
            elif IntegrationCredential.objects.filter(name=name).delete()[0]:
                changed.append(name)
    forget()
    return changed
