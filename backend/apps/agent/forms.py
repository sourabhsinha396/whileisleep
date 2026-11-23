"""Forms the AI asks for, and what visitors send back.

The AI describes a form in a small spec (in reply_to_visitor); `normalize` checks and
trims it, a2ui.form compiles it to A2UI components, and the spec is kept on the bot
message so `submit` can check the answers against it. This is the pattern A2UI's own
agent SDK uses: the model writes a compact description, the server emits the wire format,
so a model mistake drops the form instead of showing the visitor broken UI.

Spec:
    {"title": "So we can tell you when it's live:",
     "fields": [{"name": "email", "label": "Email", "type": "email", "required": true},
                {"name": "level", "label": "Level", "type": "choice", "options": ["Beginner", "Pro"]}],
     "submit_label": "Notify me"}
"""

import re
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.conversations import attributes

from . import a2ui

FIELD_TYPES = ("text", "long_text", "email", "phone", "number", "choice")
MAX_FIELDS = 6
MAX_OPTIONS = 8
MAX_VALUE = settings.VISITOR_MESSAGE_MAX_CHARS
NAME = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
PHONE = re.compile(r"^[+()0-9 .-]{5,30}$")
# Field names that mean the visitor's own name.
NAME_FIELDS = {"name", "full_name", "your_name"}

FORM_SCHEMA = {
    "type": "object",
    "description": (
        "Optional form shown under your reply, for details you need from the visitor (an email to "
        "notify them, an order number...). Keep it to the fields you need, usually one to three. "
        "Their answers come back as their next message."
    ),
    "properties": {
        "title": {"type": "string", "description": "One short line above the fields."},
        "fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "snake_case key, e.g. email or order_number."},
                    "label": {"type": "string"},
                    "type": {"type": "string", "enum": list(FIELD_TYPES)},
                    "required": {"type": "boolean"},
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Choices, for type choice only.",
                    },
                },
                "required": ["name", "label", "type"],
            },
        },
        "submit_label": {"type": "string"},
    },
    "required": ["fields"],
}


class FormError(Exception):
    """A submission the visitor should fix; the message is shown to them."""


def _text(value, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def normalize(spec) -> dict | None:
    """A clean copy of the AI's form spec, or None if nothing usable is left."""
    if not isinstance(spec, dict) or not isinstance(spec.get("fields"), list):
        return None
    fields, seen = [], set()
    for raw in spec["fields"][:MAX_FIELDS]:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name", "")).strip().lower()
        kind = raw.get("type", "text")
        if not NAME.match(name) or name in seen or kind not in FIELD_TYPES:
            continue
        field = {
            "name": name,
            "label": _text(raw.get("label"), 80) or name.replace("_", " ").capitalize(),
            "type": kind,
            "required": bool(raw.get("required", False)),
        }
        if kind == "choice":
            options = [_text(o, 80) for o in raw.get("options") or [] if _text(o, 80)]
            options = list(dict.fromkeys(options))[:MAX_OPTIONS]
            if len(options) < 2:
                continue
            field["options"] = options
        seen.add(name)
        fields.append(field)
    if not fields:
        return None
    return {
        "title": _text(spec.get("title"), 200),
        "fields": fields,
        "submit_label": _text(spec.get("submit_label"), 40) or "Send",
    }


def attach(spec: dict) -> tuple[list[dict], dict]:
    """The A2UI surface for a checked spec, and what to keep on the message (Message.form)."""
    surface_id = f"form_{uuid.uuid4().hex[:12]}"
    return a2ui.form(surface_id, spec), {**spec, "surface_id": surface_id, "submitted": False}


def check(form: dict, values) -> dict[str, str]:
    """The visitor's answers, checked against the form. Unknown keys are dropped."""
    if not isinstance(values, dict):
        raise FormError("The form came back empty.")
    clean = {}
    for field in form["fields"]:
        value = str(values.get(field["name"]) or "").strip()
        if len(value) > MAX_VALUE:
            raise FormError(f"{field['label']} is too long (at most {MAX_VALUE} characters).")
        if not value:
            if field["required"]:
                raise FormError(f"Please fill in {field['label']}.")
            continue
        kind = field["type"]
        if kind == "email":
            try:
                validate_email(value)
            except ValidationError as error:
                raise FormError(f"{field['label']} doesn't look like an email address.") from error
        elif kind == "phone" and not PHONE.match(value):
            raise FormError(f"{field['label']} doesn't look like a phone number.")
        elif kind == "number":
            try:
                float(value)
            except ValueError as error:
                raise FormError(f"{field['label']} should be a number.") from error
        elif kind == "choice" and value not in field["options"]:
            raise FormError(f"Pick one of the options for {field['label']}.")
        clean[field["name"]] = value
    return clean


def as_text(form: dict, values: dict[str, str]) -> str:
    """The answers as the visitor's chat message: one "Label: value" line each."""
    labels = {f["name"]: f["label"] for f in form["fields"]}
    return "\n".join(f"{labels[name]}: {value}" for name, value in values.items()) or "(sent the form empty)"


def remember(conversation, form: dict, values: dict[str, str]) -> list[str]:
    """Keeps the answers as attributes, so rules, tools and the AI can use them later.

    Every answer becomes an attribute of the conversation under its field name. An email,
    phone number or name is about the person, so it is also kept on the visitor, and the
    names of those that changed are returned. All of it is Source.VISITOR: typed, not proven.
    """
    about_visitor = {}
    for field in form["fields"]:
        value = values.get(field["name"])
        if not value:
            continue
        if field["type"] in ("email", "phone"):
            about_visitor[field["type"]] = value
        elif field["name"] in NAME_FIELDS:
            about_visitor["name"] = value
    attributes.set_many(conversation, values, attributes.Source.VISITOR)
    return attributes.set_many(conversation.visitor, about_visitor, attributes.Source.VISITOR)
