"""The fallback model: it takes over a reply when the main one fails, and only then."""

import json

import httpx
import pytest

from apps.agent import bot, providers, tasks
from apps.agent.llm import Chain
from apps.agent.models import Turn
from apps.agent.providers import ProviderError
from apps.conversations.models import Message
from apps.workspaces.models import LlmChoice

from .conftest import assistant, final, tool_call
from .factories import ConversationFactory, MessageFactory, OrganizationFactory, WorkspaceFactory

MAIN = LlmChoice("openrouter", "test/model", "sk-or-test-key-1234")
FALLBACK = LlmChoice("anthropic", "claude-test", "sk-ant-test-key-5678")


def asking(body="Do you ship to Canada?", **organization):
    organization = organization or {"with_fallback": True}
    workspace = WorkspaceFactory(organization=OrganizationFactory(**organization))
    conversation = ConversationFactory(workspace=workspace)
    return conversation, MessageFactory(conversation=conversation, body=body)


def notes(conversation):
    return list(conversation.messages.filter(is_note=True).values_list("body", flat=True))


def asked(fake):
    return [request["provider"] for request in fake.requests]


# --- In a reply ---


@pytest.mark.django_db
def test_the_fallback_is_not_asked_while_the_main_model_works(llm):
    conversation, message = asking()
    fake = llm(final("Yes."))
    bot.reply(conversation.id, trigger_id=message.pk)
    assert asked(fake) == ["openrouter"] and notes(conversation) == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    "error",
    [
        ProviderError("OpenRouter: overloaded", 503),
        ProviderError("The OpenRouter API key was rejected (no).", 401),
        ProviderError("OpenRouter credits or key limit ran out (no).", 402),
        ProviderError("OpenRouter: no such model", 404),
        ProviderError("Could not reach OpenRouter: ConnectTimeout", transient=True),
    ],
)
def test_the_fallback_answers_whatever_went_wrong(llm, error):
    conversation, message = asking()
    fake = llm(error, final("Yes, we do."))

    reply = bot.reply(conversation.id, trigger_id=message.pk, retry_transient=True)

    assert reply.body == "Yes, we do."
    assert [(r["provider"], r["model"], r["api_key"]) for r in fake.requests] == [
        ("openrouter", "test/model", "sk-or-test-key-1234"),
        ("anthropic", "claude-test", "sk-ant-test-key-5678"),
    ]
    # The visitor waits no longer for two models than for one.
    assert sum(r["timeout"] for r in fake.requests) == providers.TIMEOUT_SECONDS
    turn = Turn.objects.get()
    assert turn.stage == Turn.Stage.AI and turn.error == ""
    assert turn.model == "anthropic/claude-test" and turn.llm_calls == 1
    assert {
        "type": "model_fallback",
        "failed": "OpenRouter test/model",
        "used": "Anthropic claude-test",
        "error": str(error),
    } in turn.steps
    # The team hears that their model isn't the one answering, and why.
    (note,) = notes(conversation)
    assert "Anthropic claude-test is answering" in note and str(error) in note


@pytest.mark.django_db
def test_the_fallback_takes_over_from_where_the_main_model_was(llm):
    """Tools that already ran are not run again, and the fallback sees what they returned."""
    conversation, message = asking()
    fake = llm(
        assistant(tool_call("handoff_to_human", {"reason": "wants a person"})),
        ProviderError("OpenRouter: overloaded", 503),
        assistant(tool_call("search_knowledge_base", {"query": "canada"}, id="call_2")),
        final("A teammate will be with you."),
    )

    assert bot.reply(conversation.id, trigger_id=message.pk).body == "A teammate will be with you."

    # Once it has taken over it finishes the reply; the main model isn't tried at every step.
    assert asked(fake) == ["openrouter", "openrouter", "anthropic", "anthropic"]
    assert "Handed off." in fake.requests[2]["messages"][-1]["content"]
    assert len([n for n in notes(conversation) if n.startswith("Visitor asked for a person")]) == 1
    assert len([n for n in notes(conversation) if "is answering" in n]) == 1


@pytest.mark.django_db
def test_the_next_message_starts_with_the_main_model_again(llm):
    conversation, message = asking()
    llm(ProviderError("OpenRouter: overloaded", 503), final("Yes."))
    bot.reply(conversation.id, trigger_id=message.pk)
    second = MessageFactory(conversation=conversation, body="And to Peru?")
    fake = llm(final("Also."))
    bot.reply(conversation.id, trigger_id=second.pk)
    assert asked(fake) == ["openrouter"]


@pytest.mark.django_db
def test_when_both_fail_for_good_the_help_center_answers(llm):
    conversation, message = asking()
    fake = llm(
        ProviderError("The OpenRouter API key was rejected (no).", 401),
        ProviderError("Anthropic credits or key limit ran out (no).", 402),
    )
    tasks.answer.apply(args=(conversation.pk, "", message.pk, None)).get()
    assert len(fake.requests) == 2
    turn = Turn.objects.get()
    assert turn.stage == Turn.Stage.FALLBACK
    assert "OpenRouter API key" in turn.error and "Anthropic credits" in turn.error
    assert len(notes(conversation)) == 1


@pytest.mark.django_db
def test_when_both_are_down_they_are_tried_again_shortly(llm):
    conversation, message = asking()
    down = ProviderError("down", 503)
    rejected = ProviderError("The Anthropic API key was rejected (no).", 401)
    fake = llm(down, rejected, final("Yes, we do."))
    tasks.answer.apply(args=(conversation.pk, "", message.pk, None)).get()
    assert asked(fake) == ["openrouter", "anthropic", "openrouter"]
    assert conversation.messages.get(sender=Message.Sender.BOT).body == "Yes, we do."
    assert notes(conversation) == []


@pytest.mark.django_db
def test_a_fallback_without_a_key_is_not_asked(llm):
    conversation, message = asking(with_fallback=True, provider_keys={"openrouter": "sk-or-test-key-1234"})
    fake = llm(ProviderError("The OpenRouter API key was rejected (no).", 401))
    bot.reply(conversation.id, trigger_id=message.pk)
    assert asked(fake) == ["openrouter"]
    # With nobody to share it with, the model has the whole time.
    assert fake.requests[0]["timeout"] == providers.TIMEOUT_SECONDS


@pytest.mark.django_db
def test_only_the_shared_start_of_the_prompt_is_marked_for_caching(llm):
    conversation, message = asking()
    conversation.workspace.ai_instructions = "Be brief."
    conversation.workspace.save()
    fake = llm(final("Yes."))
    bot.reply(conversation.id, trigger_id=message.pk)
    system = fake.requests[0]["messages"][0]
    shared, own = system["content"][: system["cached"]], system["content"][system["cached"] :]
    assert shared.endswith("Be brief.") and "About this conversation" in own


# --- Between two real clients ---


@pytest.mark.django_db
def test_a_switch_halfway_is_readable_to_the_other_provider(monkeypatch):
    """OpenAI looks something up, goes down, and Claude finishes: its request holds the lookup
    in its own words and none of OpenAI's reasoning."""
    conversation, message = asking(
        provider_keys={"openai": "sk-openai", "anthropic": "sk-ant"},
        llm_provider="openai",
        llm_model="gpt-x",
        fallback_provider="anthropic",
        fallback_model="claude-x",
    )
    looked_up = {
        "status": "completed",
        "output": [
            {"type": "reasoning", "encrypted_content": "openai-only"},
            {
                "type": "function_call",
                "call_id": "call_1",
                "name": "search_knowledge_base",
                "arguments": '{"query": "x"}',
            },
        ],
    }
    answered = {
        "stop_reason": "tool_use",
        "content": [
            {
                "type": "tool_use",
                "id": "toolu_1",
                "name": "reply_to_visitor",
                "input": {"reply": "Yes.", "article_ids": [], "offer_human": False},
            }
        ],
    }
    responses = [(200, looked_up), (503, {"error": {"message": "down"}}), (200, answered)]
    sent = []

    def request(method, url, **kwargs):
        sent.append((url, kwargs["json"]))
        status, data = responses.pop(0)
        return httpx.Response(status, json=data, request=httpx.Request(method, url))

    monkeypatch.setattr(httpx, "request", request)

    assert bot.reply(conversation.id, trigger_id=message.pk).body == "Yes."

    url, body = sent[-1]
    assert url.startswith("https://api.anthropic.com") and "openai-only" not in json.dumps(body)
    assert body["messages"][1]["content"][0]["type"] == "tool_use"
    assert body["messages"][2]["content"][0]["tool_use_id"] == "call_1"


# --- The chain by itself ---


def test_one_error_is_reported_as_it_is(llm):
    error = ProviderError("OpenRouter: boom", 500)
    llm(error)
    with pytest.raises(ProviderError) as raised:
        Chain([MAIN]).complete([], [])
    assert raised.value is error


@pytest.mark.parametrize(
    ("first", "second", "transient"), [(503, 401, True), (401, 503, True), (401, 402, False), (429, 500, True)]
)
def test_worth_retrying_if_either_may_be_back(llm, first, second, transient):
    llm(ProviderError("a", first), ProviderError("b", second))
    with pytest.raises(ProviderError) as raised:
        Chain([MAIN, FALLBACK]).complete([], [])
    assert raised.value.transient is transient
