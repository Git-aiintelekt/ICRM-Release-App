"""Which email backend to use, from environment variables (read by config/settings/base.py).

EMAIL_MODE picks it explicitly:
    file     save each email as an .eml file in MAIL_FILE_DIR (default sent_emails/); nothing leaves the machine
    smtp     send through SMTP_HOST / SMTP_PORT / SMTP_SECURITY / SMTP_USER / SMTP_PASSWORD
    console  print emails in the server console
Without EMAIL_MODE the older rule applies: SMTP_HOST set -> smtp, else MAIL_FILE_DIR set -> file, else console.
So SMTP credentials can stay in .env while EMAIL_MODE=file, and switching is a one-word change.
"""
from pathlib import Path

BACKENDS = {
    "smtp": "django.core.mail.backends.smtp.EmailBackend",
    "file": "config.mail.EmlFileBackend",
    "console": "django.core.mail.backends.console.EmailBackend",
}
SECURITY = ("starttls", "ssl", "none")


class EmailConfigError(ValueError):
    pass


def email_settings(environ, base_dir: Path) -> dict:
    """Django EMAIL_* settings for these environment variables. Raises EmailConfigError on a bad combination."""
    get = lambda name, default="": (environ.get(name) or default).strip()  # noqa: E731
    mode = get("EMAIL_MODE").lower()
    if not mode:
        mode = "smtp" if get("SMTP_HOST") else "file" if get("MAIL_FILE_DIR") else "console"
    if mode not in BACKENDS:
        raise EmailConfigError(f"EMAIL_MODE must be one of {', '.join(BACKENDS)} (got {mode!r}).")

    result = {
        "EMAIL_MODE": mode,
        "EMAIL_BACKEND": BACKENDS[mode],
        "DEFAULT_FROM_EMAIL": get("MAIL_FROM") or get("SMTP_USER") or "no-reply@localhost",
        # Kept for every mode, so switching to file mode needs no other change.
        "EMAIL_FILE_PATH": base_dir / get("MAIL_FILE_DIR", "sent_emails"),  # an absolute path stays absolute
    }
    if mode == "smtp":
        security = get("SMTP_SECURITY", "starttls").lower()
        if not get("SMTP_HOST"):
            raise EmailConfigError("EMAIL_MODE=smtp needs SMTP_HOST.")
        if security not in SECURITY:
            raise EmailConfigError(f"SMTP_SECURITY must be one of {', '.join(SECURITY)} (got {security!r}).")
        port = get("SMTP_PORT", "587")
        if not port.isdigit():
            raise EmailConfigError(f"SMTP_PORT must be a number (got {port!r}).")
        result.update({
            "EMAIL_HOST": get("SMTP_HOST"),
            "EMAIL_PORT": int(port),
            "EMAIL_HOST_USER": get("SMTP_USER"),
            "EMAIL_HOST_PASSWORD": environ.get("SMTP_PASSWORD") or "",  # not stripped: a password may end in a space
            "EMAIL_USE_TLS": security == "starttls",
            "EMAIL_USE_SSL": security == "ssl",
            "EMAIL_TIMEOUT": int(get("SMTP_TIMEOUT", "20")) if get("SMTP_TIMEOUT", "20").isdigit() else 20,
        })
    return result
