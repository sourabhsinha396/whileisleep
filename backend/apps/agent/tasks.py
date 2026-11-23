"""Background jobs for the AI agent, run by the Celery worker.

`answer` is the AI stage of the reply pipeline (apps.agent.pipeline queues it). What the
queue adds over running it in the web process:

- A reply survives a restart: the job is acknowledged only when it finishes, so a worker
  that dies mid-reply leaves it on the queue for another.
- One reply at a time per conversation: a job waits while another holds the
  conversation's lock, and by the time it runs, the older pass has stepped aside for the
  newer message (see bot.superseded).
- A provider hiccup isn't the visitor's problem: a model call that fails in a way that
  may pass is tried again after a few seconds before the help center fallback answers.

`sweep_unanswered` is the safety net under all of it. The queue is Redis and the message is
Postgres, so there is a moment (the web process dying between saving a message and queueing
its job, or Redis losing its data) where a message exists with no job. Once a minute the
sweep finds visitor messages that nothing ever picked up and runs the pipeline for them.
"""

import logging
import uuid
from contextlib import contextmanager
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.cache import cache
from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.conversations.models import Message

from . import bot, openrouter
from .models import Turn

log = logging.getLogger(__name__)

# How often, and for how long, a job waits for another reply in the same conversation.
LOCK_RETRY_SECONDS = 2
LOCK_RETRIES = 120
# Seconds to wait before each new try after a model failure that may pass. After the last
# one, the fallback answers. Short: someone is waiting in the chat.
LLM_RETRY_DELAYS = (3, 10)
# The sweep looks at messages older than the first (anything younger may simply still be
# in progress: the longest reply, with its retries, fits inside it) and younger than the
# second (an answer hours late is worse than none; the team has the conversation by then).
SWEEP_AFTER = timedelta(minutes=6)
SWEEP_UNTIL = timedelta(minutes=30)
SWEEP_BATCH = 100


@contextmanager
def reply_lock(conversation_id: int):
    """Yields True if this job now holds the conversation's reply lock, False if another
    job does. The lock expires by itself (REPLY_LOCK_SECONDS), so a worker that dies while
    holding it can't block the conversation for long."""
    key = f"reply-lock:{conversation_id}"
    token = uuid.uuid4().hex
    # cache.add sets the key only if it is absent, atomically (SET NX on Redis).
    held = cache.add(key, token, timeout=settings.REPLY_LOCK_SECONDS)
    try:
        yield held
    finally:
        # Only our own lock: after an expiry the key may belong to a newer job.
        if held and cache.get(key) == token:
            cache.delete(key)


@shared_task(bind=True, max_retries=LOCK_RETRIES)
def answer(
    self,
    conversation_id: int,
    instruction: str = "",
    trigger_id: int | None = None,
    rule_id: int | None = None,
    attempt: int = 0,
):
    """Writes the AI's reply to one visitor message. `attempt` counts tries after model
    failures (0 is the first)."""
    arguments = (conversation_id, instruction, trigger_id, rule_id)
    tries_left = attempt < len(LLM_RETRY_DELAYS)
    with reply_lock(conversation_id) as held:
        if not held:
            # Another reply is being written for this conversation. Come back shortly; it
            # will have finished, or stepped aside for the message this job answers.
            raise self.retry(countdown=LOCK_RETRY_SECONDS)
        try:
            bot.reply(*arguments, retry_transient=tries_left)
            return
        except openrouter.OpenRouterError as error:
            # Only raised while tries are left (see bot.reply).
            log.warning("Model call failed on conversation %s, will try again: %s", conversation_id, error)
    # Outside the lock, so the next try (or a newer message's job) can take it.
    self.apply_async(args=arguments, kwargs={"attempt": attempt + 1}, countdown=LLM_RETRY_DELAYS[attempt])


def unanswered_messages():
    """Visitor messages the pipeline never finished with: no Turn was recorded for them,
    nothing was said after them, and the AI is still the one who should answer."""
    now = timezone.now()
    later = Message.objects.filter(conversation=OuterRef("conversation"), pk__gt=OuterRef("pk"), is_note=False)
    return (
        Message.objects.filter(
            sender=Message.Sender.VISITOR,
            created_at__gte=now - SWEEP_UNTIL,
            created_at__lte=now - SWEEP_AFTER,
            conversation__human_requested=False,
            conversation__workspace__ai_enabled=True,
        )
        .exclude(Exists(Turn.objects.filter(trigger=OuterRef("pk"))))
        .exclude(Exists(later))
        .select_related("conversation__workspace__organization", "conversation__visitor")
        .order_by("id")[:SWEEP_BATCH]
    )


@shared_task
def sweep_unanswered() -> int:
    """Runs the pipeline for messages that slipped through. Returns how many."""
    # Imported here: the pipeline imports this module to queue `answer`.
    from . import pipeline

    count = 0
    for message in unanswered_messages():
        log.warning(
            "Message %s in conversation %s was never answered; running it now.", message.pk, message.conversation_id
        )
        pipeline.handle(message.conversation, message)
        count += 1
    return count
