"""Where uploaded files go: an S3-compatible bucket (Cloudflare R2, Hetzner, MinIO, AWS...).

Code uses Django's `default_storage` and never talks to S3 itself.

The bucket is public: anyone can read a file at STORAGE_PUBLIC_BASE_URL if they know its
name. Keep anything private (backups, exports) out of it.
"""

from collections.abc import Mapping
from urllib.parse import urlsplit

from botocore.config import Config
from django.core.exceptions import ImproperlyConfigured

REQUIRED = (
    "S3_ENDPOINT_URL",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
    "STORAGE_BUCKET",
    "STORAGE_PUBLIC_BASE_URL",
)


def default_storage_config(env: Mapping[str, str]) -> dict:
    """STORAGES["default"] for this environment: the bucket, or the local disk when none of
    the settings are there. Some but not all of them is a mistake and stops startup."""
    values = {name: env.get(name, "").strip() for name in REQUIRED}
    missing = [name for name, value in values.items() if not value]
    if len(missing) == len(REQUIRED):
        return {"BACKEND": "django.core.files.storage.FileSystemStorage"}
    if missing:
        raise ImproperlyConfigured(f"File storage is half configured. Also set: {', '.join(missing)}.")

    public = urlsplit(values["STORAGE_PUBLIC_BASE_URL"])
    if public.scheme not in ("https", "http") or not public.netloc:
        raise ImproperlyConfigured("STORAGE_PUBLIC_BASE_URL must be a full address, like https://cdn.example.com.")
    return {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "endpoint_url": values["S3_ENDPOINT_URL"],
            "access_key": values["S3_ACCESS_KEY_ID"],
            "secret_key": values["S3_SECRET_ACCESS_KEY"],
            "bucket_name": values["STORAGE_BUCKET"],
            # R2 calls its only region "auto". Most other providers want their own name.
            "region_name": env.get("S3_REGION", "").strip() or "auto",
            # Links to the public address, unsigned, so they can be cached and never expire.
            "url_protocol": f"{public.scheme}:",
            "custom_domain": public.netloc + public.path.rstrip("/"),
            "querystring_auth": False,
            # A second file with the same name gets another name instead of replacing the first.
            "file_overwrite": False,
            # File names are random and never reused (whileisleep.folders).
            "object_parameters": {"CacheControl": "public, max-age=31536000, immutable"},
            "client_config": Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                # Newer boto3 adds AWS-only checksums that some other providers reject.
                request_checksum_calculation="when_required",
                response_checksum_validation="when_required",
                # A request waits on this: fail fast rather than hold a thread for minutes.
                connect_timeout=5,
                read_timeout=30,
                retries={"total_max_attempts": 2},
            ),
        },
    }
