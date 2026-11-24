"""Background jobs for integrations, run by the Celery worker."""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from whileisleep.locks import cache_lock

from . import deliveries, registry
from .models import Delivery
from .plugin import PluginError

log = logging.getLogger(__name__)

# A conversation's events go out one at a time, so a second job waits for the first.
LOCK_SECONDS = 180
LOCK_RETRY_SECONDS = 2
LOCK_RETRIES = 60
# The sweep leaves alone what a job is probably just about to send.
SWEEP_AFTER = timedelta(minutes=1)
KEEP_FAILED = timedelta(days=14)
# Seconds before each new try at something a service sent us.
HANDLE_DELAYS = (5, 30, 120)


@shared_task(bind=True, max_retries=LOCK_RETRIES)
def deliver(self, integration_id: int, conversation_id: int) -> None:
    with cache_lock(f"deliver:{integration_id}:{conversation_id}", LOCK_SECONDS) as held:
        if not held:
            raise self.retry(countdown=LOCK_RETRY_SECONDS)
        wait = deliveries.send_pending(integration_id, conversation_id)
    if wait is not None:
        # Outside the lock, so that job can take it. A second late, so it is due by then.
        deliveries.send_later(integration_id, conversation_id, countdown=wait + 1)


@shared_task
def sweep_deliveries() -> int:
    """Sends what no job is coming for (the queue lost it) and forgets old failures."""
    now = timezone.now()
    Delivery.objects.filter(status=Delivery.Status.FAILED, created_at__lt=now - KEEP_FAILED).delete()
    due = Delivery.objects.filter(status=Delivery.Status.PENDING, due_at__lt=now - SWEEP_AFTER)
    pairs = set(due.values_list("integration_id", "conversation_id")[:500])
    for integration_id, conversation_id in pairs:
        deliveries.send_later(integration_id, conversation_id)
    return len(pairs)


@shared_task
def handle(plugin_id: str, payload: dict, attempt: int = 0) -> None:
    """Does what a service's webhook asked for."""
    plugin = registry.get(plugin_id)
    if plugin is None:
        return
    try:
        plugin.handle(payload)
    except PluginError as error:
        if not error.retry or attempt >= len(HANDLE_DELAYS):
            log.warning("Plugin %s gave up on a webhook: %s", plugin_id, error)
            return
        handle.apply_async(args=(plugin_id, payload, attempt + 1), countdown=HANDLE_DELAYS[attempt])
