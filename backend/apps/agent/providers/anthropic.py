"""Anthropic (Claude), through its Messages API.

Docs: https://platform.claude.com/docs/en/api/messages
"""

import json
import re

from . import base

NAME = "Anthropic"
KEYS_URL = "https://platform.claude.com/settings/keys"
BASE_URL = "https://api.anthropic.com/v1"
VERSION = "2026-10-21"
# Claude caches a prompt only up to where it is told to.
CACHE = {"cache_control": {"type": "ephemeral"}}


def _call(method: str, path: str, api_key: str, **kwargs) -> dict:
    headers = {"x-api-key": api_key, "anthropic-version": VERSION}
    return base.call(NAME, method, BASE_URL + path, headers, **kwargs)


def _call_id(value: str) -> str:
    """Another provider's call id may hold characters Claude refuses."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", value) or "call"


def _system(system: dict) -> list[dict]:
    """The prompt in two blocks: what every conversation shares, cached together with the
    tools (which come before it), and what belongs to this one."""
    text, shared = system.get("content", ""), system.get("cached") or 0
    blocks = []
    if text[:shared].strip():
        blocks.append({"type": "text", "text": text[:shared], **CACHE})
    if text[shared:].strip():
        blocks.append({"type": "text", "text": text[shared:]})
    return blocks


def _assistant(message: dict) -> list[dict]:
    if message.get("native"):
        # Thinking blocks included: Claude checks that they come back unchanged.
        return message["native"]
    blocks: list[dict] = [{"type": "text", "text": message["content"]}] if message.get("content") else []
    for call in message.get("tool_calls") or []:
        function = call["function"]
        arguments = base.parse_arguments(function["arguments"])
        blocks.append({"type": "tool_use", "id": _call_id(call["id"]), "name": function["name"], "input": arguments})
    return blocks


def _messages(messages: list[dict]) -> list[dict]:
    turns: list[dict] = []
    for message in messages:
        if message["role"] == "tool":
            call_id = _call_id(message["tool_call_id"])
            result = {"type": "tool_result", "tool_use_id": call_id, "content": message["content"]}
            # All the results of one step go back in one message.
            if turns and turns[-1]["role"] == "user" and isinstance(turns[-1]["content"], list):
                turns[-1]["content"].append(result)
            else:
                turns.append({"role": "user", "content": [result]})
        elif message["role"] == "assistant":
            turns.append({"role": "assistant", "content": _assistant(message)})
        else:
            turns.append({"role": "user", "content": message["content"]})
    return turns


def _tool(tool: dict) -> dict:
    function = tool["function"]
    return {
        "name": function["name"],
        "description": function["description"],
        "input_schema": function["parameters"],
    }


def complete(
    api_key: str, model: str, messages: list[dict], tools: list[dict], timeout: float = base.TIMEOUT_SECONDS
) -> base.Completion:
    system, conversation = base.split_system(messages)
    body = {
        "model": model,
        "max_tokens": base.MAX_OUTPUT_TOKENS,
        "system": _system(system),
        "messages": _messages(conversation),
        "tools": [_tool(tool) for tool in tools],
        "tool_choice": {"type": "auto"},
    }
    data = _call("POST", "/messages", api_key, timeout=timeout, json=body)
    stop = data.get("stop_reason")
    if stop == "refusal":
        raise base.ProviderError(f"{NAME} declined to answer.")
    if stop == "max_tokens":
        raise base.ProviderError(f"{NAME} stopped before finishing its answer (max_tokens).")

    content = base.as_list(data.get("content"))
    text = "".join(str(block.get("text") or "") for block in content if block.get("type") == "text")
    calls = [
        (block.get("id", ""), block.get("name", ""), json.dumps(block.get("input") or {}))
        for block in content
        if block.get("type") == "tool_use"
    ]
    if not text and not calls:
        raise base.ProviderError(f"{NAME} sent no message.")
    usage = base.as_dict(data.get("usage"))
    read = base.count(usage.get("cache_read_input_tokens"))
    written = base.count(usage.get("cache_creation_input_tokens"))
    return base.Completion(
        message=base.answer(text, calls),
        native=content,
        # Anthropic counts cached tokens apart from the rest; everyone else includes them.
        input_tokens=base.count(usage.get("input_tokens")) + read + written,
        cached_tokens=read,
        output_tokens=base.count(usage.get("output_tokens")),
    )


def check_key(api_key: str) -> dict:
    _call("GET", "/models?limit=1", api_key)
    return {}


def list_models(api_key: str) -> list[dict]:
    rows = base.as_list(_call("GET", "/models?limit=1000", api_key).get("data"))
    # Newest first, as Anthropic sends them.
    return [{"id": row["id"], "name": row.get("display_name") or row["id"]} for row in rows if row.get("id")]
