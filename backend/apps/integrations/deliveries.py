"""Events on their way out.

`listen` runs where an event happens. It asks each connected plugin whether it wants the event and
writes a Delivery, which a worker sends (tasks.deliver). So a service that is slow or down never
holds up a chat, and nothing is lost if the queue is: a sweep finds what is still pending.
"""

import logging
import time
from datetime import timedelta
from functools import partial

from django.db import transaction
from django.dispatch import receiver
from django.utils import timezone

from apps.conversations.signals import MESSAGE, Event, happened

from . import registry
from .models import Delivery, Integration
from .plugin import PluginError

log = logging.getLogger(__name__)

# Seconds before each new try.
RETRY_DELAYS = (10, 60, 300, 1800, 7200)
# How long one job sends before it lets others have the thread.
TURN_SECONDS = 20


@receiver(happened)
def listen(sender, event: Event, **kwargs) -> None:
    for integration in Integration.objects.filter(workspace_id=event.conversation.workspace_id):
        if event.name == MESSAGE and event.origin == integration.origin:
            # It told us.
            continue
        plugin = registry.get(integration.plugin)
        if plugin is None or not plugin.available or not wants(plugin, integration, event):
            continue
        Delivery.objects.create(
            integration=integration,
            conversation=event.conversation,
            event=event.name,
            message=event.message,
            by=event.by,
            data=event.data,
        )
        transaction.on_commit(partial(send_later, integration.pk, event.conversation.pk))


def wants(plugin, integration: Integration, event: Event) -> bool:
    try:
        return plugin.wants(integration, event)
    except Exception:
        # A plugin's mistake must not break the chat.
        log.exception("Plugin %s failed on %s", plugin.id, event.name)
        return False


def send_later(integration_id: int, conversation_id: int, countdown: int = 0) -> None:
    from . import tasks

    try:
        tasks.deliver.apply_async(args=(integration_id, conversation_id), countdown=countdown)
    except Exception:
        # The queue is down: the sweep will send it. The visitor's message is already saved.
        log.exception("Could not queue deliveries of conversation %s", conversation_id)


def send_pending(integration_id: int, conversation_id: int) -> int | None:
    """Sends a conversation's pending events, oldest first. After one that should be tried again
    the rest wait behind it: returns in how many seconds. Also returns when its turn is over."""
    ends = time.monotonic() + TURN_SECONDS
    while True:
        delivery = (
            Delivery.objects.filter(
                integration_id=integration_id, conversation_id=conversation_id, status=Delivery.Status.PENDING
            )
            .select_related(
                "integration__workspace", "conversation__visitor", "conversation__workspace", "message", "by"
            )
            .order_by("id")
            .first()
        )
        if delivery is None or delivery.due_at > timezone.now():
            return None
        wait = send(delivery)
        if wait is not None:
            return wait
        if time.monotonic() > ends:
            return 0


def send(delivery: Delivery) -> int | None:
    integration = delivery.integration
    plugin = registry.get(integration.plugin)
    if plugin is None or not plugin.available:
        # Taken off this server since.
        delivery.delete()
        return None
    event = Event(
        delivery.event,
        delivery.conversation,
        message=delivery.message,
        by=delivery.by,
        data=delivery.data,
        id=str(delivery.pk),
        at=delivery.created_at,
    )
    try:
        detail = plugin.deliver(integration, event)
    except PluginError as error:
        return failed(delivery, str(error), error.retry, error.after)
    except Exception:
        log.exception("Plugin %s failed to deliver %s", plugin.id, delivery.event)
        return failed(delivery, f"{plugin.name} failed unexpectedly. The server's log says why.", retry=True)
    if plugin.keeps_log:
        delivery.status, delivery.detail = Delivery.Status.SENT, detail or ""
        delivery.save(update_fields=["status", "detail"])
    else:
        delivery.delete()
    if integration.last_error:
        Integration.objects.filter(pk=integration.pk).update(last_error="")
    return None


def failed(delivery: Delivery, error: str, retry: bool, after: int | None = None) -> int | None:
    delivery.attempts += 1
    delivery.detail = error
    if retry and delivery.attempts <= len(RETRY_DELAYS):
        # A busy service says when; never sooner than that, nor later than our longest wait.
        wait = min(max(RETRY_DELAYS[delivery.attempts - 1], after or 0), RETRY_DELAYS[-1])
        delivery.due_at = timezone.now() + timedelta(seconds=wait)
        delivery.save(update_fields=["attempts", "detail", "due_at"])
        return wait
    delivery.status = Delivery.Status.FAILED
    delivery.save(update_fields=["attempts", "detail", "status"])
    Integration.objects.filter(pk=delivery.integration_id).update(last_error=error)
    return None
