"""EMAIL_MODE: which email backend each combination of environment variables selects (no network, no database)."""
from pathlib import Path

from django.test import SimpleTestCase

from config.email_config import BACKENDS, EmailConfigError, email_settings

BASE = Path("/app")
MAILTRAP = {"SMTP_HOST": "sandbox.smtp.mailtrap.io", "SMTP_PORT": "2525", "SMTP_USER": "u", "SMTP_PASSWORD": "p"}


class EmailModeTests(SimpleTestCase):
    def test_explicit_file_mode_ignores_smtp_credentials_left_in_env(self):
        s = email_settings({"EMAIL_MODE": "file", **MAILTRAP}, BASE)
        self.assertEqual(s["EMAIL_BACKEND"], BACKENDS["file"])
        self.assertEqual(s["EMAIL_FILE_PATH"], BASE / "sent_emails")
        self.assertNotIn("EMAIL_HOST", s)

    def test_explicit_smtp_mode(self):
        s = email_settings({"EMAIL_MODE": "SMTP", **MAILTRAP, "MAIL_FROM": "App <no-reply@x.test>"}, BASE)
        self.assertEqual(s["EMAIL_BACKEND"], BACKENDS["smtp"])
        self.assertEqual((s["EMAIL_HOST"], s["EMAIL_PORT"], s["EMAIL_HOST_USER"]), ("sandbox.smtp.mailtrap.io", 2525, "u"))
        self.assertEqual((s["EMAIL_USE_TLS"], s["EMAIL_USE_SSL"]), (True, False))
        self.assertEqual(s["DEFAULT_FROM_EMAIL"], "App <no-reply@x.test>")
        self.assertEqual(s["EMAIL_FILE_PATH"], BASE / "sent_emails")  # fallback folder stays known

    def test_security_options(self):
        ssl = email_settings({"EMAIL_MODE": "smtp", **MAILTRAP, "SMTP_SECURITY": "ssl"}, BASE)
        none = email_settings({"EMAIL_MODE": "smtp", **MAILTRAP, "SMTP_SECURITY": "none"}, BASE)
        self.assertEqual((ssl["EMAIL_USE_TLS"], ssl["EMAIL_USE_SSL"]), (False, True))
        self.assertEqual((none["EMAIL_USE_TLS"], none["EMAIL_USE_SSL"]), (False, False))

    def test_without_email_mode_the_previous_rule_still_applies(self):
        self.assertEqual(email_settings({**MAILTRAP}, BASE)["EMAIL_MODE"], "smtp")
        self.assertEqual(email_settings({"MAIL_FILE_DIR": "out"}, BASE)["EMAIL_FILE_PATH"], BASE / "out")
        self.assertEqual(email_settings({"MAIL_FILE_DIR": "out"}, BASE)["EMAIL_MODE"], "file")
        self.assertEqual(email_settings({}, BASE)["EMAIL_MODE"], "console")

    def test_bad_combinations_fail_at_startup_with_a_clear_message(self):
        cases = [
            ({"EMAIL_MODE": "smpt"}, "EMAIL_MODE must be one of"),
            ({"EMAIL_MODE": "smtp"}, "needs SMTP_HOST"),
            ({"EMAIL_MODE": "smtp", **MAILTRAP, "SMTP_SECURITY": "tls"}, "SMTP_SECURITY"),
            ({"EMAIL_MODE": "smtp", **MAILTRAP, "SMTP_PORT": "abc"}, "SMTP_PORT"),
        ]
        for environ, message in cases:
            with self.assertRaisesMessage(EmailConfigError, message):
                email_settings(environ, BASE)

    def test_error_messages_never_contain_the_password(self):
        with self.assertRaises(EmailConfigError) as ctx:
            email_settings({"EMAIL_MODE": "smtp", **MAILTRAP, "SMTP_PASSWORD": "s3cret", "SMTP_PORT": "x"}, BASE)
        self.assertNotIn("s3cret", str(ctx.exception))
