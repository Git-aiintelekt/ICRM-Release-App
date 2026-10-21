"""Generate an OFBiz package from the command line (the same as Admin -> OFBiz packages -> Generate)."""
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from ofbiz_package.services.generator import PackageError, generate, preview


class Command(BaseCommand):
    help = "Generate release-notes-<version>-<YYYYMMDD-HHMM>.zip into PACKAGE_DIR from the current release notes."

    def add_arguments(self, parser):
        parser.add_argument("--build-viewer", action="store_true", help="Rebuild the React viewer first (needs npm).")
        parser.add_argument("--check", action="store_true", help="Only show what the package would contain.")

    def handle(self, *args, build_viewer=False, check=False, **options):
        if build_viewer:
            call_command("build_ofbiz_viewer")
        info = preview()
        self.stdout.write(f"Latest version {info.version}: {info.version_count} versions, {info.item_count} changes, "
                          f"{info.image_count} screenshots. Viewer built {info.viewer_built_at or 'never'}.")
        for warning in info.warnings:
            self.stdout.write(self.style.WARNING(f"Warning: {warning}"))
        for error in info.errors:
            self.stderr.write(self.style.ERROR(error))
        if check:
            return
        try:
            package = generate()
        except PackageError as exc:
            raise CommandError(str(exc))
        self.stdout.write(self.style.SUCCESS(f"Generated {package.path} ({package.size_bytes:,} bytes, sha256 {package.sha256})"))
