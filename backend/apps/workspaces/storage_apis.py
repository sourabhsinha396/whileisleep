"""The organization's own bucket, for the images in its articles and the files in its chats.
Optional: without one, both are text.

Only the organization's owner reaches these. Both halves of the key are write-only.
"""

from django.db import transaction
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.security import token_auth

from . import buckets
from .models import Bucket, Organization
from .schemas import StorageIn, StorageOut
from .services import organization_for

router = Router(tags=["organization"], auth=token_auth)


def storage_out(organization: Organization) -> dict:
    bucket = organization.storage_bucket
    if bucket is None:
        return {"connected": False}
    return {
        "connected": True,
        "endpoint_url": bucket.endpoint_url,
        "region": bucket.region,
        "bucket": bucket.bucket,
        "key_hint": bucket.key_hint,
        "public_base_url": bucket.public_base_url,
        "image_count": bucket.article_images.count(),
        "file_count": bucket.attachments.count(),
    }


@router.get("/organization/storage", response=StorageOut)
def get(request):
    return storage_out(organization_for(request.auth))


@router.put("/organization/storage", response=StorageOut)
def connect(request, payload: StorageIn):
    """Tries the bucket and saves it. One that doesn't work is not saved."""
    organization = organization_for(request.auth)
    current = organization.storage_bucket
    try:
        fields = buckets.clean(payload.dict())
        fields |= keys(current, fields)
        buckets.check(Bucket(organization=organization, **fields))
    except buckets.BucketError as error:
        raise HttpError(400, str(error)) from error

    with transaction.atomic():
        same = current and (current.endpoint_url, current.bucket) == (fields["endpoint_url"], fields["bucket"])
        if current and not same:
            # The images in it stay there, but this key is no longer ours to delete them with.
            current.delete()
        Bucket.objects.update_or_create(organization=organization, defaults=fields)
    return storage_out(Organization.objects.get(pk=organization.pk))


def keys(current: Bucket | None, fields: dict) -> dict:
    """The typed key, or the saved one when both halves are left empty. A saved key is only
    for the endpoint it was saved with."""
    typed = {name: fields[name] for name in ("access_key_id", "secret_access_key")}
    if all(typed.values()):
        return typed
    if any(typed.values()) or current is None:
        raise buckets.BucketError("Enter both the access key ID and the secret access key.")
    if current.endpoint_url != fields["endpoint_url"]:
        raise buckets.BucketError("The endpoint changed, so enter the access key ID and the secret again.")
    return {name: getattr(current, name) for name in typed}


@router.delete("/organization/storage", response=StorageOut)
def disconnect(request):
    """Forgets the bucket. Its files stay in it, and articles keep showing them."""
    organization = organization_for(request.auth)
    Bucket.objects.filter(organization=organization).delete()
    return {"connected": False}
