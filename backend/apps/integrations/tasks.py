"""Background jobs for integrations.

They wait on outside services, so they have their own queues and worker (settings.CELERY_TASK_ROUTES,
docker-compose.yaml): however slow a service is, AI replies have their threads. Two queues, so
events going out can't hold up what people wait for: their replies from the service, and the dashboard.

Among themselves, deliveries may use only some of the worker's threads, and one integration only a few
of those. A job that finds no room gives its thread back and comes again.
"""

import json
import logging
import threading
from contextlib import contextmanager
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from whileisleep import encryption
from whileisleep.locks import cache_lock

from . import deliveries, jobs, registry
from .models import Delivery, Integration
from .plugin import PluginError

log = logging.getLogger(__name__)

# A conversation's events go out one at a time, so a second job waits for the first.
LOCK_SECONDS = 180
COME_AGAIN_SECONDS = 3
# After this many tries the sweep takes over.
COME_AGAIN_TIMES = 20
# Deliveries of one integration at once, over all workers.
PER_INTEGRATION = 2
# The sweep leaves alone what a job is probably just about to send.
SWEEP_AFTER = timedelta(minutes=1)
# What was given up on, and what plugins keep in their log.
KEEP = timedelta(days=7)
# Seconds before each new try at something a service sent us.
HANDLE_DELAYS = (5, 30, 120)

# This process's threads that may be delivering.
delivering = threading.BoundedSemaphore(settings.DELIVERY_THREADS)


@contextmanager
def room(integration_id: int):
    """Yields whether there is room to deliver for this integration now. Never waits."""
    if not delivering.acquire(blocking=False):
        yield False
        return
    try:
        for number in range(PER_INTEGRATION):
            with cache_lock(f"deliveries-of:{integration_id}:{number}", LOCK_SECONDS) as held:
                if held:
                    yield True
                    return
        yield False
    finally:
        delivering.release()


@shared_task(bind=True, max_retries=None)
def deliver(self, integration_id: int, conversation_id: int) -> None:
    wait, done = None, False
    with room(integration_id) as free:
        if free:
            with cache_lock(f"deliver:{integration_id}:{conversation_id}", LOCK_SECONDS) as held:
                if held:
                    wait, done = deliveries.send_pending(integration_id, conversation_id), True
    if not done:
        if self.request.retries < COME_AGAIN_TIMES:
            raise self.retry(countdown=COME_AGAIN_SECONDS)
        return
    if wait is not None:
        # Outside the lock, so that job can take it. A second late, so it is due by then.
        deliveries.send_later(integration_id, conversation_id, countdown=wait + 1)


@shared_task
def sweep_deliveries() -> int:
    """Sends what no job is coming for (the queue lost it) and forgets what is old."""
    now = timezone.now()
    Delivery.objects.exclude(status=Delivery.Status.PENDING).filter(created_at__lt=now - KEEP).delete()
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


@shared_task
def run_job(job_id: str, sealed: str) -> None:
    """Does what the dashboard asked for (apps.integrations.jobs)."""
    jobs.run(job_id, sealed)


@shared_task
def say_goodbye(plugin_id: str, sealed: str) -> None:
    """Tells a service that a workspace disconnected. The Integration is gone already."""
    plugin, row = registry.get(plugin_id), json.loads(encryption.decrypt(sealed) or "null")
    if plugin is None or row is None:
        return
    try:
        plugin.disconnect(Integration(plugin=plugin_id, **row))
    except Exception as error:
        log.warning("Disconnecting from %s: %s", plugin_id, error)
