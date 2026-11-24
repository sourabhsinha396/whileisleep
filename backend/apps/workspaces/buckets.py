"""Files in a customer's own S3-compatible bucket (Cloudflare R2, AWS S3, Hetzner, MinIO...).

The server's own storage is Django's `default_storage`; this is the other one. The address is
one a customer typed in, so every request goes through whileisleep.outbound, which keeps it
out of our own network. That rules out boto3's client, which connects by itself: botocore
only signs here.
"""

import re
import uuid
from urllib.parse import quote, urlsplit

import httpx
from botocore.auth import S3SigV4Auth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials
from django.conf import settings

from whileisleep import outbound

from .models import Bucket

# Everything of ours is in this folder, so the bucket can hold other things too.
FOLDER = "whileisleep"
BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
REGION = re.compile(r"^[a-z0-9-]{1,40}$")
CACHE_FOREVER = "public, max-age=31536000, immutable"
TIMEOUT_SECONDS = 15


class BucketError(Exception):
    """The bucket can't be used. The message is for its owner."""


# --- What a customer types ---


def clean_address(value: str, name: str) -> str:
    """A bare address: https://host, maybe with a path, and nothing hidden in it."""
    value = value.strip().rstrip("/")
    try:
        parts = urlsplit(value)
        valid = bool(parts.hostname) and (parts.port is None or parts.port > 0)
    except ValueError:
        valid = False
    # Private networks are for self-hosters, whose MinIO often has no certificate.
    schemes = {"https", "http"} if settings.OUTBOUND_ALLOW_PRIVATE_NETWORKS else {"https"}
    if not valid or parts.scheme not in schemes or re.search(r"[\s@?#\\\"'<>()\[\]]", value):
        raise BucketError(f"{name} must be a full address, like https://example.com.")
    return value


def clean(data: dict) -> dict:
    """Checked settings. BucketError says which one is wrong."""
    bucket = data["bucket"].strip()
    if not BUCKET_NAME.match(bucket):
        raise BucketError("That isn't a bucket name. Use the name alone, like my-uploads.")
    endpoint = clean_address(data["endpoint_url"], "The endpoint")
    # Cloudflare shows the endpoint with the bucket's name on the end.
    endpoint = endpoint.removesuffix(f"/{bucket}")
    if urlsplit(endpoint).path:
        raise BucketError("The endpoint is the address alone, without a folder after it.")
    # R2 calls its only region "auto". Most other providers want their own name.
    region = data["region"].strip() or "auto"
    if not REGION.match(region):
        raise BucketError("That isn't a region. It looks like eu-central-1; leave it empty for Cloudflare R2.")
    return {
        "endpoint_url": endpoint,
        "region": region,
        "bucket": bucket,
        "access_key_id": data["access_key_id"].strip(),
        "secret_access_key": data["secret_access_key"].strip(),
        "public_base_url": clean_address(data["public_base_url"], "The public address"),
    }


# --- Using it ---


def put(bucket: Bucket, name: str, content: bytes, content_type: str, download_as: str = "") -> None:
    """With `download_as`, opening its address saves it under that name instead of showing it."""
    headers = {"Content-Type": content_type, "Cache-Control": CACHE_FOREVER}
    if download_as:
        headers["Content-Disposition"] = f"attachment; filename*=UTF-8''{quote(download_as, safe='')}"
    response = send(bucket, "PUT", name, headers=headers, content=content)
    if response.status_code != 200:
        raise BucketError(refusal(bucket, response.status_code, "store files in"))


def delete(bucket: Bucket, name: str) -> None:
    response = send(bucket, "DELETE", name)
    # 404: already gone.
    if response.status_code not in (200, 204, 404):
        raise BucketError(refusal(bucket, response.status_code, "delete files from"))


def url(bucket: Bucket, name: str) -> str:
    return f"{bucket.public_base_url}/{name}"


def check(bucket: Bucket) -> None:
    """Writes a small file, opens its public address, and deletes it."""
    content = uuid.uuid4().hex
    name = f"{FOLDER}/check/{content}.txt"
    put(bucket, name, content.encode(), "text/plain")
    try:
        check_public(url(bucket, name), content)
    finally:
        # Also when it isn't public yet: leave nothing behind.
        delete(bucket, name)


def check_public(address: str, content: str) -> None:
    try:
        response = outbound.request("GET", address, timeout=TIMEOUT_SECONDS)
    except (outbound.BlockedAddress, httpx.HTTPError) as error:
        raise BucketError("Files are stored, but the public address can't be reached. Check it.") from error
    if response.status_code != 200 or response.content != content.encode():
        raise BucketError(
            f"Files are stored, but the public address answered {response.status_code} instead of showing one. "
            "Turn on public access for the bucket and check the address."
        )


# --- Requests ---


def send(bucket: Bucket, method: str, name: str, headers: dict | None = None, content: bytes = b"") -> httpx.Response:
    # Names are ours (whileisleep.folders): ids, words and random hex, so nothing to escape.
    request = AWSRequest(
        method=method,
        url=f"{bucket.endpoint_url}/{bucket.bucket}/{name}",
        headers=headers or {},
        data=content,
    )
    credentials = Credentials(bucket.access_key_id, bucket.secret_access_key)
    S3SigV4Auth(credentials, "s3", bucket.region).add_auth(request)
    try:
        return outbound.request(
            method, request.url, headers=dict(request.headers.items()), content=content, timeout=TIMEOUT_SECONDS
        )
    except outbound.BlockedAddress as error:
        raise BucketError("The endpoint is on a private network, which this server may not call.") from error
    except (httpx.HTTPError, UnicodeError) as error:
        raise BucketError("The endpoint can't be reached. Check the address.") from error


def refusal(bucket: Bucket, status: int, what: str) -> str:
    """Why the bucket said no, by its status alone: what it answered stays on the server."""
    if status in (401, 403):
        return f"The key may not {what} {bucket.bucket}. Check the key, the secret and its permissions."
    if status == 404:
        return f"There is no bucket called {bucket.bucket} at that endpoint."
    if status in (301, 307, 308, 400):
        return f"The bucket answered {status}. The endpoint or the region is probably wrong."
    return f"The bucket answered {status}. Try again in a minute."
