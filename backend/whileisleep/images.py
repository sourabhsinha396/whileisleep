"""Checks images people upload, and deletes the ones they replace.

An image is decoded and saved again, never stored as it came. So what reaches the bucket is
an image whatever the file claimed to be, has no scripts (SVG isn't accepted), carries no
camera data such as where a photo was taken, and is no bigger than it needs to be.
"""

import io
import logging

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from ninja.errors import HttpError
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)

MAX_BYTES = 5 * 1024 * 1024
# A small file can unpack to an enormous picture; its header says how big before we try.
MAX_PIXELS = 40_000_000
FORMATS = {"PNG": "png", "JPEG": "jpg", "WEBP": "webp"}
# Longest side, in pixels. Avatars show at 64px at most, so this stays sharp on any screen.
AVATAR_SIDE = 256
PICTURE_SIDE = 1600


def require_storage() -> None:
    if not settings.UPLOADS_ENABLED:
        raise HttpError(503, "Uploads are off: file storage isn't set up on this server.")


def clean_image(upload, max_side: int, square: bool = False) -> ContentFile:
    """The uploaded image, checked and resized. HttpError 400 says what is wrong with it."""
    if upload.size > MAX_BYTES:
        raise HttpError(400, f"That image is too big. The limit is {MAX_BYTES // (1024 * 1024)} MB.")
    try:
        with Image.open(upload, formats=list(FORMATS)) as image:
            kind = image.format
            if image.width * image.height > MAX_PIXELS:
                raise HttpError(400, "That image has too many pixels. Make it smaller and try again.")
            # The camera's "this way up" note is about to be dropped, so turn the picture itself.
            image = ImageOps.exif_transpose(image)
            if kind == "JPEG" and image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            if square:
                side = min(max_side, *image.size)
                image = ImageOps.fit(image, (side, side))
            else:
                image.thumbnail((max_side, max_side))
            # A copy of the pixels alone leaves every kind of metadata behind; the color
            # profile is kept, because the pixels mean the wrong colors without it.
            profile = image.info.get("icc_profile")
            image.info = {key: value for key, value in image.info.items() if key == "transparency"}
            out = io.BytesIO()
            extra = {"icc_profile": profile} if profile else {}
            image.save(out, kind, optimize=True, quality=88, **extra)
    except UnidentifiedImageError:
        raise HttpError(400, "Use a PNG, JPEG or WebP image.") from None
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        # What Pillow raises for a damaged file depends on where it is damaged.
        raise HttpError(400, "That image can't be read. It may be damaged.") from None
    return ContentFile(out.getvalue(), name=f"image.{FORMATS[kind]}")


def delete_later(name: str) -> None:
    """Deletes a file once the change that dropped it is saved. A failure leaves an unused
    file behind, which is not worth failing the person's request for."""
    if not name:
        return

    def delete():
        try:
            default_storage.delete(name)
        except Exception:
            logger.warning("Could not delete %s", name, exc_info=True)

    transaction.on_commit(delete)


def replace(instance, field: str, content: ContentFile | None) -> None:
    """Sets an image field, or clears it with None, and drops the previous file."""
    previous = getattr(instance, field).name
    setattr(instance, field, content or "")
    instance.save(update_fields=[field])
    delete_later(previous)
