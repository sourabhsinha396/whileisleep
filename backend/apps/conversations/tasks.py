"""Background jobs for conversations."""

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from .models import Attachment

UNSENT_AFTER = timedelta(days=1)


@shared_task
def delete_unsent_files() -> int:
    """Files that were uploaded into a message box and never sent."""
    unsent = Attachment.objects.filter(message=None, created_at__lt=timezone.now() - UNSENT_AFTER)
    count = unsent.count()
    # Each one's file is deleted too (models.delete_attachment_file).
    unsent.delete()
    return count
