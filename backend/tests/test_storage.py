"""Uploaded files go to the configured bucket. The real S3 client runs here; only its network
transport is replaced, by a bucket in memory."""

import io
from urllib.parse import unquote, urlsplit

import httpx
import pytest
from botocore.awsrequest import AWSResponse
from botocore.httpsession import URLLib3Session
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import ContentFile
from django.core.files.storage import InMemoryStorage, default_storage, storages
from django.core.management import CommandError, call_command

from whileisleep.env import EnvError, validate_env_file
from whileisleep.storage import REQUIRED, default_storage_config

from .test_env import REQUIRED as ENV_REQUIRED
from .test_env import write
from .test_production import load_production

S3 = {
    "S3_ENDPOINT_URL": "https://account.r2.example.com",
    "S3_ACCESS_KEY_ID": "key-id",
    "S3_SECRET_ACCESS_KEY": "secret",
    "STORAGE_BUCKET": "uploads",
    "STORAGE_PUBLIC_BASE_URL": "https://cdn.example.com",
}


class Raw(io.BytesIO):
    """A response body, as much of urllib3's interface as botocore reads."""

    def stream(self, **kwargs):
        yield self.read()


class FakeBucket:
    def __init__(self):
        self.files = {}
        self.types = {}
        self.requests = []
        # Methods to answer 403 to, like a key without that permission.
        self.denied = set()

    def send(self, request):
        path = unquote(urlsplit(request.url).path)
        self.requests.append(request)
        if request.method in self.denied:
            return self.respond(request, 403, b"<Error><Code>AccessDenied</Code><Message>No</Message></Error>")
        if request.method == "PUT":
            body = request.body
            self.files[path] = body if isinstance(body, bytes) else body.read()
            content_type = request.headers["Content-Type"]
            self.types[path] = content_type.decode() if isinstance(content_type, bytes) else content_type
            return self.respond(request, 200)
        if request.method == "DELETE":
            self.files.pop(path, None)
            return self.respond(request, 204)
        if path not in self.files:
            return self.respond(request, 404, b"<Error><Code>NoSuchKey</Code><Message>No</Message></Error>")
        return self.respond(request, 200, self.files[path])

    def respond(self, request, status, body=b""):
        length = len(body)
        if request.method == "HEAD":
            body = b""
        return AWSResponse(request.url, status, {"Content-Length": str(length), "ETag": '"x"'}, Raw(body))


@pytest.fixture
def bucket(monkeypatch, settings):
    """`default_storage` on the settings above, talking to a bucket in memory."""
    fake = FakeBucket()
    monkeypatch.setattr(URLLib3Session, "send", lambda self, request: fake.send(request))
    settings.STORAGES = settings.STORAGES | {"default": default_storage_config(S3)}
    return fake


def public_site(bucket, monkeypatch):
    """The CDN in front of the bucket."""

    def handle(self, request):
        body = bucket.files.get("/uploads" + request.url.path)
        return httpx.Response(404) if body is None else httpx.Response(200, content=body)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)


# --- Settings ---


def test_no_settings_means_the_local_disk():
    assert "FileSystemStorage" in default_storage_config({})["BACKEND"]
    assert "FileSystemStorage" in default_storage_config(dict.fromkeys(REQUIRED, " "))["BACKEND"]


@pytest.mark.parametrize("name", REQUIRED)
def test_half_configured_storage_stops_startup(name):
    with pytest.raises(ImproperlyConfigured, match=f"Also set: {name}\\.") as error:
        default_storage_config(S3 | {name: ""})
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("url", ["cdn.example.com", "ftp://cdn.example.com", "https://"])
def test_public_address_must_be_a_full_url(url):
    with pytest.raises(ImproperlyConfigured, match="STORAGE_PUBLIC_BASE_URL"):
        default_storage_config(S3 | {"STORAGE_PUBLIC_BASE_URL": url})


def test_region():
    assert default_storage_config(S3)["OPTIONS"]["region_name"] == "auto"
    assert default_storage_config(S3 | {"S3_REGION": "fsn1"})["OPTIONS"]["region_name"] == "fsn1"


def test_env_file_accepts_the_settings(tmp_path):
    lines = "".join(f"{name}={value}\n" for name, value in S3.items())
    assert validate_env_file(write(tmp_path, ENV_REQUIRED + lines)).STORAGE_BUCKET == "uploads"
    with pytest.raises(EnvError, match="S3_ENDPOINT_URL"):
        validate_env_file(write(tmp_path, ENV_REQUIRED + "S3_ENDPOINT_URL=account.r2.example.com\n"))


def test_production_uses_the_bucket_and_still_serves_static_files_itself(monkeypatch):
    production = load_production(monkeypatch, **S3)
    assert production.STORAGES["default"]["BACKEND"] == "storages.backends.s3.S3Storage"
    assert production.STORAGES["default"]["OPTIONS"]["bucket_name"] == "uploads"
    assert "whitenoise" in production.STORAGES["staticfiles"]["BACKEND"]


def test_production_starts_without_a_bucket(monkeypatch):
    production = load_production(monkeypatch, **dict.fromkeys(REQUIRED))
    assert "FileSystemStorage" in production.STORAGES["default"]["BACKEND"]


def test_tests_never_use_the_developers_bucket():
    assert isinstance(storages["default"], InMemoryStorage)


# --- Files ---


def test_a_file_goes_to_the_bucket_and_back(bucket):
    name = default_storage.save("logos/cat.png", ContentFile(b"png bytes"))
    assert bucket.files == {"/uploads/logos/cat.png": b"png bytes"}
    assert bucket.types["/uploads/logos/cat.png"] == "image/png"
    with default_storage.open(name) as file:
        assert file.read() == b"png bytes"
    default_storage.delete(name)
    assert bucket.files == {}


def test_requests_go_to_the_endpoint_signed(bucket):
    default_storage.save("a.txt", ContentFile(b"a"))
    put = next(r for r in bucket.requests if r.method == "PUT")
    assert put.url.startswith("https://account.r2.example.com/uploads/a.txt")
    signature = put.headers["Authorization"]
    signature = signature.decode() if isinstance(signature, bytes) else signature
    assert signature.startswith("AWS4-HMAC-SHA256 Credential=key-id/") and "/auto/s3/" in signature
    assert not [h for h in put.headers if h.lower().startswith("x-amz-checksum")]


def test_the_same_name_twice_keeps_both_files(bucket):
    first = default_storage.save("a.txt", ContentFile(b"first"))
    second = default_storage.save("a.txt", ContentFile(b"second"))
    assert first != second
    assert sorted(bucket.files.values()) == [b"first", b"second"]


def test_links_use_the_public_address_and_carry_no_signature(bucket):
    assert default_storage.url("logos/my cat.png") == "https://cdn.example.com/logos/my%20cat.png"


def test_public_address_with_a_path(settings):
    config = default_storage_config(S3 | {"STORAGE_PUBLIC_BASE_URL": "http://localhost:9000/uploads/"})
    settings.STORAGES = settings.STORAGES | {"default": config}
    assert default_storage.url("a.png") == "http://localhost:9000/uploads/a.png"


# --- manage.py check_storage ---


def test_check_storage_passes_and_cleans_up(bucket, monkeypatch, capsys):
    public_site(bucket, monkeypatch)
    call_command("check_storage")
    assert "File storage works." in capsys.readouterr().out
    assert bucket.files == {}


def test_check_storage_without_a_bucket():
    with pytest.raises(CommandError, match="No bucket is configured"):
        call_command("check_storage")


def test_check_storage_reports_a_key_that_cannot_write(bucket):
    bucket.denied = {"PUT"}
    with pytest.raises(CommandError, match="Can't write"):
        call_command("check_storage")


def test_check_storage_reports_a_key_that_cannot_delete(bucket, monkeypatch):
    public_site(bucket, monkeypatch)
    bucket.denied = {"DELETE"}
    with pytest.raises(CommandError, match="is still there"):
        call_command("check_storage")


def test_check_storage_reports_a_wrong_public_address_and_cleans_up(bucket, monkeypatch):
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda self, request: httpx.Response(404))
    with pytest.raises(CommandError, match="answered 404"):
        call_command("check_storage")
    assert bucket.files == {}
