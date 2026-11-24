"""The provider clients: what each sends, and what it makes of the response. One conversation
(below) goes through all of them."""

import json
from decimal import Decimal

import httpx
import pytest

from apps.agent import providers
from apps.agent.providers import ProviderError, anthropic, google, openai, openrouter

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_order",
            "description": "Looks an order up.",
            "parameters": {"type": "object", "properties": {"id": {"type": "string"}}},
        },
    }
]
SYSTEM = {"role": "system", "content": "You are helpful. Order facts.", "cached": len("You are helpful.")}
ASKED = [SYSTEM, {"role": "user", "content": "Where is order 7?"}]
# Two calls in one step, made by some other model (so nothing native came along).
CALLS = [
    {"id": "call.1", "type": "function", "function": {"name": "get_order", "arguments": '{"id": "7"}'}},
    {"id": "call.2", "type": "function", "function": {"name": "get_order", "arguments": "not json"}},
]
LOOKED_UP = [
    *ASKED,
    {"role": "assistant", "content": "Let me look.", "tool_calls": CALLS},
    {"role": "tool", "tool_call_id": "call.1", "name": "get_order", "content": "shipped"},
    {"role": "tool", "tool_call_id": "call.2", "name": "get_order", "content": "Error: which order?"},
]


class FakeHttp:
    def __init__(self, data=None, status=200):
        self.data, self.status, self.calls = data, status, []

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return httpx.Response(self.status, json=self.data, request=httpx.Request(method, url))

    @property
    def body(self):
        return self.calls[-1]["json"]


@pytest.fixture
def http(monkeypatch):
    def install(data=None, status=200):
        fake = FakeHttp(data, status)
        monkeypatch.setattr(httpx, "request", fake)
        return fake

    return install


# What each provider sends for "hi", for a tool call, and how it counts tokens: 1200 in, of
# which 1000 cached, and 80 out.
SAID_HI = {
    "openrouter": {
        "choices": [{"message": {"role": "assistant", "content": "hi"}}],
        "usage": {"prompt_tokens": 1200, "completion_tokens": 80, "prompt_tokens_details": {"cached_tokens": 1000}},
    },
    "openai": {
        "status": "completed",
        "output": [
            {"type": "reasoning", "id": "rs_1", "encrypted_content": "abc", "summary": []},
            {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "hi"}]},
        ],
        "usage": {"input_tokens": 1200, "output_tokens": 80, "input_tokens_details": {"cached_tokens": 1000}},
    },
    "anthropic": {
        "stop_reason": "end_turn",
        "content": [{"type": "thinking", "thinking": "", "signature": "s"}, {"type": "text", "text": "hi"}],
        "usage": {
            "input_tokens": 150,
            "cache_read_input_tokens": 1000,
            "cache_creation_input_tokens": 50,
            "output_tokens": 80,
        },
    },
    "google": {
        "candidates": [
            {"content": {"parts": [{"text": "hmm", "thought": True}, {"text": "hi"}]}, "finishReason": "STOP"}
        ],
        "usageMetadata": {
            "promptTokenCount": 1200,
            "cachedContentTokenCount": 1000,
            "candidatesTokenCount": 60,
            "thoughtsTokenCount": 20,
        },
    },
}
CALLED_A_TOOL = {
    "openrouter": {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": CALLS[:1]}}]},
    "openai": {
        "status": "completed",
        "output": [
            {"type": "reasoning", "id": "rs_1", "encrypted_content": "abc"},
            {
                "type": "function_call",
                "id": "fc_1",
                "call_id": "call.1",
                "name": "get_order",
                "arguments": '{"id": "7"}',
            },
        ],
    },
    "anthropic": {
        "stop_reason": "tool_use",
        "content": [
            {"type": "thinking", "thinking": "", "signature": "s"},
            {"type": "tool_use", "id": "call.1", "name": "get_order", "input": {"id": "7"}},
        ],
    },
    "google": {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {
                            "functionCall": {"id": "call.1", "name": "get_order", "args": {"id": "7"}},
                            "thoughtSignature": "sig",
                        }
                    ]
                },
                "finishReason": "STOP",
            }
        ]
    },
}
ALL = pytest.mark.parametrize("provider", list(providers.PROVIDERS))


# --- What they all do ---


@ALL
def test_an_answer_and_its_tokens(http, provider):
    http(SAID_HI[provider])
    completion = providers.complete(provider, "key", "m", ASKED, TOOLS)
    assert completion.message["content"] == "hi" and not completion.message.get("tool_calls")
    assert (completion.input_tokens, completion.cached_tokens, completion.output_tokens) == (1200, 1000, 80)
    assert completion.cost is None


@ALL
def test_a_tool_call(http, provider):
    http(CALLED_A_TOOL[provider])
    completion = providers.complete(provider, "key", "m", ASKED, TOOLS)
    (call,) = completion.message["tool_calls"]
    assert call["id"] == "call.1" and call["function"]["name"] == "get_order"
    assert json.loads(call["function"]["arguments"]) == {"id": "7"}
    # No usage in the response: counted as nothing rather than failing.
    assert (completion.input_tokens, completion.cached_tokens, completion.output_tokens) == (0, 0, 0)


@ALL
def test_the_key_travels_in_a_header_and_the_timeout_is_kept(http, provider):
    fake = http(SAID_HI[provider])
    providers.complete(provider, "s3cret-key", "m", ASKED, TOOLS, 30)
    (call,) = fake.calls
    assert "s3cret-key" in str(call["headers"]) and "s3cret-key" not in call["url"]
    assert "s3cret-key" not in str(call["json"])
    assert call["timeout"] == 30


@ALL
def test_the_next_step_continues_from_the_models_own_answer(http, provider):
    """Signed reasoning is sent back exactly as it came."""
    fake = http(CALLED_A_TOOL[provider])
    first = providers.complete(provider, "key", "m", ASKED, TOOLS)
    step = [
        *ASKED,
        {**first.message, "native": first.native},
        {"role": "tool", "tool_call_id": "call.1", "name": "get_order", "content": "shipped"},
    ]
    providers.complete(provider, "key", "m", step, TOOLS)
    written = {
        "openrouter": lambda body: body["messages"][2] == {"role": "assistant", "tool_calls": CALLS[:1]},
        "openai": lambda body: body["input"][1:3] == CALLED_A_TOOL["openai"]["output"],
        "anthropic": lambda body: body["messages"][1]["content"] == CALLED_A_TOOL["anthropic"]["content"],
        "google": lambda body: (
            body["contents"][1]
            == {
                "role": "model",
                **CALLED_A_TOOL["google"]["candidates"][0]["content"],
            }
        ),
    }
    assert written[provider](fake.body)


@ALL
def test_another_model_never_sees_native_data(http, provider):
    """Not another provider's, nor another model's of the same provider."""
    fake = http(SAID_HI[provider])
    others = [p for p in providers.PROVIDERS if p != provider]
    for author in [[provider, "other-model"], *[[p, "m"] for p in others]]:
        message = {**LOOKED_UP[2], "native": {"by": author, "data": [{"secret": "reasoning"}]}}
        providers.complete(provider, "key", "m", [*ASKED, message, *LOOKED_UP[3:]], TOOLS)
        assert "reasoning" not in json.dumps(fake.body.get("messages") or fake.body.get("input") or fake.body)
        assert "native" not in json.dumps(fake.body) and "shipped" in json.dumps(fake.body)


@ALL
@pytest.mark.parametrize(
    ("status", "expected", "transient"),
    [
        (401, "API key was rejected", False),
        (402, "credits or key limit", False),
        (404, "boom", False),
        (429, "boom", True),
        (500, "boom", True),
        (529, "boom", True),
    ],
)
def test_errors_are_readable(http, provider, status, expected, transient):
    http({"error": {"code": status, "message": "boom"}}, status)
    with pytest.raises(ProviderError, match=expected) as error:
        providers.complete(provider, "k", "m", ASKED, TOOLS)
    assert providers.PROVIDERS[provider].NAME in str(error.value)
    assert error.value.transient is transient


@ALL
@pytest.mark.parametrize("data", [{}, [], {"choices": []}, {"output": "x", "content": 3, "candidates": [1]}])
def test_odd_responses_are_errors_not_crashes(http, provider, data):
    http(data)
    with pytest.raises(ProviderError):
        providers.complete(provider, "k", "m", ASKED, TOOLS)


@ALL
@pytest.mark.parametrize("usage", ["lots", {"prompt_tokens": "many"}, {"input_tokens": -5, "cost": "free"}])
def test_odd_usage_does_not_break_a_reply(http, provider, usage):
    http({**SAID_HI[provider], "usage": usage, "usageMetadata": usage})
    completion = providers.complete(provider, "k", "m", ASKED, TOOLS)
    assert completion.input_tokens == 0 and completion.cost is None


@ALL
def test_a_page_instead_of_json_is_an_error(monkeypatch, provider):
    page = lambda method, url, **kw: httpx.Response(200, text="<html>", request=httpx.Request(method, url))  # noqa: E731
    monkeypatch.setattr(httpx, "request", page)
    with pytest.raises(ProviderError, match="isn't JSON"):
        providers.complete(provider, "k", "m", ASKED, TOOLS)


@ALL
def test_checking_a_key_asks_the_provider(http, provider):
    fake = http({"data": [], "models": []})
    providers.PROVIDERS[provider].check_key("s3cret-key")
    assert fake.calls[0]["method"] == "GET" and "s3cret-key" in str(fake.calls[0]["headers"])
    http({"error": {"message": "nope"}}, 401)
    with pytest.raises(ProviderError, match="rejected"):
        providers.PROVIDERS[provider].check_key("bad")


# --- OpenRouter ---


def test_openrouter_request(http):
    fake = http(SAID_HI["openrouter"])
    providers.complete("openrouter", "sk-or-x", "m/1", LOOKED_UP, TOOLS)
    assert fake.calls[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert fake.calls[0]["headers"]["Authorization"] == "Bearer sk-or-x"
    assert fake.body["model"] == "m/1" and fake.body["tools"] == TOOLS
    assert fake.body["messages"][0] == {"role": "system", "content": SYSTEM["content"]}
    assert fake.body["messages"][3] == {"role": "tool", "tool_call_id": "call.1", "content": "shipped"}


def test_openrouter_reports_cost(http):
    http({**SAID_HI["openrouter"], "usage": {"cost": 0.00042}})
    assert providers.complete("openrouter", "k", "m", [], []).cost == Decimal("0.00042")


def test_openrouter_error_inside_a_good_response(http):
    http({"error": {"code": 502, "message": "Upstream is down"}})
    with pytest.raises(ProviderError, match="Upstream is down") as error:
        providers.complete("openrouter", "k", "m", [], [])
    assert error.value.transient


def test_openrouter_models_skip_those_without_tools(http):
    rows = [
        {"id": "b/with-tools", "name": "B", "supported_parameters": ["tools", "temperature"]},
        {"id": "a/no-tools", "name": "A", "supported_parameters": ["temperature"]},
        {"id": "c/unknown", "display_name": "C"},
    ]
    http({"data": rows})
    assert openrouter.list_models() == [
        {"id": "b/with-tools", "name": "B", "recommended": False, "tier": ""},
        {"id": "c/unknown", "name": "C", "recommended": False, "tier": ""},
    ]


def test_openrouter_recommends_a_short_list_in_order(http):
    kept = list(openrouter.RECOMMENDED)[:-1]
    ids = ["anthropic/claude-haiku-4.5", *reversed(kept), "z/other"]
    http({"data": [{"id": i, "name": i} for i in ids]})
    models = openrouter.list_models()
    # One that OpenRouter no longer lists isn't offered.
    assert [m["id"] for m in models if m["recommended"]] == kept
    assert [m["tier"] for m in models if m["recommended"]] == [openrouter.RECOMMENDED[i] for i in kept]
    assert [m["id"] for m in models if not m["recommended"]] == ["anthropic/claude-haiku-4.5", "z/other"]


def test_the_openrouter_short_list_stays_short():
    assert len(openrouter.RECOMMENDED) <= 20
    # Tier by tier, as the picker groups them.
    tiers = list(openrouter.RECOMMENDED.values())
    assert tiers == sorted(tiers, key=["low", "mid", "high"].index)
    high = sorted(i.split("/")[0] for i, tier in openrouter.RECOMMENDED.items() if tier == "high")
    assert high == ["anthropic", "google", "openai"]


# --- OpenAI ---


def test_openai_request(http):
    fake = http(SAID_HI["openai"])
    providers.complete("openai", "sk-x", "gpt-x", LOOKED_UP, TOOLS)
    assert fake.calls[0]["url"] == "https://api.openai.com/v1/responses"
    assert fake.calls[0]["headers"] == {"Authorization": "Bearer sk-x"}
    assert fake.body["instructions"] == SYSTEM["content"] and fake.body["store"] is False
    assert fake.body["tools"] == [{"type": "function", **TOOLS[0]["function"], "strict": False}]
    assert fake.body["input"] == [
        {"role": "user", "content": "Where is order 7?"},
        {"role": "assistant", "content": "Let me look."},
        {"type": "function_call", "call_id": "call.1", "name": "get_order", "arguments": '{"id": "7"}'},
        {"type": "function_call", "call_id": "call.2", "name": "get_order", "arguments": "{}"},
        {"type": "function_call_output", "call_id": "call.1", "output": "shipped"},
        {"type": "function_call_output", "call_id": "call.2", "output": "Error: which order?"},
    ]


def test_openai_reasoning_that_cannot_be_replayed_is_left_out(http):
    data = json.loads(json.dumps(CALLED_A_TOOL["openai"]))
    del data["output"][0]["encrypted_content"]
    http(data)
    assert providers.complete("openai", "k", "m", ASKED, TOOLS).native is None


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"status": "incomplete", "incomplete_details": {"reason": "max_output_tokens"}}, "max_output_tokens"),
        (
            {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]},
            "declined",
        ),
        ({"status": "failed", "error": {"code": "server_error", "message": "Oops"}}, "Oops"),
    ],
)
def test_openai_answers_that_are_not_answers(http, data, expected):
    http(data)
    with pytest.raises(ProviderError, match=expected):
        providers.complete("openai", "k", "m", ASKED, TOOLS)


def test_openai_empty_balance_is_not_worth_a_retry(http):
    http({"error": {"code": "insufficient_quota", "message": "You exceeded your current quota."}}, 429)
    with pytest.raises(ProviderError) as error:
        providers.complete("openai", "k", "m", ASKED, TOOLS)
    assert not error.value.transient


def test_openai_models_are_the_ones_that_chat(http):
    ids = ["gpt-6-luna", "o4-mini", "gpt-image-2.6-flare", "gpt-realtime-2.1", "text-embedding-3", "gpt-4o-audio"]
    http({"data": [{"id": i} for i in ids]})
    assert [m["id"] for m in openai.list_models("k")] == ["gpt-6-luna", "o4-mini"]


# --- Anthropic ---


def test_anthropic_request(http):
    fake = http(SAID_HI["anthropic"])
    providers.complete("anthropic", "sk-ant-x", "claude-x", LOOKED_UP, TOOLS)
    assert fake.calls[0]["url"] == "https://api.anthropic.com/v1/messages"
    assert fake.calls[0]["headers"] == {"x-api-key": "sk-ant-x", "anthropic-version": "2026-10-21"}
    # The shared part of the prompt is cached; this conversation's part is not.
    assert fake.body["system"] == [
        {"type": "text", "text": "You are helpful.", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": " Order facts."},
    ]
    assert fake.body["tools"] == [
        {
            "name": "get_order",
            "description": "Looks an order up.",
            "input_schema": TOOLS[0]["function"]["parameters"],
        }
    ]
    assert fake.body["messages"] == [
        {"role": "user", "content": "Where is order 7?"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "Let me look."},
                # Ids in Claude's alphabet, the same in call and result.
                {"type": "tool_use", "id": "call_1", "name": "get_order", "input": {"id": "7"}},
                {"type": "tool_use", "id": "call_2", "name": "get_order", "input": {}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_1", "content": "shipped"},
                {"type": "tool_result", "tool_use_id": "call_2", "content": "Error: which order?"},
            ],
        },
    ]
    # Newer Claude models refuse these.
    assert not {"temperature", "top_p", "top_k"} & set(fake.body)


@pytest.mark.parametrize(("stop", "expected"), [("refusal", "declined"), ("max_tokens", "before finishing")])
def test_anthropic_answers_that_are_not_answers(http, stop, expected):
    http({**SAID_HI["anthropic"], "stop_reason": stop})
    with pytest.raises(ProviderError, match=expected):
        providers.complete("anthropic", "k", "m", ASKED, TOOLS)


def test_anthropic_models(http):
    http({"data": [{"id": "claude-x", "display_name": "Claude X"}, {"id": "claude-y"}]})
    assert anthropic.list_models("k") == [
        {"id": "claude-x", "name": "Claude X"},
        {"id": "claude-y", "name": "claude-y"},
    ]


# --- Google ---


def test_google_request(http):
    fake = http(SAID_HI["google"])
    providers.complete("google", "AIza-x", "models/gemini-x", LOOKED_UP, TOOLS)
    assert fake.calls[0]["url"] == "https://generativelanguage.googleapis.com/v1beta/models/gemini-x:generateContent"
    assert fake.calls[0]["headers"] == {"x-goog-api-key": "AIza-x"}
    assert fake.body["systemInstruction"] == {"parts": [{"text": SYSTEM["content"]}]}
    (declared,) = fake.body["tools"][0]["functionDeclarations"]
    assert declared["parametersJsonSchema"] == TOOLS[0]["function"]["parameters"]
    skipped = "skip_thought_signature_validator"
    assert fake.body["contents"] == [
        {"role": "user", "parts": [{"text": "Where is order 7?"}]},
        {
            "role": "model",
            "parts": [
                {"text": "Let me look."},
                {"functionCall": {"name": "get_order", "args": {"id": "7"}}, "thoughtSignature": skipped},
                {"functionCall": {"name": "get_order", "args": {}}, "thoughtSignature": skipped},
            ],
        },
        {
            "role": "user",
            "parts": [
                {"functionResponse": {"name": "get_order", "response": {"result": "shipped"}}},
                {"functionResponse": {"name": "get_order", "response": {"result": "Error: which order?"}}},
            ],
        },
    ]


def test_google_results_carry_the_id_gemini_gave_the_call(http):
    fake = http(CALLED_A_TOOL["google"])
    first = providers.complete("google", "k", "m", ASKED, TOOLS)
    result = {"role": "tool", "tool_call_id": "call.1", "name": "get_order", "content": "shipped"}
    providers.complete("google", "k", "m", [*ASKED, {**first.message, "native": first.native}, result], TOOLS)
    assert fake.body["contents"][-1]["parts"][0]["functionResponse"]["id"] == "call.1"


def test_google_call_without_an_id_gets_one(http):
    data = json.loads(json.dumps(CALLED_A_TOOL["google"]))
    del data["candidates"][0]["content"]["parts"][0]["functionCall"]["id"]
    http(data)
    (call,) = providers.complete("google", "k", "m", ASKED, TOOLS).message["tool_calls"]
    assert call["id"].startswith("call_")


def test_google_answers_400_to_a_bad_key(http):
    http({"error": {"code": 400, "message": "API key not valid. Please pass a valid API key."}}, 400)
    with pytest.raises(ProviderError, match="API key was rejected"):
        google.check_key("bad")


@pytest.mark.parametrize(
    "data",
    [{"promptFeedback": {"blockReason": "SAFETY"}}, {"candidates": [{"finishReason": "SAFETY", "content": {}}]}],
)
def test_google_blocked_answers_say_why(http, data):
    http(data)
    with pytest.raises(ProviderError, match="SAFETY"):
        providers.complete("google", "k", "m", ASKED, TOOLS)


def test_google_model_id_cannot_change_the_address(http):
    fake = http(SAID_HI["google"])
    providers.complete("google", "k", "../../evil?x=", ASKED, TOOLS)
    assert fake.calls[0]["url"].startswith("https://generativelanguage.googleapis.com/v1beta/models/..%2F..%2Fevil%3F")


def test_google_models_are_the_ones_that_chat(http):
    def row(name, methods=("generateContent",)):
        return {"name": f"models/{name}", "displayName": name.upper(), "supportedGenerationMethods": list(methods)}

    http({"models": [row("gemini-x"), row("gemini-embedding", ["embedContent"]), row("gemini-x-image"), row("gemma")]})
    assert google.list_models("k") == [{"id": "gemini-x", "name": "GEMINI-X"}]
