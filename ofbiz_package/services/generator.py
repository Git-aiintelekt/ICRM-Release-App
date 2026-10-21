"""Build the OFBiz component zip: release-notes-<latest version>-<YYYYMMDD-HHMM>.zip.

The zip holds one folder, release-notes/, which is unzipped into <ofbiz>/hot-deploy-ext/. It contains
  * the component config (ofbiz-component.xml, web.xml, controller.xml, a decorator and the menu seed data),
  * main.ftl: the viewer's index.html with every release embedded as window.__RELEASE_NOTES__,
  * the prebuilt React viewer (viewer_build/, from `npm run build:ofbiz`) and every screenshot,
  * package-manifest.json with counts and a SHA-256 for every file.
OFBiz needs nothing else at runtime.
"""
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from releases.models import ReleaseImage, ReleaseVersion, Status
from releases.services import image_store
from releases.services.release_json import all_releases_json

from ..models import OfbizPackage

APP_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = APP_DIR / "component_template"
VIEWER_DIR = APP_DIR / "viewer_build"
COMPONENT = "release-notes"
RESOURCE_URL = "/release-notes-resource"
PACKAGE_FORMAT = 1
# Files of the viewer build that belong in the package (public/samples is only for the upload page).
VIEWER_FILES = re.compile(r"^(assets/.+|favicon\.ico|favicon\.svg|icons\.svg)$")


class PackageError(Exception):
    """The package can't be built; the message says what to fix."""


@dataclass
class Preview:
    """What the next package would contain, and anything that stops it from being built."""

    version: str | None = None
    version_count: int = 0
    item_count: int = 0
    image_count: int = 0
    versions: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    viewer_built_at: str | None = None

    @property
    def ready(self) -> bool:
        return not self.errors


def _package_version() -> tuple[str | None, list[str]]:
    """The version the package is named after: the one marked Latest, else the newest released one."""
    latest = ReleaseVersion.objects.filter(latest=True).order_by("-release_date").first()
    if latest:
        return latest.version, []
    fallback = (ReleaseVersion.objects.filter(status=Status.RELEASED).order_by("-release_date").first()
                or ReleaseVersion.objects.order_by("-release_date").first())
    if fallback is None:
        return None, []
    return fallback.version, [f"No version is marked Latest; the package is named after {fallback.version}."]


def viewer_info() -> dict | None:
    info = VIEWER_DIR / "viewer-build.json"
    if not (VIEWER_DIR / "index.html").is_file():
        return None
    try:
        return json.loads(info.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def preview() -> Preview:
    result = Preview()
    result.version, result.warnings = _package_version()
    releases = all_releases_json()
    result.version_count = len(releases)
    result.item_count = sum(len(r["items"]) for r in releases)
    result.versions = [
        {"version": r["version"], "releaseDate": r["releaseDate"], "status": r["status"], "isLatest": r["isLatest"],
         "items": len(r["items"])}
        for r in releases
    ]
    images = list(ReleaseImage.objects.select_related("release_version"))
    result.image_count = len(images)
    if not releases:
        result.errors.append("There are no release versions to package yet.")
    missing = [i for i in images if image_store.path_for(i.file_name) is None]
    for image in missing[:10]:
        result.errors.append(f"Screenshot file missing for {image.release_version} (image #{image.id}, {image.file_name}). "
                             "Upload it again or delete the screenshot.")
    if len(missing) > 10:
        result.errors.append(f"...and {len(missing) - 10} more missing screenshot files.")
    info = viewer_info()
    if info is None:
        result.errors.append("The OFBiz viewer isn't built. Run: python manage.py build_ofbiz_viewer")
    else:
        result.viewer_built_at = info.get("builtAt")
    return result


def _script_json(value) -> str:
    """JSON that is safe inside <script> and inside FreeMarker's <#noparse> (no '<', '>' or '&' left)."""
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return (text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _main_ftl(index_html: str, data: dict, file_name: str) -> str:
    script = f"<script>window.__RELEASE_NOTES__ = {_script_json(data)};</script>\n"
    marker = '<script type="module"'
    if marker not in index_html:
        raise PackageError("The viewer build's index.html has no module script. Rebuild it: python manage.py build_ofbiz_viewer")
    html = index_html.replace(marker, script + "    " + marker, 1)
    if "</#noparse>" in html:
        raise PackageError("The viewer build contains '</#noparse>', which FreeMarker can't embed.")
    # <#noparse>: FreeMarker outputs the page exactly as it is (release text may contain ${...}).
    return (f"<#-- iCRM Release Notes page, generated by the Release Notes Django app ({file_name}). "
            f"Do not edit: generate a new package instead. -->\n<#noparse>{html}</#noparse>\n")


def _file_name(version: str, when) -> str:
    safe = re.sub(r"[^0-9A-Za-z._-]", "-", version)
    base = f"release-notes-{safe}-{when:%Y%m%d-%H%M}"
    name, n = f"{base}.zip", 2
    while (settings.PACKAGE_DIR / name).exists() or OfbizPackage.objects.filter(file_name=name).exists():
        name, n = f"{base}-{n}.zip", n + 1
    return name


def _fill(text: str, values: dict) -> str:
    for key, value in values.items():
        text = text.replace(f"@@{key}@@", str(value))
    return text


def generate(user=None) -> OfbizPackage:
    """Build the zip into PACKAGE_DIR and record it. Raises PackageError when it can't be built."""
    check = preview()
    if not check.ready:
        raise PackageError(" ".join(check.errors))

    now = timezone.now().replace(microsecond=0)
    file_name = _file_name(check.version, now)
    generated_by = (user.email or user.username) if user else "command line"
    info = {"fileName": file_name, "version": check.version, "generatedAt": now.isoformat(), "generatedBy": generated_by}

    image_url = lambda image: f"{RESOURCE_URL}/images/{image.file_name}"  # noqa: E731
    releases = all_releases_json(image_url)
    data = {"releases": releases, "package": info, "homeUrl": settings.OFBIZ_HOME_URL}

    values = {"FILE_NAME": file_name, "VERSION": check.version, "GENERATED_AT": now.strftime("%Y-%m-%d %H:%M"),
              "GENERATED_BY": generated_by, "VERSION_COUNT": len(releases),
              "ITEM_COUNT": sum(len(r["items"]) for r in releases), "IMAGE_COUNT": check.image_count}
    files: dict[str, bytes] = {}
    for path in sorted(TEMPLATE_DIR.rglob("*")):
        if path.is_file():
            files[path.relative_to(TEMPLATE_DIR).as_posix()] = _fill(path.read_text(encoding="utf-8"), values).encode("utf-8")

    for path in sorted(VIEWER_DIR.rglob("*")):
        relative = path.relative_to(VIEWER_DIR).as_posix()
        if path.is_file() and VIEWER_FILES.match(relative):
            files[f"webapp/release-notes-resource/{relative}"] = path.read_bytes()
    index_html = (VIEWER_DIR / "index.html").read_text(encoding="utf-8")
    files["webapp/release-notes/main.ftl"] = _main_ftl(index_html, data, file_name).encode("utf-8")

    for image in ReleaseImage.objects.all():
        path = image_store.path_for(image.file_name)
        files[f"webapp/release-notes-resource/images/{image.file_name}"] = path.read_bytes()

    manifest = {
        "packageFormat": PACKAGE_FORMAT,
        "component": COMPONENT,
        **info,
        "counts": {"versions": len(releases), "items": values["ITEM_COUNT"], "screenshots": check.image_count},
        "versions": check.versions,
        "viewerBuiltAt": check.viewer_built_at,
        "files": {name: hashlib.sha256(content).hexdigest() for name, content in sorted(files.items())},
    }
    files["package-manifest.json"] = json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(zipfile.ZipInfo(f"{COMPONENT}/{name}", date_time=now.timetuple()[:6]), content,
                             compress_type=zipfile.ZIP_DEFLATED)
    content = buffer.getvalue()

    settings.PACKAGE_DIR.mkdir(parents=True, exist_ok=True)
    target = settings.PACKAGE_DIR / file_name
    with transaction.atomic():
        package = OfbizPackage.objects.create(
            file_name=file_name, release_version=check.version, generated_at=now, generated_by=user,
            generated_by_name=generated_by, size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
            version_count=len(releases), item_count=values["ITEM_COUNT"], image_count=check.image_count,
        )
        target.write_bytes(content)
    return package
