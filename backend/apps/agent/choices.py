"""Choices the AI offers under a reply: buttons that answer the question it just asked.

Pressing one sends exactly its words as the visitor's next message, so it can do nothing that
typing couldn't. The button carries only a position; the words come from what the server kept
on the message (Message.form). Choices work until anyone but the bot writes again.

Like a form (apps.agent.forms), choices that aren't usable are dropped. Slack and pages with an
older widget show only the text, so the question must make sense without them.
"""

import re
import uuid

from . import a2ui

MAX_OPTIONS = 5
MAX_LABEL = 60
# Long enough to be an order number or an amount, which the AI must not make up.
LONG_NUMBER = re.compile(r"\d{4,}")
# How choices look in the history the AI reads.
NOTE = re.compile(r"^\[Choices shown: .*\]$", re.MULTILINE)

CHOICES_SCHEMA = {
    "type": "array",
    "items": {"type": "string"},
    "description": (
        "Optional buttons under your reply, when it asks the visitor to pick exactly one of two to five "
        "short answers. Each is written as the visitor would say it, in their language, in a few words; "
        "pressing it sends those words as their next message. A product, category, service, size or order "
        "may be a choice only if a tool result, the help center or your instructions name it: look it up "
        "before you ask, and never offer what you couldn't find. Not for open questions, for details they "
        "must type (use a form), or under a question you have already answered."
    ),
}


def normalize(raw, known: str) -> list[str] | None:
    """Clean options, or None. `known` is all the AI was told; a long number must be in it.

    One bad option drops them all: a question with an answer missing is worse than no buttons.
    """
    if not isinstance(raw, list):
        return None
    options = {}
    for label in raw:
        if not isinstance(label, str):
            return None
        text = " ".join(label.split())
        if not text:
            continue
        if len(text) > MAX_LABEL or not set(LONG_NUMBER.findall(text)) <= set(LONG_NUMBER.findall(known)):
            return None
        options.setdefault(text.casefold(), text)
    return list(options.values()) if 2 <= len(options) <= MAX_OPTIONS else None


def attach(options: list[str]) -> tuple[list[dict], dict]:
    """The A2UI surface, and what to keep on the message (Message.form)."""
    surface_id = f"choices_{uuid.uuid4().hex[:12]}"
    return a2ui.choices(surface_id, options), {"choices": options, "surface_id": surface_id}


def picked(form: dict, index) -> str | None:
    """The words of the button at `index`."""
    options = form.get("choices") or []
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(options):
        return None
    return options[index]


def note(form: dict | None) -> str:
    """A message's choices in a line, so the AI knows later what it offered."""
    options = (form or {}).get("choices")
    if not options:
        return ""
    return f"[Choices shown: {'; '.join(options)}]".replace("\n", " ")


def without_notes(text: str) -> str:
    """A reply without such lines, in case the AI copied one."""
    return NOTE.sub("", text).strip()
