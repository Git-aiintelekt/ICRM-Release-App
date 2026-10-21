"""Build the read-only React viewer for OFBiz and copy it into ofbiz_package/viewer_build/.

Needed only after changing the React UI (frontend/src). The build is kept in the repository, so servers
that generate packages don't need Node.js.
"""
import json
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ofbiz_package.services.generator import VIEWER_DIR


class Command(BaseCommand):
    help = "Build the OFBiz viewer (npm run build:ofbiz) into ofbiz_package/viewer_build/."

    def add_arguments(self, parser):
        parser.add_argument("--skip-npm", action="store_true", help="Copy frontend/dist-ofbiz as it is, without building.")

    def handle(self, *args, skip_npm=False, **options):
        frontend = Path(settings.FRONTEND_DIR)
        if not skip_npm:
            npm = shutil.which("npm")
            if npm is None:
                raise CommandError("npm is not installed. Install Node.js, or copy a built frontend/dist-ofbiz and use --skip-npm.")
            if not (frontend / "node_modules").is_dir():
                self.stdout.write("Installing frontend packages (npm ci)...")
                subprocess.run([npm, "ci", "--no-audit", "--no-fund"], cwd=frontend, check=True)
            self.stdout.write("Building the viewer (npm run build:ofbiz)...")
            subprocess.run([npm, "run", "build:ofbiz"], cwd=frontend, check=True)
        built = frontend / "dist-ofbiz"
        if not (built / "index.html").is_file():
            raise CommandError(f"{built} has no index.html. Run `npm run build:ofbiz` in {frontend}.")
        if VIEWER_DIR.exists():
            shutil.rmtree(VIEWER_DIR)
        shutil.copytree(built, VIEWER_DIR, ignore=shutil.ignore_patterns("samples"))
        (VIEWER_DIR / "viewer-build.json").write_text(json.dumps({"builtAt": timezone.now().replace(microsecond=0).isoformat()}))
        files = sorted(p.relative_to(VIEWER_DIR).as_posix() for p in VIEWER_DIR.rglob("*") if p.is_file())
        self.stdout.write(self.style.SUCCESS(f"Viewer copied to {VIEWER_DIR}: {', '.join(files)}"))
