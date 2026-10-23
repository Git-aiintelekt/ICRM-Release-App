"""Make a fresh checkout ready to run: create the database if it doesn't exist, create every table, and add a default
admin account when there are no users yet. Safe to run any number of times; `runserver` runs it first (manage.py).

    .venv\\Scripts\\python manage.py setup

The default account is releasemanager / releasemanager. Signing in with it shows only a password change form until a new password is
chosen, and Django Admin stays closed to it until then.
"""
import re

import MySQLdb
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, connection, transaction

from accounts.models import AppUser, PasswordChangeRequired
from releases.services.latest import refresh_latest

DEFAULT_ADMIN_USERNAME = "releasemanager"
DEFAULT_ADMIN_PASSWORD = "releasemanager"
UNKNOWN_DATABASE = 1049
DATABASE_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


class Command(BaseCommand):
    help = "Create the database, its tables and a default admin (releasemanager / releasemanager) where they are missing."
    # The system checks connect to the database, which may not exist yet; migrate runs them afterwards.
    requires_system_checks = []

    def handle(self, *args, **options):
        self.create_database()
        call_command("migrate", interactive=False, verbosity=0)
        self.stdout.write("Tables are up to date.")
        refresh_latest()  # Latest = the highest released version number, also for data saved before that rule
        self.create_default_admin()
        if not (settings.BASE_DIR / "frontend" / "dist" / "index.html").exists():
            self.stdout.write(self.style.WARNING(
                "The React app isn't built yet: run  cd frontend; npm ci; npm run build  before opening the site."))

    def create_database(self):
        db = settings.DATABASES["default"]
        try:
            connection.ensure_connection()
            return
        except OperationalError as exc:
            if not exc.args or exc.args[0] != UNKNOWN_DATABASE:
                raise CommandError(f"Can't connect to MySQL with the DB_* settings in .env: {exc}") from exc
        name = db["NAME"]
        if not DATABASE_NAME_RE.match(name):
            raise CommandError(f"DB_NAME {name!r} may only contain letters, digits and underscores.")
        server = MySQLdb.connect(host=db["HOST"] or "localhost", port=int(db["PORT"] or 3306), user=db["USER"],
                                 password=db["PASSWORD"])
        try:
            server.cursor().execute(f"CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8")
        finally:
            server.close()
        connection.close()
        self.stdout.write(self.style.SUCCESS(f"Created the database {name}."))

    def create_default_admin(self):
        if AppUser.objects.exists():
            return
        with transaction.atomic():
            user = AppUser.objects.create_user(DEFAULT_ADMIN_USERNAME, DEFAULT_ADMIN_PASSWORD, is_admin=True)
            PasswordChangeRequired.objects.create(user=user)
        self.stdout.write(self.style.WARNING(
            f"Created the default admin: {DEFAULT_ADMIN_USERNAME} / {DEFAULT_ADMIN_PASSWORD}. "
            "Sign in and choose a new password; nothing else works for this account until you do."))
