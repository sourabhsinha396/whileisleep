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
"""

import logging
import uuid
from contextlib import contextmanager

from celery import shared_task
from django.conf import settings
from django.core.cache import cache

from . import bot, openrouter

log = logging.getLogger(__name__)

# How often, and for how long, a job waits for another reply in the same conversation.
LOCK_RETRY_SECONDS = 2
LOCK_RETRIES = 120
# Seconds to wait before each new try after a model failure that may pass. After the last
# one, the fallback answers. Short: someone is waiting in the chat.
LLM_RETRY_DELAYS = (3, 10)


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
