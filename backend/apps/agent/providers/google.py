"""Google Gemini, through its generateContent API.

Docs: https://ai.google.dev/api/generate-content
"""

import json
import re
import uuid
from urllib.parse import quote

from . import base

NAME = "Google Gemini"
KEYS_URL = "https://aistudio.google.com/apikey"
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
# Gemini refuses a tool call that lacks the signature it wrote with it. A call another model
# made has none; Google documents this value for that case.
NO_SIGNATURE = "skip_thought_signature_validator"
# Gemini models that take generateContent but don't chat.
OTHER_WORK = re.compile(r"image|tts|audio|live|embedding|robotics|computer-use")


def _call(method: str, path: str, api_key: str, **kwargs) -> dict:
    try:
        # The key goes in a header: in the address it would end up in logs.
        return base.call(NAME, method, BASE_URL + path, {"x-goog-api-key": api_key}, **kwargs)
    except base.ProviderError as error:
        if error.status == 400 and "api key not valid" in str(error).lower():
            # Google answers 400 to a bad key.
            raise base.ProviderError(f"The {NAME} API key was rejected.", 401) from error
        raise


def _parts(message: dict) -> list[dict]:
    if message.get("native"):
        # Thought signatures included.
        return message["native"]
    parts: list[dict] = [{"text": message["content"]}] if message.get("content") else []
    for call in message.get("tool_calls") or []:
        function = call["function"]
        made = {"name": function["name"], "args": base.parse_arguments(function["arguments"])}
        parts.append({"functionCall": made, "thoughtSignature": NO_SIGNATURE})
    return parts


def _contents(messages: list[dict]) -> list[dict]:
    contents: list[dict] = []
    # Ids Gemini gave its own calls. A result names its call's id only when there was one.
    known: set[str] = set()
    for message in messages:
        if message["role"] == "tool":
            response = {"name": message["name"], "response": {"result": message["content"]}}
            if message["tool_call_id"] in known:
                response["id"] = message["tool_call_id"]
            part = {"functionResponse": response}
            # All the results of one step go back in one turn.
            if contents and contents[-1]["role"] == "user" and "functionResponse" in contents[-1]["parts"][-1]:
                contents[-1]["parts"].append(part)
            else:
                contents.append({"role": "user", "parts": [part]})
        elif message["role"] == "assistant":
            parts = _parts(message)
            known.update(p["functionCall"]["id"] for p in parts if base.as_dict(p.get("functionCall")).get("id"))
            contents.append({"role": "model", "parts": parts})
        else:
            contents.append({"role": "user", "parts": [{"text": message["content"]}]})
    return contents


def _declaration(tool: dict) -> dict:
    function = tool["function"]
    return {
        "name": function["name"],
        "description": function["description"],
        "parametersJsonSchema": function["parameters"],
    }


def complete(
    api_key: str, model: str, messages: list[dict], tools: list[dict], timeout: float = base.TIMEOUT_SECONDS
) -> base.Completion:
    system, conversation = base.split_system(messages)
    body: dict = {
        "contents": _contents(conversation),
        "generationConfig": {"maxOutputTokens": base.MAX_OUTPUT_TOKENS},
    }
    if system.get("content"):
        body["systemInstruction"] = {"parts": [{"text": system["content"]}]}
    if tools:
        body["tools"] = [{"functionDeclarations": [_declaration(tool) for tool in tools]}]
    path = f"/models/{quote(model.removeprefix('models/'), safe='')}:generateContent"
    data = _call("POST", path, api_key, timeout=timeout, json=body)
    candidates = base.as_list(data.get("candidates"))
    candidate = candidates[0] if candidates else {}
    reason = candidate.get("finishReason") or base.as_dict(data.get("promptFeedback")).get("blockReason") or ""
    if reason == "MAX_TOKENS":
        raise base.ProviderError(f"{NAME} stopped before finishing its answer (MAX_TOKENS).")

    parts = base.as_list(base.as_dict(candidate.get("content")).get("parts"))
    text = "".join(str(part.get("text") or "") for part in parts if not part.get("thought"))
    calls = []
    for part in parts:
        if function := base.as_dict(part.get("functionCall")):
            call_id = function.get("id") or f"call_{uuid.uuid4().hex[:24]}"
            calls.append((call_id, function.get("name", ""), json.dumps(function.get("args") or {})))
    if not text and not calls:
        raise base.ProviderError(f"{NAME} sent no message ({reason or 'no reason given'}).")
    usage = base.as_dict(data.get("usageMetadata"))
    return base.Completion(
        message=base.answer(text, calls),
        native=parts,
        input_tokens=base.count(usage.get("promptTokenCount")),
        cached_tokens=base.count(usage.get("cachedContentTokenCount")),
        # Thinking is billed as output.
        output_tokens=base.count(usage.get("candidatesTokenCount")) + base.count(usage.get("thoughtsTokenCount")),
    )


def check_key(api_key: str) -> dict:
    _call("GET", "/models?pageSize=1", api_key)
    return {}


def list_models(api_key: str) -> list[dict]:
    models = []
    for row in base.as_list(_call("GET", "/models?pageSize=1000", api_key).get("models")):
        model = str(row.get("name") or "").removeprefix("models/")
        if not model.startswith("gemini") or OTHER_WORK.search(model):
            continue
        if "generateContent" in (row.get("supportedGenerationMethods") or []):
            models.append({"id": model, "name": row.get("displayName") or model})
    return sorted(models, key=lambda m: m["id"])
