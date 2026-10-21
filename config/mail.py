"""Local email: every message is saved as its own .eml file (opens in Outlook or Windows Mail, attachments included).

Used with EMAIL_MODE=file, so password resets and release-notes emails can be checked
without a mail server. Nothing leaves the machine.
"""
import uuid
from pathlib import Path

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend
from django.utils import timezone

from .email_config import BACKENDS


def delivery_mode() -> str:
    """"smtp", "file" or "console": told to admins, so a saved-to-file email isn't mistaken for a delivered one."""
    return next((mode for mode, backend in BACKENDS.items() if backend == settings.EMAIL_BACKEND), "console")


class EmlFileBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        folder = Path(settings.EMAIL_FILE_PATH)
        folder.mkdir(parents=True, exist_ok=True)
        sent = 0
        for message in email_messages:
            if not message.recipients():
                continue
            name = f"{timezone.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.eml"
            (folder / name).write_bytes(message.message().as_bytes())
            sent += 1
        return sent
