"""What every provider client shares: the HTTP call, its errors, and the shape of an answer.

The reply loop (apps.agent.bot) speaks one language, the OpenAI-style chat message, whoever
answers. Each client translates it to its provider's own API and back:

    {"role": "system", "content": "...", "cached": 1200}
        cached: how many leading characters are the same in every conversation
    {"role": "user", "content": "..."}
    {"role": "assistant", "content": "...", "tool_calls": [...], "native": ...}
        tool_calls: [{"id", "type", "function": {"name", "arguments"}}]; native: see Completion
    {"role": "tool", "tool_call_id": "...", "name": "...", "content": "..."}
"""

import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

# The most one model call may take. With a fallback set, the two share it (apps.agent.llm).
TIMEOUT_SECONDS = 60
# Room for the answer and for the thinking newer models do before it.
MAX_OUTPUT_TOKENS = 8000

# Statuses that mean "try again shortly": timeouts, rate limits, and the provider being
# down or overloaded. A rejected key or an empty balance is not among them.
TRANSIENT_STATUSES = {408, 429, 500, 502, 503, 504, 529}


class ProviderError(Exception):
    """A failed call. Its message is safe to show the workspace team."""

    def __init__(self, message: str, status: int | None = None, transient: bool | None = None):
        super().__init__(message)
        self.status = status
        # Whether the same call might work a few seconds later.
        self.transient = status in TRANSIENT_STATUSES if transient is None else transient


@dataclass
class Completion:
    """One model response and what it cost."""

    # An assistant message; may hold `tool_calls`.
    message: dict
    # The same answer exactly as the provider wrote it, which can hold more than `message`
    # (signed or encrypted reasoning). It is sent back unchanged on the next step, to the
    # same model only: another provider or model can't read it.
    native: Any = None
    input_tokens: int = 0
    # The part of input_tokens the provider read from its prompt cache (billed at a fraction).
    cached_tokens: int = 0
    output_tokens: int = 0
    # In US dollars, when the provider reports it (only OpenRouter does).
    cost: Decimal | None = None


def count(value) -> int:
    """A token count from a response. Providers omit parts of these; anything odd means 0."""
    return value if isinstance(value, int) and value > 0 else 0


def as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def as_list(value) -> list[dict]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def error_message(response: httpx.Response) -> str:
    try:
        message = response.json()["error"]["message"]
    except (ValueError, KeyError, TypeError):
        message = None
    return str(message or response.text[:300] or response.reason_phrase)


def failure(name: str, response: httpx.Response) -> ProviderError:
    """The error for a response with a failing status, worded for the workspace team."""
    message = error_message(response)
    if response.status_code == 401:
        message = f"The {name} API key was rejected ({message})."
    elif response.status_code == 402:
        message = f"{name} credits or key limit ran out ({message})."
    else:
        message = f"{name}: {message}"
    return ProviderError(message, response.status_code)


def call(name: str, method: str, url: str, headers: dict, timeout: float = TIMEOUT_SECONDS, **kwargs) -> dict:
    """One request to a provider. Raises ProviderError unless it answers with a JSON object."""
    try:
        response = httpx.request(method, url, headers=headers, timeout=timeout, **kwargs)
    except httpx.HTTPError as error:
        # The network, not the request: worth another try.
        raise ProviderError(f"Could not reach {name}: {type(error).__name__}", transient=True) from error
    if response.status_code >= 400:
        raise failure(name, response)
    try:
        data = response.json()
    except ValueError as error:
        raise ProviderError(f"{name} sent a response that isn't JSON.") from error
    if not isinstance(data, dict):
        raise ProviderError(f"{name} sent a response in a shape we don't know.")
    return data


def shortlist(models: list[dict], recommended: dict[str, str]) -> list[dict]:
    """Marks the models the picker offers (`recommended`: id to tier, cheapest first) and puts
    them first. The others stay listed, so a typed id can be recognized. An account that has
    none of the recommended ones is offered everything it has."""
    rank = {model: position for position, model in enumerate(recommended)}
    none = not any(model["id"] in rank for model in models)
    marked = [
        {**model, "recommended": none or model["id"] in rank, "tier": recommended.get(model["id"], "")}
        for model in models
    ]
    return sorted(marked, key=lambda m: rank.get(m["id"], len(rank)))


def split_system(messages: list[dict]) -> tuple[dict, list[dict]]:
    """The system message (empty when there is none) and the rest of the conversation."""
    if messages and messages[0]["role"] == "system":
        return messages[0], messages[1:]
    return {}, messages


def parse_arguments(raw) -> dict:
    """A tool call's arguments as an object; empty when the model wrote something else."""
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return as_dict(value)


def answer(text: str, calls: list[tuple[str, str, str]]) -> dict:
    """An assistant message from its text and its tool calls (id, name, JSON arguments)."""
    message: dict = {"role": "assistant", "content": text or None}
    if calls:
        message["tool_calls"] = [
            {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}
            for call_id, name, arguments in calls
        ]
    return message
