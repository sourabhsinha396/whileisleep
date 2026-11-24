"""OpenAI, through its Responses API: its newer models take tools nowhere else.

Docs: https://developers.openai.com/api/docs/guides/migrate-to-responses
"""

import json
import re

from . import base

NAME = "OpenAI"
KEYS_URL = "https://platform.openai.com/api-keys"
BASE_URL = "https://api.openai.com/v1"

# The models the picker offers: current, cheap or mid-priced, and one high-end. Reviewed 2026-11-24.
RECOMMENDED = {
    "gpt-6-luna": "low",
    "gpt-6.1-terra": "mid",
    "gpt-6.2-sol": "mid",
    "gpt-6.2-astra": "high",
}
# The model list doesn't say what a model does, so its name has to: these can chat...
CHAT_MODEL = re.compile(r"^(gpt-|chatgpt-|o\d)")
# ...and these, which start the same way, are for something else.
OTHER_WORK = re.compile(
    r"audio|realtime|transcribe|tts|image|search|instruct|live|translate|whisper|embedding|moderation|cyber"
)


def _call(method: str, path: str, api_key: str, **kwargs) -> dict:
    try:
        return base.call(NAME, method, BASE_URL + path, {"Authorization": f"Bearer {api_key}"}, **kwargs)
    except base.ProviderError as error:
        if error.status == 429 and "quota" in str(error):
            # An empty balance arrives as a rate limit, but waiting won't refill it.
            raise base.ProviderError(str(error), 429, transient=False) from error
        raise


def _items(messages: list[dict]) -> list[dict]:
    items: list[dict] = []
    for message in messages:
        if message["role"] == "tool":
            items.append(
                {"type": "function_call_output", "call_id": message["tool_call_id"], "output": message["content"]}
            )
        elif message.get("native"):
            items.extend(message["native"])
        else:
            if message.get("content"):
                items.append({"role": message["role"], "content": message["content"]})
            for call in message.get("tool_calls") or []:
                name = call["function"]["name"]
                arguments = json.dumps(base.parse_arguments(call["function"]["arguments"]))
                items.append({"type": "function_call", "call_id": call["id"], "name": name, "arguments": arguments})
    return items


def _native(output: list[dict]) -> list[dict] | None:
    """The output to send back as it came. Nothing is stored at OpenAI, so reasoning can only
    be replayed when it carries its encrypted content."""
    if any(item.get("type") == "reasoning" and not item.get("encrypted_content") for item in output):
        return None
    return output


def complete(
    api_key: str, model: str, messages: list[dict], tools: list[dict], timeout: float = base.TIMEOUT_SECONDS
) -> base.Completion:
    system, conversation = base.split_system(messages)
    body = {
        "model": model,
        "instructions": system.get("content", ""),
        "input": _items(conversation),
        # Not strict: workspaces write their own schemas, which strict mode would refuse.
        "tools": [{"type": "function", **tool["function"], "strict": False} for tool in tools],
        "tool_choice": "auto",
        "max_output_tokens": base.MAX_OUTPUT_TOKENS,
        # Visitors' conversations stay here, not in OpenAI's response log.
        "store": False,
    }
    data = _call("POST", "/responses", api_key, timeout=timeout, json=body)
    if data.get("status") == "failed" or data.get("error"):
        error = base.as_dict(data.get("error"))
        transient = error.get("code") in ("server_error", "rate_limit_exceeded")
        raise base.ProviderError(f"{NAME}: {error.get('message') or 'The response failed.'}", transient=transient)
    if data.get("status") == "incomplete":
        reason = base.as_dict(data.get("incomplete_details")).get("reason") or "unknown reason"
        raise base.ProviderError(f"{NAME} stopped before finishing its answer ({reason}).")

    output = base.as_list(data.get("output"))
    text, calls = [], []
    for item in output:
        if item.get("type") == "function_call":
            calls.append((item.get("call_id", ""), item.get("name", ""), item.get("arguments", "")))
        if item.get("type") != "message":
            continue
        for part in base.as_list(item.get("content")):
            if part.get("type") == "refusal":
                raise base.ProviderError(f"{NAME} declined to answer.")
            if part.get("type") == "output_text":
                text.append(str(part.get("text") or ""))
    if not text and not calls:
        raise base.ProviderError(f"{NAME} sent no message.")
    usage = base.as_dict(data.get("usage"))
    return base.Completion(
        message=base.answer("".join(text), calls),
        native=_native(output),
        input_tokens=base.count(usage.get("input_tokens")),
        cached_tokens=base.count(base.as_dict(usage.get("input_tokens_details")).get("cached_tokens")),
        output_tokens=base.count(usage.get("output_tokens")),
    )


def check_key(api_key: str) -> dict:
    _call("GET", "/models", api_key)
    return {}


def list_models(api_key: str) -> list[dict]:
    ids = [str(row.get("id") or "") for row in base.as_list(_call("GET", "/models", api_key).get("data"))]
    models = [{"id": i, "name": i} for i in sorted(ids) if CHAT_MODEL.match(i) and not OTHER_WORK.search(i)]
    return base.shortlist(models, RECOMMENDED)
