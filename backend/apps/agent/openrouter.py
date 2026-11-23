"""Minimal OpenRouter client (OpenAI-style chat completions with tools).

Docs: https://openrouter.ai/docs/api-reference/chat-completion
"""

import httpx

BASE_URL = "https://openrouter.ai/api/v1"
TIMEOUT_SECONDS = 60
HEADERS = {"X-OpenRouter-Title": "whileisleep"}


class OpenRouterError(Exception):
    """A failed call. `message` is safe to show the workspace team."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _error(response: httpx.Response) -> OpenRouterError:
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = response.text[:300] or response.reason_phrase
    if response.status_code == 401:
        message = f"The OpenRouter API key was rejected ({message})."
    elif response.status_code == 402:
        message = f"OpenRouter credits or key limit ran out ({message})."
    return OpenRouterError(message, response.status_code)


def _call(method: str, path: str, api_key: str, **kwargs) -> dict:
    try:
        response = httpx.request(
            method,
            BASE_URL + path,
            headers={**({"Authorization": f"Bearer {api_key}"} if api_key else {}), **HEADERS},
            timeout=TIMEOUT_SECONDS,
            **kwargs,
        )
    except httpx.HTTPError as error:
        raise OpenRouterError(f"Could not reach OpenRouter: {type(error).__name__}") from error
    if response.status_code >= 400:
        raise _error(response)
    try:
        return response.json()
    except ValueError as error:
        raise OpenRouterError("OpenRouter sent a response that isn't JSON.") from error


def complete(api_key: str, model: str, messages: list[dict], tools: list[dict]) -> dict:
    """One chat completion. Returns choices[0].message (may hold `tool_calls`)."""
    data = _call(
        "POST",
        "/chat/completions",
        api_key,
        json={"model": model, "messages": messages, "tools": tools, "tool_choice": "auto", "max_tokens": 4000},
    )
    if "error" in data:
        raise OpenRouterError(str(data["error"].get("message", "Unknown error")))
    try:
        return data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as error:
        raise OpenRouterError("OpenRouter sent no message.") from error


def key_info(api_key: str) -> dict:
    """Checks a key. Returns its label, usage and remaining limit."""
    data = _call("GET", "/key", api_key).get("data") or {}
    return {
        "label": data.get("label") or "",
        "usage": data.get("usage"),
        "limit_remaining": data.get("limit_remaining"),
        "is_free_tier": bool(data.get("is_free_tier")),
    }


def list_models(api_key: str = "") -> list[dict]:
    """Model ids and names, for the model picker."""
    data = _call("GET", "/models", api_key)
    rows = data.get("data") if isinstance(data, dict) else None
    models = []
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("id"):
            continue
        params = row.get("supported_parameters")
        # Skip models known not to take tools; keep those that don't say.
        if isinstance(params, list) and "tools" not in params:
            continue
        models.append({"id": row["id"], "name": row.get("name") or row.get("display_name") or row["id"]})
    return sorted(models, key=lambda m: m["id"])
