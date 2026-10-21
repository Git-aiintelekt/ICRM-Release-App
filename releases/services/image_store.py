"""Screenshot files for release notes, stored on disk under <UPLOAD_DIR>/release-images/ (settings.IMAGE_DIR).

Files get random names; only PNG, JPEG, GIF and WebP (checked from the bytes, not the name) are kept.
"""
import base64
import re
import uuid
from pathlib import Path

from django.conf import settings
MAX_IMAGE_BYTES = 5 * 1024 * 1024

_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp"}
_DATA_URL_RE = re.compile(r"^data:(image/[a-z]+);base64,([A-Za-z0-9+/=\s]+)$")
_SAFE_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|gif|webp)$")


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
    return None


def to_data_url(data: bytes) -> str:
    content_type = sniff(data)
    if content_type is None:
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
    return save_bytes(data)


def save_bytes(data: bytes) -> tuple[str, str]:
    """Validate raw image bytes (a direct upload) and store them. Returns (file_name, content_type)."""
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageError("The screenshot is larger than 5 MB.")
    content_type = sniff(data)
    if content_type is None:
        raise ImageError("Screenshots must be PNG, JPEG, GIF or WebP.")
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
