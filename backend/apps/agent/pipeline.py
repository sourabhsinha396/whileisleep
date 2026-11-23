"""The reply pipeline: everything that happens after a visitor message is stored.

A message is answered by the cheapest stage that can answer it, and each pass is recorded as
a Turn that says which stage that was:

1. Rules run in code. A rule with a fixed reply answers on its own (Stage.RULE): no model
   call, the same answer every time. Other rule actions (tag, hand-off, an instruction for
   the AI) still apply and the message moves on.
2. If the AI is off or a person has the conversation, nothing replies (Stage.NONE).
3. Limits: past the daily AI cap the conversation goes to a person (Stage.GUARD).
4. The AI answers (Stage.AI), or a help center search does when the model is unavailable
   (Stage.FALLBACK). See apps.agent.bot.

Stages 1-3 are fast and run inside the request. The AI stage is slow, so it runs apart from
the request (a thread today; tests run it inline with BOT_SYNC).

People often send a thought as two or three quick messages. The AI stage waits a moment
before starting (REPLY_DEBOUNCE_SECONDS), and a pass whose message is no longer the newest
steps aside (Stage.SUPERSEDED), so the burst gets one answer that has read all of it.
"""

import logging
import threading
import time

from django.conf import settings
from django.db import close_old_connections

from apps.conversations import limits
from apps.conversations.models import Conversation, Message
from apps.conversations.services import add_message

from . import bot, rules
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

    if conversation.workspace.organization.llm_ready and not limits.allow_ai_reply(conversation):
        # Daily AI cap reached for this visitor or workspace: a person takes it from here.
        bot.request_human(conversation, "daily AI reply limit reached")
        sent = add_message(conversation, Message.Sender.BOT, "Thanks! A teammate will reply here soon.")
        recorder.finish(Turn.Stage.GUARD, reply=sent, rule=rule)
        return

    answer_later(conversation.pk, instruction, message.pk, rule.pk if rule else None)


def answer_later(conversation_id: int, instruction: str, trigger_id: int, rule_id: int | None) -> None:
    """Starts the AI stage without making the visitor's request wait for it."""
    arguments = (conversation_id, instruction, trigger_id, rule_id)
    if settings.BOT_SYNC:
        bot.reply(*arguments)
    else:
        threading.Thread(target=_answer_in_thread, args=arguments, daemon=True).start()


def _answer_in_thread(conversation_id: int, *arguments) -> None:
    try:
        time.sleep(settings.REPLY_DEBOUNCE_SECONDS)
        bot.reply(conversation_id, *arguments)
    except Exception:
        log.exception("The AI stage failed on conversation %s", conversation_id)
    finally:
        close_old_connections()
