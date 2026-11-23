"""Attributes: what we know about a visitor or about one conversation, as named values.

Two scopes:

- a visitor's attributes last across conversations (email, phone, plan);
- a conversation's attributes last for that conversation (order_number, topic).

Every value remembers its *source*: who said so. That matters because not every source can
be believed equally. An email the visitor typed is fine for "we'll notify you there", but
it must not unlock a tool that returns that person's orders; only a value the host site's
server signed (Source.VERIFIED) can. A less trusted source never overwrites a more trusted
one, so a visitor (or the AI) can't replace a verified email with someone else's.

Stored on `Visitor.attributes` / `Conversation.attributes` as
{"plan": {"value": "pro", "source": "verified"}}. A visitor's name and email are also kept
in their own columns, for lists and search; write them through here so both stay in step.

Rules, reply templates, tool parameters and the AI's "what we know" block all read
attributes through `flat()`, as `contact.plan` and `conversation.order_number`.
"""

import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import models

KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MAX_VALUE_CHARS = 300
MAX_KEYS = 50
# Visitor attributes that also live in a column of the same name.
COLUMNS = ("name", "email")
# Values the AI is told we have, but not shown.
PRIVATE = ("email", "phone")

Value = str | int | float | bool


class Source(models.TextChoices):
    VERIFIED = "verified"  # signed by the host site's server (an identity token)
    AGENT = "agent"  # set by a teammate in the dashboard
    RULE = "rule"  # set by a rule's action
    HOST = "host"  # sent by the host page's JavaScript, unsigned
    VISITOR = "visitor"  # typed by the visitor (a form, the chat)
    AI = "ai"  # worked out by the AI from the conversation


# Higher wins. Equal may overwrite (a visitor correcting their own email).
TRUST = {
    Source.VERIFIED: 3,
    Source.AGENT: 2,
    Source.RULE: 1,
    Source.HOST: 1,
    Source.VISITOR: 1,
    Source.AI: 0,
}


def clean(key: str, value) -> Value | None:
    """The value as stored, or None if it can't be an attribute."""
    if isinstance(value, bool | int | float):
        return value
    if not isinstance(value, str):
        return None
    value = " ".join(value.split())[:MAX_VALUE_CHARS]
    if not value:
        return None
    if key == "email":
        try:
            validate_email(value)
        except ValidationError:
            return None
        return value.lower()
    return value


def set_many(target, values: dict, source: str) -> list[str]:
    """Sets several attributes on a Visitor or Conversation and saves it.

    Returns the keys that changed. Skipped without error: bad keys, unusable values, and
    values a more trusted source already set.
    """
    stored = dict(target.attributes or {})
    changed = []
    for key, raw in values.items():
        if not isinstance(key, str) or not KEY.match(key):
            continue
        value = clean(key, raw)
        if value is None:
            continue
        current = stored.get(key)
        if current is not None:
            if TRUST.get(current.get("source"), 0) > TRUST[source]:
                continue
            if current.get("value") == value and current.get("source") == source:
                continue
        elif len(stored) >= MAX_KEYS:
            continue
        stored[key] = {"value": value, "source": str(source)}
        changed.append(key)
    if not changed:
        return []
    target.attributes = stored
    fields = ["attributes"]
    for column in COLUMNS:
        if column in changed and hasattr(target, column):
            limit = target._meta.get_field(column).max_length
            setattr(target, column, str(stored[column]["value"])[:limit])
            fields.append(column)
    target.save(update_fields=fields)
    return changed


def set_attribute(target, key: str, value, source: str) -> bool:
    return bool(set_many(target, {key: value}, source))


def remove(target, key: str) -> bool:
    """Deletes an attribute (a teammate's correction). Returns whether it was there."""
    stored = dict(target.attributes or {})
    if key not in stored:
        return False
    del stored[key]
    target.attributes = stored
    fields = ["attributes"]
    if key in COLUMNS and hasattr(target, key):
        setattr(target, key, "")
        fields.append(key)
    target.save(update_fields=fields)
    return True


def get(target, key: str, default=None):
    entry = (target.attributes or {}).get(key)
    return entry["value"] if entry else default


def source_of(target, key: str) -> str | None:
    entry = (target.attributes or {}).get(key)
    return entry["source"] if entry else None


def is_verified(target, key: str) -> bool:
    return source_of(target, key) == Source.VERIFIED


def listing(target) -> list[dict]:
    """For API responses: [{"key", "value", "source"}], by key."""
    return [{"key": key, **entry} for key, entry in sorted((target.attributes or {}).items())]


def flat(conversation) -> dict[str, Value]:
    """Everything known in one conversation, by dotted name: contact.email, conversation.topic."""
    values = {f"contact.{key}": entry["value"] for key, entry in (conversation.visitor.attributes or {}).items()}
    values |= {f"conversation.{key}": entry["value"] for key, entry in (conversation.attributes or {}).items()}
    return values
