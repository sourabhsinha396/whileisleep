"""The reply pipeline: everything that happens after a visitor message is stored.

A message is answered by the cheapest stage that can answer it, and each pass is recorded as
a Turn that says which stage that was:

1. Rules run in code. A rule with a fixed reply answers on its own (Stage.RULE): no model
   call, the same answer every time. Other rule actions (tag, hand-off, an instruction for
   the AI) still apply and the message moves on.
2. If the AI is off or a person has the conversation, nothing replies (Stage.NONE).
3. Limits: past the daily AI cap, or when the trial is over and nobody pays, the
   conversation goes to a person (Stage.GUARD).
4. The AI answers (Stage.AI), or a help center search does when the model is unavailable
   (Stage.FALLBACK). See apps.agent.bot.

Stages 1-3 are fast and run inside the request. The AI stage is slow, so it is queued as
a Celery task (apps.agent.tasks.answer) and a worker runs it.

People often send a thought as two or three quick messages. The task is queued with a
short delay (REPLY_DEBOUNCE_SECONDS), and a pass whose message is no longer the newest
steps aside (Stage.SUPERSEDED), so the burst gets one answer that has read all of it.
"""

import logging

from django.conf import settings
from django.db import transaction

from apps.billing import services as billing
from apps.conversations import limits
from apps.conversations.models import Conversation, Message
from apps.conversations.services import add_message

from . import bot, rules, tasks
from .models import Rule, Turn
from .turns import Recorder

log = logging.getLogger(__name__)


def handle(conversation: Conversation, message: Message, instruction: str = "", run_rules: bool = True) -> None:
    """Runs the pipeline for a visitor message that was just saved.

    `instruction` is extra guidance for the AI's answer to this message only (a form the AI
    showed came back). `run_rules=False` skips stage 1, for messages that continue something
    a rule or the AI already started.
    """
    recorder = Recorder(conversation, message)
    rule: Rule | None = None
    if run_rules:
        outcome = rules.apply(conversation, message)
        rule = outcome.rule
        if outcome.replied:
            recorder.finish(Turn.Stage.RULE, reply=outcome.message, rule=rule)
            return
        instruction = outcome.instruction or instruction

    if not bot.will_reply(conversation):
        recorder.finish(Turn.Stage.NONE, rule=rule)
        return

    if blocked := why_blocked(conversation):
        # A person takes it from here.
        bot.request_human(conversation, blocked)
        sent = add_message(conversation, Message.Sender.BOT, "Thanks! A teammate will reply here soon.")
        recorder.finish(Turn.Stage.GUARD, reply=sent, rule=rule)
        return

    answer_later(conversation.pk, instruction, message.pk, rule.pk if rule else None)


def why_blocked(conversation: Conversation) -> str:
    """Why the AI may not answer this conversation now, for the team to read. Empty: it may."""
    organization = conversation.workspace.organization
    if not billing.ai_allowed(organization):
        return "the AI is paused until a plan is active (Settings › Billing)"
    if organization.llm_ready and not limits.allow_ai_reply(conversation):
        return "daily AI reply limit reached"
    return ""


def answer_later(conversation_id: int, instruction: str, trigger_id: int, rule_id: int | None) -> None:
    """Queues the AI stage, so the visitor's request doesn't wait for it.

    Queued only once the surrounding database transaction commits: a worker that picked the
    job up sooner wouldn't find the visitor's message yet.
    """
    arguments = (conversation_id, instruction, trigger_id, rule_id)
    transaction.on_commit(lambda: tasks.answer.apply_async(args=arguments, countdown=settings.REPLY_DEBOUNCE_SECONDS))
