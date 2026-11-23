"""Calls a workspace's HTTP tool with the inputs the model chose."""

import json
import re
from urllib.parse import quote

import httpx

from .models import Tool

PLACEHOLDER = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_.]*)\}")
TIMEOUT_SECONDS = 10
# Tool results go back into the prompt; keep them small.
MAX_RESULT_CHARS = 8000


def visitor_values(visitor) -> dict[str, str]:
    return {
        "visitor.id": str(visitor.pk),
        "visitor.email": visitor.email or "",
        "visitor.name": visitor.name or "",
    }


def build_request(tool: Tool, inputs: dict, visitor) -> tuple[str, dict, dict | None]:
    """Return (url, query params, json body) for one call."""
    used: set[str] = set()
    from_visitor = visitor_values(visitor)

    def fill(match: re.Match) -> str:
        key = match.group(1)
        if key.startswith("visitor."):
            return quote(from_visitor.get(key, ""), safe="")
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
    url, params, body = build_request(tool, inputs or {}, visitor)
    headers = {str(k): str(v) for k, v in (tool.headers or {}).items()}
    try:
        response = httpx.request(tool.method, url, params=params, json=body, headers=headers, timeout=TIMEOUT_SECONDS)
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
