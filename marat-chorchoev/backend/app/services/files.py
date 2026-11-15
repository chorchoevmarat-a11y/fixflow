"""Evidence image validation and storage (COMM-05 / COMM-06 / SEC-04)."""

import contextlib
import hashlib
import io
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.core.errors import PayloadTooLarge, Unprocessable

_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
_CHUNK = 64 * 1024

# Pillow raises DecompressionBombError above this; we also check explicitly below.
Image.MAX_IMAGE_PIXELS = settings.MAX_IMAGE_PIXELS


@dataclass(slots=True)
class ValidatedImage:
    data: bytes
    content_type: str
    extension: str
    width: int
    height: int
    sha256: str


async def read_image(upload: UploadFile) -> ValidatedImage:
    """Read at most MAX_UPLOAD_BYTES and verify the bytes really are an allowed image."""
    buffer = bytearray()
    while chunk := await upload.read(_CHUNK):
        buffer.extend(chunk)
        if len(buffer) > settings.MAX_UPLOAD_BYTES:
            raise PayloadTooLarge("Image is larger than 10 MiB.", code="FILE_TOO_LARGE")
    if not buffer:
        raise Unprocessable("The uploaded file is empty.", code="FILE_EMPTY")
    data = bytes(buffer)
    try:
        with Image.open(io.BytesIO(data)) as probe:
            image_format = probe.format
            width, height = probe.size
            probe.verify()
        if image_format not in _FORMATS:
            raise Unprocessable(
                "Only JPEG, PNG, or WebP images are accepted.", code="FILE_TYPE_UNSUPPORTED"
            )
        if (
            width <= 0
            or height <= 0
            or width > settings.MAX_IMAGE_SIDE
            or height > settings.MAX_IMAGE_SIDE
            or width * height > settings.MAX_IMAGE_PIXELS
        ):
            raise Unprocessable("Image dimensions are too large.", code="IMAGE_DIMENSIONS")
        # verify() does not decode pixel data; decode once to reject truncated images.
        with Image.open(io.BytesIO(data)) as full:
            full.load()
    except Unprocessable:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError, SyntaxError):
        raise Unprocessable(
            "The file is not a valid JPEG, PNG, or WebP image.", code="FILE_TYPE_UNSUPPORTED"
        ) from None
    content_type, extension = _FORMATS[image_format]
    return ValidatedImage(
        data=data,
        content_type=content_type,
        extension=extension,
        width=width,
        height=height,
        sha256=hashlib.sha256(data).hexdigest(),
    )


def _root() -> Path:
    return Path(settings.UPLOAD_DIR).resolve()


def new_storage_key(org_id: uuid.UUID, extension: str) -> str:
    """Server-generated key; nothing user-controlled ever becomes part of a path."""
    return f"{org_id}/{uuid.uuid4().hex}.{extension}"


def path_for(storage_key: str) -> Path:
    root = _root()
    path = (root / storage_key).resolve()
    if not path.is_relative_to(root):
        raise Unprocessable("Invalid storage key.", code="FILE_INVALID")
    return path


def store(storage_key: str, data: bytes) -> None:
    path = path_for(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_bytes(data)
    temp.replace(path)


def discard(storage_key: str) -> None:
    with contextlib.suppress(OSError):
        path_for(storage_key).unlink(missing_ok=True)


def safe_name(name: str | None) -> str:
    cleaned = Path(name or "image").name.replace("\x00", "").strip() or "image"
    return cleaned[:255]
