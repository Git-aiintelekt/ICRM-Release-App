"""Send one test email with the mail settings in .env, and say where it went.

    .venv\\Scripts\\python manage.py send_test_email you@example.com

EMAIL_MODE=smtp sends through SMTP_* (errors are shown, the password never is); file saves an .eml file in
MAIL_FILE_DIR; console prints it here.
"""
from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from config.mail import delivery_mode


class Command(BaseCommand):
    help = "Send a test email using the configured mail settings."

    def add_arguments(self, parser):
        parser.add_argument("to", help="Recipient address.")

    def handle(self, *args, to, **options):
        try:
            validate_email(to)
        except ValidationError:
            raise CommandError(f"Not an email address: {to}")
        mode = delivery_mode()
        self.stdout.write(f"Delivery: {mode}; from: {settings.DEFAULT_FROM_EMAIL}")
        if mode == "smtp":
            self.stdout.write(f"SMTP: {settings.EMAIL_HOST}:{settings.EMAIL_PORT} "
                              f"({'STARTTLS' if settings.EMAIL_USE_TLS else 'SSL' if settings.EMAIL_USE_SSL else 'no TLS'}), "
                              f"user {settings.EMAIL_HOST_USER or '-'}, password {'set' if settings.EMAIL_HOST_PASSWORD else 'not set'}")
        try:
            send_mail("iCRM Releases test email", "This is a test email from iCRM Releases. Mail settings work.",
                      None, [to], fail_silently=False)
        except Exception as exc:  # noqa: BLE001 - report any failure plainly
            raise CommandError(f"Sending failed: {type(exc).__name__}: {exc}")
        where = {"smtp": "handed to the SMTP server", "file": f"saved as an .eml file in {settings.EMAIL_FILE_PATH}",
                 "console": "printed above (console backend: nothing was delivered)"}[mode]
        self.stdout.write(self.style.SUCCESS(f"Test email {where}."))
