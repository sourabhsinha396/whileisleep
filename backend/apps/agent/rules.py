"""Rules: decisions made in code, before (or instead of) the AI.

On each visitor message the first enabled rule, by position, whose conditions hold wins,
and its actions run in order:

    {"type": "tag", "value": "refund"}
    {"type": "set_attribute", "scope": "conversation", "key": "topic", "value": "billing"}
    {"type": "handoff"}
    {"type": "reply", "text": "We're open 9 to 5, {contact.name}."}   the AI stays quiet
    {"type": "instruct", "text": "Offer the annual plan."}            for this answer only

Conditions are a tree (apps.agent.conditions) over the facts `context_for` gathers: the
message, the page, the visitor's and the conversation's attributes, and the local time.
No model is involved, so a rule gives the same answer every time and costs nothing.
"""

import re
from dataclasses import dataclass
from zoneinfo import ZoneInfo

from django.db.models import F
from django.utils import timezone

from apps.conversations import attributes
from apps.conversations.models import Conversation, Message
from apps.conversations.services import add_message

from . import conditions
from .bot import request_human
from .models import Rule

# What a condition may look at. `message.data.KEY`, `contact.KEY` and `conversation.KEY`
# take any key; the others are the fixed names listed in context_for.
NAMESPACES = ("message", "page", "contact", "conversation", "time")
ACTION_TYPES = ("reply", "instruct", "tag", "set_attribute", "handoff")
MAX_ACTIONS = 10
MAX_TEXT = 4000
MAX_TAG = 40
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

PLACEHOLDER = re.compile(r"\{([a-z]+\.[A-Za-z0-9_.]{1,80})\}")
# Names rules used before attributes existed, kept so their text still fills in.
LEGACY_PLACEHOLDERS = {"visitor.": "contact.", "data.": "message.data."}
# Values from the visitor's browser land in replies; keep them short and on one line.
MAX_FILLED_VALUE = 120


class InvalidRule(ValueError):
    """The rule can't be saved. The message is safe to show its author."""


@dataclass
class Outcome:
    rule: Rule | None = None
    # A fixed reply went out, so the AI shouldn't answer this message.
    replied: bool = False
    # That fixed reply.
    message: Message | None = None
    # Extra instruction for the AI's answer to this message.
    instruction: str = ""


# --- Facts ---


def context_for(conversation: Conversation, message: Message, is_first: bool, at=None) -> dict:
    """Everything a condition or a reply template can refer to, by dotted name."""
    visitor = conversation.visitor
    local = (at or timezone.now()).astimezone(ZoneInfo(conversation.workspace.timezone))
    data = message.intent_data if isinstance(message.intent_data, dict) else {}
    return {
        **attributes.flat(conversation),
        "contact.verified": visitor.is_verified,
        "conversation.tags": list(conversation.tags or []),
        "conversation.has_human": conversation.human_requested,
        "message.text": message.body,
        "message.intent": message.intent,
        "message.is_first": is_first,
        **{f"message.data.{key}": value for key, value in data.items()},
        "page.url": visitor.current_url,
        "page.title": visitor.page_title,
        "page.referrer": visitor.referrer,
        # In the workspace's timezone, for office-hours rules.
        "time.hour": local.hour,
        "time.weekday": WEEKDAYS[local.weekday()],
    }


def is_first_message(conversation: Conversation, message: Message) -> bool:
    return not conversation.messages.filter(sender=Message.Sender.VISITOR, pk__lt=message.pk).exists()


# --- Checking a rule before it is saved ---


def validate(rule_conditions, actions) -> None:
    """Raises InvalidRule unless the conditions and actions make a rule that can run."""
    try:
        conditions.validate(rule_conditions)
    except conditions.InvalidCondition as error:
        raise InvalidRule(str(error)) from error
    for field in conditions.fields(rule_conditions):
        if field.split(".", 1)[0] not in NAMESPACES:
            raise InvalidRule(f"Unknown field {field}. Fields start with {', '.join(NAMESPACES)}.")

    if not isinstance(actions, list) or not actions:
        raise InvalidRule("Set at least one action.")
    if len(actions) > MAX_ACTIONS:
        raise InvalidRule(f"A rule can have at most {MAX_ACTIONS} actions.")
    for action in actions:
        validate_action(action)
    kinds = [action["type"] for action in actions]
    if "reply" in kinds and "instruct" in kinds:
        raise InvalidRule("Use a fixed reply or an AI instruction, not both.")
    for kind in ("reply", "instruct", "handoff"):
        if kinds.count(kind) > 1:
            raise InvalidRule(f"A rule can have only one {kind} action.")


def validate_action(action) -> None:
    if not isinstance(action, dict) or action.get("type") not in ACTION_TYPES:
        raise InvalidRule(f"An action needs a type: {', '.join(ACTION_TYPES)}.")
    kind = action["type"]
    if kind in ("reply", "instruct"):
        text = action.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > MAX_TEXT:
            raise InvalidRule(f"A {kind} action needs text (at most {MAX_TEXT} characters).")
    elif kind == "tag":
        value = action.get("value")
        if not isinstance(value, str) or not value.strip() or len(value.strip()) > MAX_TAG:
            raise InvalidRule(f"A tag action needs a tag (at most {MAX_TAG} characters).")
    elif kind == "set_attribute":
        if action.get("scope") not in ("contact", "conversation"):
            raise InvalidRule('A set_attribute action needs a scope: "contact" or "conversation".')
        key = action.get("key")
        if not isinstance(key, str) or not attributes.KEY.match(key):
            raise InvalidRule("Attribute names are lowercase letters, digits and underscores.")
        if attributes.clean(key, action.get("value")) is None:
            raise InvalidRule(f"The value for {key} can't be stored as an attribute.")


# --- Running ---


def matches(rule: Rule, context: dict) -> bool:
    return conditions.evaluate(rule.conditions, context)


def apply(conversation: Conversation, message: Message) -> Outcome:
    """Runs the first matching rule's actions. Outcome() when none matches."""
    context = None
    for rule in Rule.objects.filter(workspace=conversation.workspace, enabled=True):
        if conversation.human_requested and not rule.also_when_human:
            continue
        if context is None:
            # Built once, and only when there is a rule to check.
            context = context_for(conversation, message, is_first_message(conversation, message))
        if matches(rule, context):
            return run(rule, conversation, context)
    return Outcome()


def run(rule: Rule, conversation: Conversation, context: dict) -> Outcome:
    Rule.objects.filter(pk=rule.pk).update(match_count=F("match_count") + 1, last_matched_at=timezone.now())
    add_message(conversation, Message.Sender.SYSTEM, f"Rule matched: {rule.name}", is_note=True)
    outcome = Outcome(rule=rule)
    for action in rule.actions:
        kind = action["type"]
        if kind == "tag":
            tag = action["value"].strip()
            if tag not in conversation.tags:
                conversation.tags = [*conversation.tags, tag]
                conversation.save(update_fields=["tags"])
        elif kind == "set_attribute":
            target = conversation if action["scope"] == "conversation" else conversation.visitor
            attributes.set_attribute(target, action["key"], action["value"], attributes.Source.RULE)
        elif kind == "handoff":
            request_human(conversation, f"rule {rule.name}")
        elif kind == "reply":
            outcome.message = add_message(conversation, Message.Sender.BOT, fill(action["text"], context))
            outcome.replied = True
        elif kind == "instruct":
            outcome.instruction = fill(action["text"], context)
    return outcome


def fill(template: str, context: dict) -> str:
    """Fills {contact.name}, {conversation.topic}, {message.data.exam_name}... from the facts.

    A known kind of placeholder with no value becomes empty; anything else in braces is left
    alone (it is probably meant literally).
    """

    def value(match: re.Match) -> str:
        name = match.group(1)
        for old, new in LEGACY_PLACEHOLDERS.items():
            if name.startswith(old):
                name = new + name.removeprefix(old)
        if name.split(".", 1)[0] not in NAMESPACES:
            return match.group(0)
        found = context.get(name, "")
        if isinstance(found, list):
            found = ", ".join(map(str, found))
        return " ".join(str(found).split())[:MAX_FILLED_VALUE]

    return PLACEHOLDER.sub(value, template).strip()


# --- Trying a rule on past messages ---


def backtest(workspace, rule_conditions: dict, limit: int = 500, samples: int = 10) -> dict:
    """How often these conditions would have matched the workspace's recent visitor messages.

    Free to run: conditions are code. Two approximations, since history isn't replayed:
    attributes, tags and the page are today's (not what they were when the message came), and
    rules that would have matched earlier in the order aren't taken into account.
    """
    messages = (
        Message.objects.filter(conversation__workspace=workspace, sender=Message.Sender.VISITOR)
        .select_related("conversation__visitor", "conversation__workspace")
        .order_by("-id")[:limit]
    )
    checked, matched, examples = 0, 0, []
    first_ids: dict[int, int] = {}
    for message in messages:
        conversation = message.conversation
        if conversation.pk not in first_ids:
            first = conversation.messages.filter(sender=Message.Sender.VISITOR).order_by("id").values_list("pk")
            first_ids[conversation.pk] = first[0][0]
        is_first = first_ids[conversation.pk] == message.pk
        context = context_for(conversation, message, is_first, at=message.created_at)
        checked += 1
        if conditions.evaluate(rule_conditions, context):
            matched += 1
            if len(examples) < samples:
                examples.append(
                    {
                        "message_id": message.pk,
                        "conversation_id": conversation.pk,
                        "text": message.body[:200],
                        "created_at": message.created_at,
                    }
                )
    return {"checked": checked, "matched": matched, "samples": examples}
