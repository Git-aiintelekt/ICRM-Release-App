"""Screenshot files for release notes, stored on disk under <UPLOAD_DIR>/release-images/ (settings.IMAGE_DIR).

Files get random names; only PNG, JPEG, GIF and WebP images (up to 5 MB) and MP4 and WebM videos (up to 25 MB,
uploaded directly, not from a Word document) are kept, checked from the bytes, not the name.
"""
import base64
import re
import uuid
from pathlib import Path

from django.conf import settings
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_VIDEO_BYTES = 25 * 1024 * 1024
MAX_UPLOAD_BYTES = max(MAX_IMAGE_BYTES, MAX_VIDEO_BYTES)

_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp",
               "video/mp4": "mp4", "video/webm": "webm"}
_DATA_URL_RE = re.compile(r"^data:(image/[a-z]+);base64,([A-Za-z0-9+/=\s]+)$")
_SAFE_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|gif|webp|mp4|webm)$")


class ImageError(ValueError):
    pass


def sniff(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return sniff_video(data)


def sniff_video(data: bytes) -> str | None:
    if data[4:8] == b"ftyp":  # ISO base media: MP4 (and QuickTime .mov, which browsers play as MP4)
        return "video/mp4"
    if data.startswith(b"\x1a\x45\xdf\xa3"):  # EBML header: WebM
        return "video/webm"
    return None


def is_video(content_type: str | None) -> bool:
    return (content_type or "").startswith("video/")


def to_data_url(data: bytes) -> str:
    content_type = sniff(data)
    if content_type is None or is_video(content_type):
        raise ImageError("Unsupported image format.")
    return f"data:{content_type};base64,{base64.b64encode(data).decode()}"


def save_data_url(data_url: str) -> tuple[str, str]:
    """Validate a data: URL from the upload preview and store it. Returns (file_name, content_type)."""
    match = _DATA_URL_RE.match(data_url)
    if not match:
        raise ImageError("A screenshot is not a valid image.")
    try:
        data = base64.b64decode(match.group(2), validate=False)
    except ValueError as exc:
        raise ImageError("A screenshot is not a valid image.") from exc
    if is_video(sniff(data)):
        raise ImageError("A screenshot is not a valid image.")
    return save_bytes(data)


def save_bytes(data: bytes) -> tuple[str, str]:
    """Validate raw image or video bytes (a direct upload) and store them. Returns (file_name, content_type)."""
    content_type = sniff(data)
    if content_type is None:
        raise ImageError("Screenshots must be PNG, JPEG, GIF or WebP images, or MP4 or WebM videos.")
    if is_video(content_type):
        if len(data) > MAX_VIDEO_BYTES:
            raise ImageError("The video is larger than 25 MB.")
    elif len(data) > MAX_IMAGE_BYTES:
        raise ImageError("The screenshot is larger than 5 MB.")
    image_dir = Path(settings.IMAGE_DIR)
    image_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid.uuid4().hex}.{_EXTENSIONS[content_type]}"
    (image_dir / file_name).write_bytes(data)
    return file_name, content_type


def path_for(file_name: str) -> Path | None:
    if not _SAFE_NAME_RE.match(file_name):
        return None
    path = Path(settings.IMAGE_DIR) / file_name
    return path if path.is_file() else None


def delete(file_name: str) -> None:
    path = path_for(file_name)
    if path:
        path.unlink(missing_ok=True)
