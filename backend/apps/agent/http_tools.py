"""Calls a workspace's HTTP tool with the inputs the model chose.

`{visitor.KEY}` placeholders in the URL are filled here from the visitor's attributes, never
by the model, so the model can't ask about someone else. That only helps if the attribute
itself is true: a typed email proves nothing. So a placeholder is filled only from a value
the host site signed (apps.conversations.identity), unless the tool's owner turned on
`allow_unverified_identity` for a tool where the value unlocks nothing private.
"""

import json
import re
from urllib.parse import quote

import httpx

from apps.conversations import attributes
from whileisleep import outbound

from .models import Tool

PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")
TIMEOUT_SECONDS = 10
# Tool results go back into the prompt; keep them small.
MAX_RESULT_CHARS = 8000


class UnverifiedIdentity(Exception):
    """The tool needs a fact about the visitor that nothing has proven."""

    def __init__(self, key: str):
        self.key = key
        super().__init__(
            f"This lookup needs the visitor's verified {key.replace('_', ' ')}, and the website hasn't "
            "confirmed who this visitor is. Don't guess or ask them for it: say you can't look that up "
            "in this chat and offer a teammate."
        )


def visitor_value(tool: Tool, visitor, key: str) -> str:
    """The value for a `{visitor.KEY}` placeholder."""
    if key == "id":
        # Our own id for the visitor: not something they could have claimed.
        return str(visitor.pk)
    if key == "external_id":
        # Only ever set from a signed token.
        if not visitor.external_id:
            raise UnverifiedIdentity("user id")
        return visitor.external_id
    if not (tool.allow_unverified_identity or attributes.is_verified(visitor, key)):
        raise UnverifiedIdentity(key)
    return str(attributes.get(visitor, key, ""))


def build_request(tool: Tool, inputs: dict, visitor) -> tuple[str, dict, dict | None]:
    """Return (url, query params, json body) for one call. Raises UnverifiedIdentity."""
    used: set[str] = set()

    def fill(match: re.Match) -> str:
        key = match.group(1)
        if key.startswith("visitor."):
            return quote(visitor_value(tool, visitor, key.removeprefix("visitor.")), safe="")
        if key in inputs:
            used.add(key)
            return quote(str(inputs[key]), safe="")
        return ""

    url = PLACEHOLDER.sub(fill, tool.url)
    rest = {k: v for k, v in inputs.items() if k not in used}
    if tool.method == Tool.Method.POST:
        return url, {}, rest
    return url, {k: v for k, v in rest.items() if v is not None}, None


def run(tool: Tool, inputs: dict, visitor) -> tuple[str, bool]:
    """Call the tool. Returns (result text for the model, is_error)."""
    try:
        url, params, body = build_request(tool, inputs or {}, visitor)
    except UnverifiedIdentity as error:
        return str(error), True
    headers = {str(k): str(v) for k, v in (tool.headers or {}).items()}
    try:
        response = outbound.request(
            tool.method, url, params=params, json=body, headers=headers, timeout=TIMEOUT_SECONDS
        )
    except outbound.BlockedAddress as error:
        return str(error), True
    except httpx.HTTPError as error:
        return f"Could not reach the service: {type(error).__name__}", True
    text = response.text
    try:
        # Compact JSON uses fewer tokens.
        text = json.dumps(response.json(), separators=(",", ":"), ensure_ascii=False)
    except ValueError:
        pass
    if len(text) > MAX_RESULT_CHARS:
        text = text[:MAX_RESULT_CHARS] + " ...[truncated]"
    if response.status_code >= 400:
        return f"HTTP {response.status_code}: {text[:1000]}", True
    return text, False
