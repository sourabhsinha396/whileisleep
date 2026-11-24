"""Uploaded images are checked, re-saved without metadata, and kept in folders."""

import io
import re
from types import SimpleNamespace

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from ninja.errors import HttpError
from PIL import Image

from whileisleep import folders, images
from whileisleep.storage import default_storage_config

from .test_storage import S3


def picture(kind="PNG", size=(40, 20), mode="RGB", name="a.png", **save) -> SimpleUploadedFile:
    out = io.BytesIO()
    Image.new(mode, size, "red" if mode == "RGB" else None).save(out, kind, **save)
    return SimpleUploadedFile(name, out.getvalue())


def opened(content) -> Image.Image:
    return Image.open(io.BytesIO(content.read()))


# --- Checking ---


@pytest.mark.parametrize(("kind", "extension"), [("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")])
def test_accepted_formats_keep_their_format(kind, extension):
    # The name says otherwise; the content decides.
    clean = images.clean_image(picture(kind, name="evil.html"), 100)
    assert clean.name == f"image.{extension}"
    assert opened(clean).format == kind


@pytest.mark.parametrize(
    "content",
    [
        b"<svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>",
        b"<html><script>alert(1)</script></html>",
        b"GIF89a" + b"\0" * 40,
        b"",
    ],
)
def test_other_files_are_refused_whatever_their_name(content):
    with pytest.raises(HttpError, match="PNG, JPEG or WebP"):
        images.clean_image(SimpleUploadedFile("a.png", content, content_type="image/png"), 100)


def test_gif_is_refused():
    with pytest.raises(HttpError, match="PNG, JPEG or WebP"):
        images.clean_image(picture("GIF"), 100)


def test_a_damaged_image_is_refused():
    whole = picture(size=(300, 300)).read()
    with pytest.raises(HttpError, match="can't be read|PNG, JPEG"):
        images.clean_image(SimpleUploadedFile("a.png", whole[: len(whole) // 2]), 100)


def test_a_big_file_is_refused(monkeypatch):
    monkeypatch.setattr(images, "MAX_BYTES", 10)
    with pytest.raises(HttpError, match="too big"):
        images.clean_image(picture(), 100)


def test_a_small_file_that_unpacks_to_a_huge_picture_is_refused(monkeypatch):
    monkeypatch.setattr(images, "MAX_PIXELS", 100)
    with pytest.raises(HttpError, match="too many pixels"):
        images.clean_image(picture(size=(11, 10)), 100)


def test_code_hidden_behind_an_image_is_dropped():
    upload = SimpleUploadedFile("a.png", picture().read() + b"<script>alert(1)</script>")
    assert b"script" not in images.clean_image(upload, 100).read()


def test_camera_data_is_dropped():
    exif = Image.Exif()
    exif[0x010F] = "SecretCamera"
    exif[0x8825] = {1: "N", 2: (52.0, 31.0, 0.0)}
    clean = images.clean_image(picture("JPEG", exif=exif), 100)
    assert not opened(clean).getexif()
    clean.seek(0)
    assert b"SecretCamera" not in clean.read()


def test_png_text_is_dropped():
    from PIL.PngImagePlugin import PngInfo

    info = PngInfo()
    info.add_text("Comment", "secret-comment")
    assert b"secret-comment" not in images.clean_image(picture(pnginfo=info), 100).read()


def test_a_sideways_photo_is_turned_upright():
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90
    assert opened(images.clean_image(picture("JPEG", size=(40, 20), exif=exif), 100)).size == (20, 40)


def test_cmyk_jpegs_become_rgb():
    assert opened(images.clean_image(picture("JPEG", mode="CMYK"), 100)).mode == "RGB"


@pytest.mark.parametrize("mode", ["RGBA", "LA", "P", "L", "1", "I;16"])
def test_every_kind_of_png_is_accepted(mode):
    out = io.BytesIO()
    Image.new(mode, (30, 30)).save(out, "PNG")
    for square in (False, True):
        images.clean_image(SimpleUploadedFile("a.png", out.getvalue()), 20, square=square)


def test_transparency_survives():
    clean = images.clean_image(picture(mode="RGBA"), 100, square=True)
    assert opened(clean).mode == "RGBA"


# --- Sizes ---


def test_pictures_shrink_to_fit_and_keep_their_shape():
    assert opened(images.clean_image(picture(size=(400, 200)), 100)).size == (100, 50)


def test_small_pictures_are_not_enlarged():
    assert opened(images.clean_image(picture(size=(40, 20)), 100)).size == (40, 20)
    assert opened(images.clean_image(picture(size=(40, 20)), 100, square=True)).size == (20, 20)


def test_square_pictures_are_cropped_square():
    assert opened(images.clean_image(picture(size=(400, 200)), 100, square=True)).size == (100, 100)


# --- Folders ---


def test_every_kind_of_file_has_its_folder():
    name = r"/[0-9a-f]{32}\.png"
    article = SimpleNamespace(pk=7, workspace_id=3)
    assert re.fullmatch(r"workspaces/3/logo" + name, folders.workspace_logo(SimpleNamespace(pk=3), "image.png"))
    assert re.fullmatch(
        r"workspaces/3/articles/7" + name, folders.article_image(SimpleNamespace(article=article), "image.png")
    )
    assert re.fullmatch(r"users/5/photo" + name, folders.user_photo(SimpleNamespace(user_id=5), "image.png"))


def test_file_names_are_random_and_ignore_the_uploaded_name():
    names = {folders.workspace_logo(SimpleNamespace(pk=3), "../../other/logo.PNG") for _ in range(20)}
    assert len(names) == 20
    assert all(n.startswith("workspaces/3/logo/") and ".." not in n and n.endswith(".png") for n in names)


# --- Storage ---


def test_uploads_need_a_bucket(settings):
    settings.UPLOADS_ENABLED = False
    with pytest.raises(HttpError) as error:
        images.require_storage()
    assert error.value.status_code == 503


def test_files_may_be_cached_forever_because_names_are_never_reused():
    assert "immutable" in default_storage_config(S3)["OPTIONS"]["object_parameters"]["CacheControl"]


@pytest.mark.django_db
def test_delete_later_deletes_and_never_fails(monkeypatch):
    name = default_storage.save("workspaces/1/logo/a.png", ContentFile(b"x"))
    images.delete_later(name)
    assert not default_storage.exists(name)
    images.delete_later("")

    def broken(name):
        raise OSError("bucket is down")

    monkeypatch.setattr(default_storage, "delete", broken)
    images.delete_later("workspaces/1/logo/b.png")
