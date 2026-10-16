"""Helpers for safe, private file storage."""
import hashlib
import uuid
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.deconstruct import deconstructible
from PIL import Image, UnidentifiedImageError

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG", "WEBP"}


@deconstructible
class RandomUploadPath:
    """upload_to that discards the client filename (no path tricks, no PII in names)."""

    def __init__(self, prefix: str):
        self.prefix = prefix

    def __call__(self, instance, filename: str) -> str:
        ext = PurePosixPath(filename).suffix.lower()[:6] or ".jpg"
        return f"{self.prefix}/{uuid.uuid4().hex}{ext}"

    def __eq__(self, other):
        return isinstance(other, RandomUploadPath) and other.prefix == self.prefix


def random_upload_path(prefix: str) -> RandomUploadPath:
    return RandomUploadPath(prefix)


def validate_image(file) -> None:
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if file.size > max_bytes:
        raise ValidationError(f"Image larger than {settings.MAX_UPLOAD_MB} MB.")
    try:
        file.seek(0)
        with Image.open(file) as img:
            fmt = img.format
            img.verify()
    except (UnidentifiedImageError, OSError) as exc:
        raise ValidationError("File is not a valid image.") from exc
    finally:
        file.seek(0)
    if fmt not in ALLOWED_IMAGE_FORMATS:
        raise ValidationError("Only JPEG, PNG or WEBP images are allowed.")


def sha256_of(file) -> str:
    digest = hashlib.sha256()
    file.seek(0)
    for chunk in file.chunks() if hasattr(file, "chunks") else iter(lambda: file.read(65536), b""):
        digest.update(chunk)
    file.seek(0)
    return digest.hexdigest()
