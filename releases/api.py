"""Release endpoints, same URLs and JSON as python-backend.

Signed in: GET /api/releases, /api/releases/<id>, /api/releases/version/<version>, /api/release-images/<id>
Public:   GET /api/public/releases, /api/public/releases/version/<version>, /api/public/release-images/<id>, only while
          PUBLIC_RELEASE_NOTES=true (404 otherwise): the same release notes without Jira numbers, for the public page.
Admins:   POST /api/admin/releases/parse (read a .docx or .csv, save nothing), POST /api/admin/releases (publish),
          and the edit endpoints below; POST /api/admin/releases/<id>/items/import adds a CSV's changes to a version. Every edit returns the whole updated release.
          GET /api/admin/releases/<id>/notes-file and POST /api/admin/releases/<id>/email: one release's notes as an
          HTML file, downloaded or emailed as an attachment.
"""
import logging
import re
import smtplib

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Max
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse
from django.utils import timezone
from rest_framework import exceptions, serializers, status
from rest_framework.decorators import api_view, parser_classes, permission_classes, throttle_classes
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response

from audit import models as audit
from audit.service import record
from accounts.authentication import BearerTokenAuthentication
from config.api import CamelCaseJSONParser, IsAdmin, IsSignedIn, NotFound, PublicReadThrottle, bad_request, not_found
from config.mail import delivery_mode
from integrations import release_generator

from .models import CATEGORY_ORDER, Category, ReleaseImage, ReleaseItem, ReleaseUpload, ReleaseVersion, Status
from .services import image_store, release_email
from .services.csv_parser import CsvParseError, parse_csv
from .services.docx_parser import MAX_BYTES, DocxParseError, parse_docx
from .services.latest import refresh_latest
from .services.release_json import all_releases_json, one_release_json, public_release_json

log = logging.getLogger(__name__)

MAX_IMAGES = 40
MAX_RECIPIENTS = 20
VERSION_PATTERN = r"^[0-9A-Za-z][0-9A-Za-z._-]*$"
EXISTING_VERSION = ("Version {version} already exists. An upload can only add a new version: edit, add or delete its "
                    "changes on the Release Notes page, or delete the whole version first and upload it again.")


# ---- Signed in: every user who has signed in reads the release notes ----

@api_view(["GET"])
@permission_classes([IsSignedIn])
def list_releases(request):
    return Response(all_releases_json())


def _release_or_404(**lookup) -> dict:
    body = one_release_json(**lookup)
    if body is None:
        what = f"version {lookup['version']}" if "version" in lookup else f"id {lookup['pk']}"
        raise NotFound(f"Release not found for {what}")
    return body


@api_view(["GET"])
@permission_classes([IsSignedIn])
def release_by_id(request, release_id):
    return Response(_release_or_404(pk=release_id))


@api_view(["GET"])
@permission_classes([IsSignedIn])
def release_by_version(request, version):
    return Response(_release_or_404(version=version))


def _signed_in(request) -> bool:
    """The Django session (what an <img> tag sends) or the app's Bearer token."""
    if request.user.is_authenticated:
        return True
    try:
        return BearerTokenAuthentication().authenticate(request) is not None
    except exceptions.APIException:
        return False


RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")


def _byte_range(header: str, size: int) -> tuple[int, int] | None:
    """(first, last) of a single "Range: bytes=..." header; None when there is none or it can't be served."""
    match = RANGE_PATTERN.match(header.strip())
    if not match or match.groups() == ("", ""):
        return None
    first, last = match.groups()
    if first == "":  # bytes=-500: the last 500 bytes
        return max(size - int(last), 0), size - 1
    first, last = int(first), min(int(last), size - 1) if last else size - 1
    return (first, last) if first <= last else None


def _file_chunks(path, first: int, length: int, chunk_size: int = 64 * 1024):
    with open(path, "rb") as f:
        f.seek(first)
        while length > 0:
            data = f.read(min(chunk_size, length))
            if not data:
                break
            length -= len(data)
            yield data


def _image_response(request, image_id, cache_control: str):
    """The screenshot or video file. Range requests get 206 and that part only: browsers need it to play videos."""
    image = ReleaseImage.objects.filter(pk=image_id).first()
    path = image_store.path_for(image.file_name) if image else None
    if path is None:
        raise Http404("Image not found.")
    size = path.stat().st_size
    byte_range = _byte_range(request.headers.get("Range", ""), size) if size else None
    if byte_range:
        first, last = byte_range
        response = StreamingHttpResponse(_file_chunks(path, first, last - first + 1), status=206,
                                         content_type=image.content_type)
        response["Content-Range"] = f"bytes {first}-{last}/{size}"
        response["Content-Length"] = str(last - first + 1)
    else:
        response = FileResponse(open(path, "rb"), content_type=image.content_type)
    response["Accept-Ranges"] = "bytes"
    response["Cache-Control"] = cache_control
    response["X-Content-Type-Options"] = "nosniff"
    return response


def release_image(request, image_id):
    """Screenshots need a signed-in user, like the release notes they belong to."""
    if not _signed_in(request):
        return HttpResponse("Sign in to see this screenshot.", status=401, content_type="text/plain")
    return _image_response(request, image_id, "private, max-age=86400")


# ---- Public: the release notes page anyone can open, while PUBLIC_RELEASE_NOTES=true ----

def _public_or_404() -> None:
    if not settings.PUBLIC_RELEASE_NOTES:
        raise Http404("Not found.")


@api_view(["GET"])
@throttle_classes([PublicReadThrottle])
def public_releases(request):
    _public_or_404()
    return Response(public_release_json(all_releases_json()))


@api_view(["GET"])
@throttle_classes([PublicReadThrottle])
def public_release_by_version(request, version):
    _public_or_404()
    return Response(public_release_json([_release_or_404(version=version)])[0])


def public_release_image(request, image_id):
    """Every screenshot belongs to a release, so all of them are as public as the release notes."""
    _public_or_404()
    return _image_response(request, image_id, "public, max-age=86400")


# ---- Shared helpers ----

def _lines(values) -> str | None:
    text = "\n".join(v.strip().replace("\n", " ") for v in values or [] if v and v.strip())
    return text or None


def _text(value) -> str | None:
    return (value or "").strip() or None


def _get_release(release_id) -> ReleaseVersion:
    release = ReleaseVersion.objects.filter(pk=release_id).first()
    if release is None:
        raise not_found("Release not found.")
    return release


def _get_item(item_id) -> ReleaseItem:
    item = ReleaseItem.objects.select_related("release_version").filter(pk=item_id).first()
    if item is None:
        raise not_found("Change not found.")
    return item


def _get_image(image_id) -> ReleaseImage:
    image = ReleaseImage.objects.select_related("release_version", "release_item").filter(pk=image_id).first()
    if image is None:
        raise not_found("Screenshot not found.")
    return image


def _edited(request, release: ReleaseVersion, details: str) -> None:
    ReleaseVersion.objects.filter(pk=release.pk).update(edited_at=timezone.now(), updated_at=timezone.now())
    record(request, audit.RELEASE_EDIT, request.user, target=str(release), details=details)


def _next_order(release: ReleaseVersion, category: str) -> int:
    return (release.items.filter(category=category).aggregate(m=Max("display_order"))["m"] or 0) + 1


def _valid(serializer_class, request, **kwargs):
    serializer = serializer_class(data=request.data, **kwargs)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


# ---- Admin: Word document upload ----

class ParsedImageSerializer(serializers.Serializer):
    # data: URL so the preview can show it without another request; stored on publish.
    data_url = serializers.CharField(max_length=7_500_000)
    caption = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)


class ParsedItemSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=Category.values)
    title = serializers.CharField(min_length=1, max_length=500)
    description = serializers.CharField(max_length=1000, required=False, allow_null=True, allow_blank=True)
    jira_id = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)
    images = ParsedImageSerializer(many=True, required=False, default=list, max_length=MAX_IMAGES)


class SourceBranchSerializer(serializers.Serializer):
    repository = serializers.CharField(max_length=100)
    branch = serializers.CharField(max_length=200)


class PublishSerializer(serializers.Serializer):
    """Required: version and at least one change. Everything else is optional."""

    file_name = serializers.CharField(min_length=1, max_length=255)
    version = serializers.RegexField(VERSION_PATTERN, min_length=1, max_length=50)
    release_date = serializers.DateField()
    status = serializers.ChoiceField(choices=Status.values, default=Status.RELEASED)
    planned_label = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    summary = serializers.CharField(max_length=1000, required=False, default="", allow_blank=True)
    highlights = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False, default=list, max_length=50)
    known_issues = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False, default=list, max_length=100)
    upgrade_notes = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False, default=list, max_length=100)
    images = ParsedImageSerializer(many=True, required=False, default=list, max_length=MAX_IMAGES)
    items = ParsedItemSerializer(many=True, min_length=1)
    # Drafted from Bitbucket: the version's release branches, which the integration screens are then limited to.
    branches = SourceBranchSerializer(many=True, required=False, default=list, max_length=20)


@api_view(["POST"])
@permission_classes([IsAdmin])
@parser_classes([MultiPartParser, FormParser])
def parse_upload(request):
    """Read a Word document or CSV file and return the release it describes, without saving anything."""
    upload = request.FILES.get("file")
    name = (upload.name or "").lower() if upload else ""
    if not name.endswith((".docx", ".csv")):
        raise bad_request("Please upload a Word document (.docx) or a CSV file (.csv).")
    data = upload.read(MAX_BYTES + 1)
    try:
        parsed = parse_csv(data) if name.endswith(".csv") else parse_docx(data)
    except (DocxParseError, CsvParseError) as exc:
        raise bad_request(str(exc))
    existing = parsed.version is not None and ReleaseVersion.objects.filter(version=parsed.version).exists()
    return Response({
        "fileName": upload.name,
        "version": parsed.version,
        "releaseDate": parsed.release_date.isoformat() if parsed.release_date else None,
        "status": parsed.status,
        "plannedLabel": parsed.planned_label,
        "summary": parsed.summary,
        "highlights": parsed.highlights,
        "knownIssues": parsed.known_issues,
        "upgradeNotes": parsed.upgrade_notes,
        "images": parsed.images,
        "items": parsed.items,
        "warnings": parsed.warnings,
        "existingVersion": existing,
    })


def _store_images(release, images, item, saved: list[str]) -> None:
    siblings = release.images.filter(release_item=item) if item else release.images.filter(release_item__isnull=True)
    start = siblings.count()
    for order, image in enumerate(images, start=start + 1):
        try:
            file_name, content_type = image_store.save_data_url(image["data_url"])
        except image_store.ImageError as exc:
            raise bad_request(str(exc))
        saved.append(file_name)
        ReleaseImage.objects.create(release_version=release, release_item=item, file_name=file_name,
                                    content_type=content_type, caption=_text(image.get("caption")), display_order=order)


@api_view(["POST"])
@permission_classes([IsAdmin])
@parser_classes([CamelCaseJSONParser])
def publish(request):
    """Create a new version from reviewed upload items.

    An upload never overwrites or adds to a version that already exists: change that version's fixes one at a time
    (add / edit / delete), or delete the whole version first and upload it again.
    """
    body = _valid(PublishSerializer, request)
    if ReleaseVersion.objects.filter(version=body["version"]).exists():
        return Response({"detail": EXISTING_VERSION.format(version=body["version"])}, status=status.HTTP_409_CONFLICT)
    saved_files: list[str] = []
    try:
        with transaction.atomic():
            release = ReleaseVersion.objects.create(version=body["version"], release_date=body["release_date"],
                                                    description="", latest=False)
            release.description = body["summary"].strip()
            release.status = body["status"]
            release.planned_label = _text(body.get("planned_label")) if body["status"] == Status.UPCOMING else None
            release.highlights = _lines(body["highlights"])
            release.known_issues = _lines(body["known_issues"])
            release.upgrade_notes = _lines(body["upgrade_notes"])

            next_order = {c: _next_order(release, c) for c in CATEGORY_ORDER}
            for parsed in body["items"]:
                item = ReleaseItem.objects.create(
                    release_version=release, category=parsed["category"], title=parsed["title"].strip(),
                    description=_text(parsed.get("description")), jira_id=_text(parsed.get("jira_id")),
                    display_order=next_order[parsed["category"]],
                )
                next_order[parsed["category"]] += 1
                _store_images(release, parsed.get("images", []), item, saved_files)
            _store_images(release, body["images"], None, saved_files)

            release.save()
            refresh_latest()

            image_count = len(body["images"]) + sum(len(i.get("images", [])) for i in body["items"])
            ReleaseUpload.objects.create(release_version=release, file_name=body["file_name"],
                                         item_count=len(body["items"]), mode="new", uploaded_by=request.user)
            record(request, audit.RELEASE_PUBLISH, request.user, target=str(release),
                   details=f"new {len(body['items'])} items, {image_count} screenshots from {body['file_name']}")
            linked = release_generator.link_branches(release.version, body["branches"], request.user)
            if linked:
                record(request, audit.INTEGRATION_SCOPE, request.user, target=str(release),
                       details="added release branches " + ", ".join(linked))
    except IntegrityError:  # the same version was uploaded at the same moment
        for file_name in saved_files:
            image_store.delete(file_name)
        return Response({"detail": EXISTING_VERSION.format(version=body["version"])}, status=status.HTTP_409_CONFLICT)
    except Exception:
        for file_name in saved_files:
            image_store.delete(file_name)
        raise
    return Response(one_release_json(pk=release.pk), status=status.HTTP_201_CREATED)


# ---- Admin: edit a published release ----

class ReleaseDetailsSerializer(serializers.Serializer):
    """Only the fields sent are changed."""

    release_date = serializers.DateField(required=False, allow_null=True)
    status = serializers.ChoiceField(choices=Status.values, required=False, allow_null=True)
    planned_label = serializers.CharField(max_length=100, required=False, allow_null=True, allow_blank=True)
    summary = serializers.CharField(max_length=1000, required=False, allow_null=True, allow_blank=True)
    highlights = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False, allow_null=True, max_length=50)
    known_issues = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False, allow_null=True, max_length=100)
    upgrade_notes = serializers.ListField(child=serializers.CharField(allow_blank=True), required=False, allow_null=True, max_length=100)


class ItemSerializer(serializers.Serializer):
    category = serializers.ChoiceField(choices=Category.values)
    title = serializers.CharField(min_length=1, max_length=500)
    description = serializers.CharField(max_length=1000, required=False, allow_null=True, allow_blank=True)
    jira_id = serializers.CharField(max_length=20, required=False, allow_null=True, allow_blank=True)


class CaptionSerializer(serializers.Serializer):
    caption = serializers.CharField(max_length=255, required=False, allow_null=True, allow_blank=True)


FIELD_NAMES = {"release_date": "date", "planned_label": "planned date", "known_issues": "known issues",
               "upgrade_notes": "upgrade notes"}


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdmin])
def release_detail(request, release_id):
    release = _get_release(release_id)
    if request.method == "DELETE":
        return _delete_release(request, release)
    body = _valid(ReleaseDetailsSerializer, request)
    changed = set(body)
    with transaction.atomic():
        if body.get("release_date"):
            release.release_date = body["release_date"]
        if body.get("status"):
            release.status = body["status"]
        if "planned_label" in changed:
            release.planned_label = _text(body["planned_label"])
        if release.status != Status.UPCOMING:
            release.planned_label = None
        if "summary" in changed:
            release.description = (body["summary"] or "").strip()
        for field in ("highlights", "known_issues", "upgrade_notes"):
            if field in changed:
                setattr(release, field, _lines(body[field]))
        release.edited_at = timezone.now()
        release.save()
        refresh_latest()  # a version that becomes "coming soon", or is released, can change which one is latest
        record(request, audit.RELEASE_EDIT, request.user, target=str(release),
               details="edited " + ", ".join(FIELD_NAMES.get(f, f) for f in sorted(changed)))
    return Response(one_release_json(pk=release.pk))


def _delete_release(request, release):
    with transaction.atomic():
        count = release.images.count()
        record(request, audit.RELEASE_DELETE, request.user, target=str(release), details=f"deleted with {count} screenshots")
        unlinked = release_generator.unlink_version(release.version)
        if unlinked:
            record(request, audit.INTEGRATION_SCOPE, request.user, target=str(release),
                   details="removed release branches " + ", ".join(unlinked))
        release.delete()  # items, screenshots (and their files) and upload history go with it
        refresh_latest()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(["POST"])
@permission_classes([IsAdmin])
def add_item(request, release_id):
    release = _get_release(release_id)
    body = _valid(ItemSerializer, request)
    with transaction.atomic():
        item = ReleaseItem.objects.create(
            release_version=release, category=body["category"], title=body["title"].strip(),
            description=_text(body.get("description")), jira_id=_text(body.get("jira_id")),
            display_order=_next_order(release, body["category"]), edited_at=timezone.now(),
        )
        _edited(request, release, f"added change {item.label}")
    return Response(one_release_json(pk=release.pk), status=status.HTTP_201_CREATED)


@api_view(["POST"])
@permission_classes([IsAdmin])
@parser_classes([MultiPartParser, FormParser])
def import_items(request, release_id):
    """Add every change in a CSV file to an existing version. Rows for a different version are left out."""
    release = _get_release(release_id)
    upload = request.FILES.get("file")
    if upload is None or not (upload.name or "").lower().endswith(".csv"):
        raise bad_request("Please upload a CSV file (.csv).")
    try:
        parsed = parse_csv(upload.read(MAX_BYTES + 1))
    except CsvParseError as exc:
        raise bad_request(str(exc))
    if parsed.version and parsed.version != release.version:
        raise bad_request(f"This CSV file is for version {parsed.version}, not {release.version}. "
                          f"Change its Version column, or leave it empty.")
    if not parsed.items:
        raise bad_request("No changes were found in the CSV file: it needs a Title column with at least one row.")
    with transaction.atomic():
        next_order = {c: _next_order(release, c) for c in CATEGORY_ORDER}
        for parsed_item in parsed.items:
            ReleaseItem.objects.create(
                release_version=release, category=parsed_item["category"], title=parsed_item["title"],
                description=parsed_item["description"], jira_id=parsed_item["jira_id"],
                display_order=next_order[parsed_item["category"]], edited_at=timezone.now(),
            )
            next_order[parsed_item["category"]] += 1
        ReleaseUpload.objects.create(release_version=release, file_name=upload.name[:255],
                                     item_count=len(parsed.items), mode="add", uploaded_by=request.user)
        _edited(request, release, f"added {len(parsed.items)} changes from {upload.name}")
    return Response({"release": one_release_json(pk=release.pk), "added": len(parsed.items), "warnings": parsed.warnings},
                    status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdmin])
def item_detail(request, item_id):
    item = _get_item(item_id)
    release = item.release_version
    with transaction.atomic():
        if request.method == "DELETE":
            label = item.label
            item.delete()  # its screenshots (and their files) go with it
            _edited(request, release, f"removed change {label}")
        else:
            body = _valid(ItemSerializer, request)
            if body["category"] != item.category:
                item.display_order = _next_order(release, body["category"])
            item.category = body["category"]
            item.title = body["title"].strip()
            item.description = _text(body.get("description"))
            item.jira_id = _text(body.get("jira_id"))
            item.edited_at = timezone.now()
            item.save()
            _edited(request, release, f"edited change {item.label}")
    return Response(one_release_json(pk=release.pk))


@api_view(["POST"])
@permission_classes([IsAdmin])
@parser_classes([MultiPartParser, FormParser])
def add_image(request, release_id):
    """Add a screenshot to a change (itemId) or to the release's gallery (no itemId)."""
    release = _get_release(release_id)
    upload = request.FILES.get("file")
    if upload is None:
        return Response({"timestamp": timezone.now().isoformat(), "status": 400, "error": "Bad Request",
                         "errors": {"file": "Field required"}}, status=400)
    caption = request.data.get("caption")
    if caption and len(caption) > 255:
        raise bad_request("The caption is longer than 255 characters.")
    item = None
    item_id = request.data.get("itemId")
    if item_id:
        try:
            item = _get_item(int(item_id))
        except ValueError:
            raise bad_request("itemId must be a number.")
        if item.release_version_id != release.id:
            raise bad_request("That change belongs to another release.")
    try:
        file_name, content_type = image_store.save_bytes(upload.read(image_store.MAX_UPLOAD_BYTES + 1))
    except image_store.ImageError as exc:
        raise bad_request(str(exc))
    try:
        with transaction.atomic():
            siblings = release.images.filter(release_item=item) if item else release.images.filter(release_item__isnull=True)
            ReleaseImage.objects.create(
                release_version=release, release_item=item, file_name=file_name, content_type=content_type,
                caption=_text(caption), display_order=(siblings.aggregate(m=Max("display_order"))["m"] or 0) + 1,
            )
            if item:
                ReleaseItem.objects.filter(pk=item.pk).update(edited_at=timezone.now())
            _edited(request, release, f"added a screenshot to {item.label if item else 'the gallery'}")
    except Exception:
        image_store.delete(file_name)
        raise
    return Response(one_release_json(pk=release.pk), status=status.HTTP_201_CREATED)


@api_view(["PATCH", "DELETE"])
@permission_classes([IsAdmin])
def image_detail(request, image_id):
    image = _get_image(image_id)
    release = image.release_version
    with transaction.atomic():
        if request.method == "DELETE":
            where = image.release_item.label if image.release_item else "the gallery"
            image.delete()  # the file is removed after the commit
            _edited(request, release, f"removed a screenshot from {where}")
        else:
            image.caption = _text(_valid(CaptionSerializer, request).get("caption"))
            image.save(update_fields=["caption"])
            _edited(request, release, "edited a screenshot caption")
    return Response(one_release_json(pk=release.pk))


# ---- Release notes as a file: download, or email as an attachment ----

@api_view(["GET"])
@permission_classes([IsAdmin])
def release_notes_file(request, release_id):
    release = _release_or_404(pk=release_id)
    response = HttpResponse(release_email.notes_html(release), content_type="text/html; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{release_email.file_name(release)}"'
    return response


class ReleaseEmailSerializer(serializers.Serializer):
    to = serializers.ListField(child=serializers.EmailField(max_length=191), min_length=1, max_length=MAX_RECIPIENTS)
    cc = serializers.ListField(child=serializers.EmailField(max_length=191), required=False, default=list,
                               max_length=MAX_RECIPIENTS)
    message = serializers.CharField(required=False, allow_blank=True, default="", max_length=2000)


@api_view(["POST"])
@permission_classes([IsAdmin])
@parser_classes([CamelCaseJSONParser])
def email_release(request, release_id):
    release = _release_or_404(pk=release_id)
    body = _valid(ReleaseEmailSerializer, request)
    to = list(dict.fromkeys(a.lower() for a in body["to"]))
    cc = [a for a in dict.fromkeys(a.lower() for a in body["cc"]) if a not in to]
    user = request.user
    email = release_email.build_email(release, to=to, cc=cc, message=body["message"],
                                      sender_name=getattr(user, "display_name", None) or user.username,
                                      reply_to=getattr(user, "email", None))
    mode = delivery_mode()
    target = f"Version {release['version']}"
    try:
        email.send(fail_silently=False)
    except (smtplib.SMTPException, OSError) as exc:
        # The reason is logged for the server admin; the browser gets a message without server details.
        log.warning("Release notes email for %s failed: %s: %s", target, type(exc).__name__, exc)
        record(request, audit.RELEASE_EMAIL, user, target=target, details=f"failed ({type(exc).__name__})")
        return Response({"detail": "The mail server didn't accept the email. Check the SMTP settings; "
                                   "the server log has the reason."}, status=status.HTTP_502_BAD_GATEWAY)
    record(request, audit.RELEASE_EMAIL, user, target=target,
           details=f"{mode}: to {', '.join(to)}" + (f"; cc {', '.join(cc)}" if cc else ""))
    return Response({"delivery": mode, "recipients": to + cc, "attachment": release_email.file_name(release)})
