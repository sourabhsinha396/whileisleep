"""Cards the AI shows under a reply: details, a list or a timeline from a tool's result.

The AI never writes the values. It names a result ("r1", the label call results carry in the
prompt) and JSON Pointers into it, and the server reads the values from what the tool really
returned. Only the values a card shows are sent to the visitor, not the rest of the result.
The AI does write titles and labels, so a number in one must appear in the result too.

Like a form (apps.agent.forms), a card that isn't usable is dropped, never shown broken. The
reply's text must make sense without it: Slack and pages with an older widget don't show it.
"""

import json
import re
import uuid
from datetime import datetime

from . import a2ui

MAX_CARDS = 3
MAX_ROWS = 8
MAX_ITEMS = 6
MAX_VALUE = 200
MAX_SUMMARY = 600

NUMBER = re.compile(r"\d+")
WHOLE = re.compile(r"^-?\d+$")
ISO_TIME = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d")
# A label or key that says an amount isn't the one a person reads: 4250 for 42.50.
CENTS = re.compile(r"(?<![a-z])(cents?|minor)(?![a-z])", re.IGNORECASE)
# Keys of money. A whole number in one may be cents, and nothing in the data says which.
MONEY = re.compile(r"amount|price|total|cost|fee(?![a-z])|balance|charge|refund|paid|due", re.IGNORECASE)
# How a card looks in the history the AI reads.
NOTE = re.compile(r"^\[Card shown: .*\]$", re.MULTILINE)
SURFACE_PREFIX = "card_"

CARDS_SCHEMA = {
    "type": "array",
    "description": (
        "Optional cards under your reply, showing facts from a tool result whose content starts with a "
        "label like [result r1]. Use one for an order, a booking, a few products, or delivery steps; not "
        "for a single fact. You give JSON Pointers and the values are shown exactly as they are in the "
        "result, so leave out what reads badly that way: an amount in cents (no card, if that is the "
        "point of it), a Unix time, an internal id. Also leave out what the visitor didn't ask about. "
        "One result can fill two cards: the details of an order, then a timeline of its steps. Your "
        "reply must still make sense without the card."
    ),
    "items": {
        "type": "object",
        "properties": {
            "type": {
                "type": "string",
                "enum": ["details", "list", "timeline"],
                "description": "details: facts about one thing. list: several things. timeline: steps in order.",
            },
            "result": {"type": "string", "description": "The label of the tool result, e.g. r1."},
            "title": {"type": "string", "description": "A few words, in the visitor's language."},
            "rows": {
                "type": "array",
                "description": "For details.",
                "items": {
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "path": {"type": "string", "description": "From the top of the result, e.g. /order/status."},
                    },
                    "required": ["label", "path"],
                },
            },
            "items_path": {
                "type": "string",
                "description": "For list and timeline: where the array is, e.g. /products. Empty if the result is it.",
            },
            "title_path": {"type": "string", "description": "For list and timeline: each item's name, e.g. /name."},
            "detail_path": {"type": "string", "description": "For list and timeline: each item's price, date..."},
            "done_path": {"type": "string", "description": "For timeline: each item's true or false, if it's done."},
        },
        "required": ["type", "result"],
    },
}


def parse(content: str):
    """A tool's answer as data cards can use, or None."""
    try:
        data = json.loads(content)
    except (ValueError, RecursionError):
        return None  # plain text, or JSON cut for length
    return data if isinstance(data, dict | list) and data else None


def _get(data, path):
    """What a JSON Pointer finds, or None. The first slash may be missing."""
    if not isinstance(path, str):
        return None
    for token in path.removeprefix("/").split("/") if path.strip("/") else ():
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(data, dict):
            data = data.get(token)
        elif isinstance(data, list) and token.isascii() and token.isdigit() and len(token) < 6:
            data = data[int(token)] if int(token) < len(data) else None
        else:
            return None
    return data


def _value(data, path) -> str:
    """The text of one value. Empty for nothing, for objects and lists, and for money that may be in cents."""
    found = _get(data, path)
    if MONEY.search(str(path).rsplit("/", 1)[-1]) and WHOLE.match(str(found)):
        return ""
    if isinstance(found, bool):
        return "Yes" if found else "No"
    if isinstance(found, int | float):
        return str(found)
    if not isinstance(found, str):
        return ""
    text = " ".join(found.split())
    if ISO_TIME.match(text):
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            pass
        else:
            # In the time zone the data gave; we don't know the visitor's.
            zone = "" if moment.tzinfo is None else moment.strftime(" %Z")
            text = f"{moment:%Y-%m-%d %H:%M}{zone}"
    return text if len(text) <= MAX_VALUE else text[:MAX_VALUE] + "…"


def _label(raw, data, limit: int) -> str:
    """Words the AI wrote, or nothing if they hold a number the result doesn't."""
    if not isinstance(raw, str):
        return ""
    text = " ".join(raw.split())[:limit]
    numbers = set(NUMBER.findall(text))
    if numbers and not numbers <= set(NUMBER.findall(json.dumps(data, ensure_ascii=False))):
        return ""
    return text


def _details(spec: dict, data) -> list[dict]:
    rows = []
    for row in spec["rows"] if isinstance(spec.get("rows"), list) else []:
        if not isinstance(row, dict):
            continue
        if CENTS.search(f"{row.get('label')} {row.get('path')}"):
            continue
        label, value = _label(row.get("label"), data, 60), _value(data, row.get("path"))
        if label and value:
            rows.append({"label": label, "value": value})
    return rows[:MAX_ROWS]


def _items(spec: dict, data) -> list[dict]:
    found = _get(data, spec.get("items_path") or "")
    items = []
    for item in found if isinstance(found, list) else []:
        # A list of plain values needs no path; an object has no text of its own.
        title = _value(item, spec.get("title_path") or "")
        if not title:
            continue
        path = spec.get("detail_path")
        detail = _value(item, path) if path and not CENTS.search(str(path)) else ""
        done = _get(item, spec["done_path"]) if spec.get("done_path") else None
        items.append({"title": title, "detail": detail, "done": done if isinstance(done, bool) else None})
        if len(items) == MAX_ITEMS:
            break
    return items


def normalize(specs, results: dict) -> list[dict]:
    """The AI's cards, with values read from `results` ({label: data}). Unusable ones are left out."""
    cards = []
    for spec in specs if isinstance(specs, list) else []:
        if not isinstance(spec, dict) or not isinstance(spec.get("result"), str):
            continue
        kind, data = spec.get("type"), results.get(spec["result"].strip("[] ").removeprefix("result "))
        if data is None or kind not in ("details", "list", "timeline"):
            continue
        rows = _details(spec, data) if kind == "details" else _items(spec, data)
        if rows:
            cards.append({"type": kind, "title": _label(spec.get("title"), data, 80), "rows": rows})
    return cards[:MAX_CARDS]


def attach(cards: list[dict]) -> list[dict]:
    """The A2UI messages of `normalize`d cards."""
    return [m for card in cards for m in a2ui.card(f"{SURFACE_PREFIX}{uuid.uuid4().hex[:12]}", card)]


def note(messages: list | None) -> str:
    """The cards among a message's A2UI in a line, so the AI knows later what it showed."""
    words, data = [], {}
    for message in messages or []:
        create, update = message.get("createSurface"), message.get("updateComponents")
        if create:
            data = create.get("dataModel") or {}
        elif update and update["surfaceId"].startswith(SURFACE_PREFIX):
            for component in update["components"]:
                if component["component"] == "Text":
                    text = component["text"]
                    words.append(str(_get(data, text["@path"])) if isinstance(text, dict) else text)
    if not words:
        return ""
    line = "; ".join(words).replace("[", "(").replace("]", ")")
    return f"[Card shown: {line if len(line) <= MAX_SUMMARY else line[:MAX_SUMMARY] + '…'}]"


def without_notes(text: str) -> str:
    """A reply without such lines, in case the AI copied one."""
    return NOTE.sub("", text).strip()
