"""OpenRouter: one key for many providers' models. OpenAI-style chat completions with tools.

Docs: https://openrouter.ai/docs/api-reference/chat-completion
"""

from decimal import Decimal, InvalidOperation

from . import base

NAME = "OpenRouter"
KEYS_URL = "https://openrouter.ai/keys"
BASE_URL = "https://openrouter.ai/api/v1"
# Less than the others get: OpenRouter refuses a call whose whole allowance the balance
# can't cover.
MAX_TOKENS = 4000
# What it knows in a message; the rest is there for the other providers.
FIELDS = ("role", "content", "tool_calls", "tool_call_id")


def _call(method: str, path: str, api_key: str, **kwargs) -> dict:
    headers = {"X-OpenRouter-Title": "whileisleep"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return base.call(NAME, method, BASE_URL + path, headers, **kwargs)


def _usage(data: dict) -> dict:
    usage = base.as_dict(data.get("usage"))
    try:
        cost = Decimal(str(usage["cost"])) if usage.get("cost") is not None else None
    except (InvalidOperation, ValueError):
        cost = None
    return {
        "input_tokens": base.count(usage.get("prompt_tokens")),
        "cached_tokens": base.count(base.as_dict(usage.get("prompt_tokens_details")).get("cached_tokens")),
        "output_tokens": base.count(usage.get("completion_tokens")),
        "cost": cost,
    }


def _message(message: dict) -> dict:
    if message.get("native"):
        # Reasoning details included, so the model continues from them.
        return message["native"]
    return {key: message[key] for key in FIELDS if message.get(key) is not None}


def complete(
    api_key: str, model: str, messages: list[dict], tools: list[dict], timeout: float = base.TIMEOUT_SECONDS
) -> base.Completion:
    body = {
        "model": model,
        "messages": [_message(message) for message in messages],
        "tools": tools,
        "tool_choice": "auto",
        "max_tokens": MAX_TOKENS,
        # Ask for token counts and cost in the response.
        "usage": {"include": True},
    }
    data = _call("POST", "/chat/completions", api_key, timeout=timeout, json=body)
    if data.get("error"):
        # The model's own provider failed after OpenRouter had answered 200.
        error = base.as_dict(data["error"])
        status = error.get("code") if isinstance(error.get("code"), int) else None
        raise base.ProviderError(f"{NAME}: {error.get('message') or 'Unknown error'}", status)
    try:
        message = data["choices"][0]["message"]
        native = {key: value for key, value in message.items() if value is not None}
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        raise base.ProviderError(f"{NAME} sent no message.") from error
    return base.Completion(message=message, native=native, **_usage(data))


def check_key(api_key: str) -> dict:
    """What OpenRouter says about the key: its label, usage and remaining limit."""
    data = base.as_dict(_call("GET", "/key", api_key).get("data"))
    return {
        "label": data.get("label") or "",
        "usage": data.get("usage"),
        "limit_remaining": data.get("limit_remaining"),
    }


def list_models(api_key: str = "") -> list[dict]:
    """Its list is public, so this works without a key."""
    models = []
    for row in base.as_list(_call("GET", "/models", api_key).get("data")):
        if not row.get("id"):
            continue
        params = row.get("supported_parameters")
        # Skip models known not to take tools; keep those that don't say.
        if isinstance(params, list) and "tools" not in params:
            continue
        models.append({"id": row["id"], "name": row.get("name") or row.get("display_name") or row["id"]})
    return sorted(models, key=lambda m: m["id"])
