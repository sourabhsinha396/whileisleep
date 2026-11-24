"""Background jobs for help articles."""

import logging

from celery import shared_task

from apps.workspaces import buckets
from apps.workspaces.models import Bucket

logger = logging.getLogger(__name__)


@shared_task
def delete_from_bucket(bucket_id: int, name: str) -> None:
    """Deletes a file from a customer's bucket. In the background, because an article can have
    many pictures and their bucket can be slow. A failure leaves an unused file behind."""
    bucket = Bucket.objects.filter(pk=bucket_id).first()
    if bucket is None:
        return  # Disconnected meanwhile: no longer ours to touch.
    try:
        buckets.delete(bucket, name)
    except buckets.BucketError as error:
        logger.warning("Could not delete %s from a customer's bucket: %s", name, error)
