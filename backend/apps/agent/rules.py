"""Runs a workspace's rules on a new visitor message, before the AI.

The first enabled rule (by position) whose conditions all hold wins. Its actions run in
code: tag, hand off, send a fixed reply (then the AI stays quiet for this message), or
hand the AI an extra instruction for this message only.
"""

import re
from dataclasses import dataclass

from django.db.models import F
from django.utils import timezone

from apps.conversations.models import Conversation, Message
from apps.conversations.services import add_message

from .bot import request_human
from .models import Rule

PLACEHOLDER = re.compile(r"\{(visitor\.(?:name|email)|data\.[A-Za-z0-9_]{1,40})\}")
# Intent data comes from the visitor's browser; keep what lands in a reply short and plain.
MAX_DATA_VALUE = 120


@dataclass
class Outcome:
    rule: Rule | None = None
    # A fixed reply went out, so the AI shouldn't answer this message.
    replied: bool = False
    # That fixed reply.
    message: Message | None = None
    # Extra instruction for the AI's answer to this message.
    instruction: str = ""


def has_conditions(rule: Rule) -> bool:
    return bool(rule.intent or rule.keyword_list or rule.page_contains or rule.first_message_only)


def matches(rule: Rule, message: Message, is_first: bool) -> bool:
    # A rule with no conditions would fire on every message; the API refuses those too.
    if not has_conditions(rule):
        return False
    if rule.intent and rule.intent != message.intent:
        return False
    if rule.keyword_list and not any(k in message.body.lower() for k in rule.keyword_list):
        return False
    if rule.page_contains and rule.page_contains.lower() not in message.conversation.visitor.current_url.lower():
        return False
    if rule.first_message_only and not is_first:
        return False
    return True


def plain(value) -> str:
    return " ".join(str(value).split())[:MAX_DATA_VALUE]


def fill(template: str, message: Message) -> str:
    visitor = message.conversation.visitor
    data = message.intent_data if isinstance(message.intent_data, dict) else {}

    def value(match: re.Match) -> str:
        key = match.group(1)
        if key == "visitor.name":
            return visitor.name
        if key == "visitor.email":
            return visitor.email
        return plain(data.get(key.removeprefix("data."), ""))

    return PLACEHOLDER.sub(value, template).strip()


def apply(conversation: Conversation, message: Message) -> Outcome:
    is_first = not conversation.messages.filter(sender=Message.Sender.VISITOR).exclude(pk=message.pk).exists()
    for rule in Rule.objects.filter(workspace=conversation.workspace, enabled=True):
        if conversation.human_requested and not rule.also_when_human:
            continue
        if matches(rule, message, is_first):
            return run(rule, conversation, message)
    return Outcome()


def run(rule: Rule, conversation: Conversation, message: Message) -> Outcome:
    Rule.objects.filter(pk=rule.pk).update(match_count=F("match_count") + 1, last_matched_at=timezone.now())
    add_message(conversation, Message.Sender.SYSTEM, f"Rule matched: {rule.name}", is_note=True)
    if rule.tag and rule.tag not in conversation.tags:
        conversation.tags = [*conversation.tags, rule.tag]
        conversation.save(update_fields=["tags"])
    if rule.handoff:
        request_human(conversation, f"rule {rule.name}")
    if rule.reply.strip():
        sent = add_message(conversation, Message.Sender.BOT, fill(rule.reply, message))
        return Outcome(rule=rule, replied=True, message=sent)
    return Outcome(rule=rule, instruction=fill(rule.ai_instruction, message))
