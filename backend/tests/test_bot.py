import json

import pytest

from apps.agent import bot, http_tools, openrouter
from apps.conversations.models import Message

from .conftest import assistant, final, tool_call
from .factories import ArticleFactory, ConversationFactory, MessageFactory, OrganizationFactory, ToolFactory

pytestmark = pytest.mark.django_db


def ask(body: str, ready: bool = True, **workspace):
    """A conversation whose visitor just asked `body`, in a workspace whose organization has an LLM."""
    organization = OrganizationFactory(ready=ready)
    message = MessageFactory(
        body=body,
        conversation__workspace__organization=organization,
        **{f"conversation__workspace__{k}": v for k, v in workspace.items()},
    )
    return message.conversation


def tool_messages(request) -> list[dict]:
    return [m for m in request["messages"] if m.get("role") == "tool"]


def test_answers_from_a_workspace_tool(llm, monkeypatch):
    """The point of tools: live data, not a guess."""
    conversation = ask("Do you have the AZ-104 exam?")
    ToolFactory(workspace=conversation.workspace, name="search_exams", url="https://shop.example.com/api/exams")
    calls = []

    def fake_run(tool, inputs, visitor):
        calls.append((tool.name, inputs))
        return '[{"code":"AZ-104","name":"Azure Administrator","url":"/exams/az-104"}]', False

    monkeypatch.setattr(http_tools, "run", fake_run)
    fake = llm(
        assistant(tool_call("search_exams", {"q": "AZ-104"})),
        final("Yes, we have [AZ-104 Azure Administrator](/exams/az-104)."),
    )

    message = bot.reply(conversation.id)

    assert calls == [("search_exams", {"q": "AZ-104"})]
    assert message.body == "Yes, we have [AZ-104 Azure Administrator](/exams/az-104)."
    # The organization's key and model are used.
    assert fake.requests[0]["api_key"] == "sk-or-test-key-1234"
    assert fake.requests[0]["model"] == "test/model"
    # The tool is offered with the owner's description and schema.
    offered = {t["function"]["name"]: t["function"] for t in fake.requests[0]["tools"]}
    assert offered["search_exams"]["parameters"]["properties"] == {"q": {"type": "string"}}
    # The tool result went back in the second request, tied to its call.
    [result] = tool_messages(fake.requests[1])
    assert result["tool_call_id"] == "call_1"
    assert "Azure Administrator" in result["content"]
    # Teammates can see what the bot looked up.
    assert conversation.messages.filter(is_note=True, body__contains="search_exams").exists()


def test_system_prompt_comes_first_with_business_instructions(llm):
    conversation = ask("hi", ai_instructions="Always answer in a pirate voice.")
    fake = llm(final("Ahoy"))
    bot.reply(conversation.id)
    first = fake.requests[0]["messages"][0]
    assert first["role"] == "system"
    assert "pirate voice" in first["content"]


def test_disabled_and_foreign_tools_are_not_offered(llm):
    conversation = ask("hi")
    ToolFactory(workspace=conversation.workspace, name="mine")
    ToolFactory(workspace=conversation.workspace, name="off", enabled=False)
    ToolFactory(name="someone_elses")
    fake = llm(final("Hello!"))
    bot.reply(conversation.id)
    names = {t["function"]["name"] for t in fake.requests[0]["tools"]}
    assert names == {"reply_to_visitor", "search_knowledge_base", "handoff_to_human", "mine"}


def test_unknown_tool_name_is_an_error_result(llm):
    conversation = ask("hi")
    fake = llm(assistant(tool_call("drop_tables", {})), final("Sorry"))
    bot.reply(conversation.id)
    assert tool_messages(fake.requests[1])[0]["content"].startswith("Error:")


def test_bad_tool_arguments_become_empty_inputs(llm, monkeypatch):
    conversation = ask("hi")
    ToolFactory(workspace=conversation.workspace, name="lookup")
    seen = []
    monkeypatch.setattr(http_tools, "run", lambda tool, inputs, visitor: (seen.append(inputs), ("[]", False))[1])
    broken = {"id": "call_1", "type": "function", "function": {"name": "lookup", "arguments": "{not json"}}
    llm(assistant(broken), final("Done"))
    bot.reply(conversation.id)
    assert seen == [{}]


def test_knowledge_base_tool_and_article_buttons(llm):
    conversation = ask("How do refunds work?")
    article = ArticleFactory(workspace=conversation.workspace, title="Refund policy", body="Refunds within 30 days.")
    fake = llm(
        assistant(tool_call("search_knowledge_base", {"query": "refund"})),
        final("Refunds are accepted within 30 days.", article_ids=[article.id], offer_human=True),
    )

    message = bot.reply(conversation.id)

    found = json.loads(tool_messages(fake.requests[1])[0]["content"])
    assert found[0]["title"] == "Refund policy"
    events = [
        c["action"]["event"]
        for m in message.a2ui
        if "updateComponents" in m
        for c in m["updateComponents"]["components"]
        if c["component"] == "Button"
    ]
    assert events == [
        {"name": "open_article", "context": {"articleId": article.id}},
        {"name": "talk_to_human", "context": {}},
    ]


def test_article_ids_from_other_workspaces_are_dropped(llm):
    conversation = ask("hi")
    stranger = ArticleFactory()
    llm(final("Hi", article_ids=[stranger.id]))
    assert bot.reply(conversation.id).a2ui is None


def test_handoff_tool_flags_the_conversation(llm):
    conversation = ask("I want a refund NOW")
    llm(
        assistant(tool_call("handoff_to_human", {"reason": "angry about refund"})),
        final("A teammate will reply here shortly.", offer_human=True),
    )
    message = bot.reply(conversation.id)
    conversation.refresh_from_db()
    assert conversation.human_requested
    # No "Talk to a person" button once a person is already on the way.
    assert message.a2ui is None


def test_assistant_tool_call_message_is_kept_for_the_next_turn(llm):
    conversation = ask("hi")
    first = assistant(tool_call("search_knowledge_base", {"query": "x"}))
    first["reasoning_details"] = [{"type": "reasoning.encrypted", "data": "abc"}]
    fake = llm(first, final("ok"))
    bot.reply(conversation.id)
    replayed = [m for m in fake.requests[1]["messages"] if m.get("role") == "assistant"]
    assert replayed[-1]["reasoning_details"] == first["reasoning_details"]


def test_history_alternates_and_ends_with_the_visitor(llm):
    conversation = ConversationFactory(workspace__organization=OrganizationFactory(ready=True))
    MessageFactory(conversation=conversation, sender=Message.Sender.BOT, body="Hi! How can we help?")
    MessageFactory(conversation=conversation, body="Hello")
    MessageFactory(conversation=conversation, body="Do you ship to Canada?")
    MessageFactory(conversation=conversation, sender=Message.Sender.AGENT, body="private", is_note=True)
    fake = llm(final("Yes"))

    bot.reply(conversation.id)

    assert fake.requests[0]["messages"][1:] == [{"role": "user", "content": "Hello\n\nDo you ship to Canada?"}]


def test_plain_text_answer_is_still_used(llm):
    conversation = ask("hi")
    llm(assistant(content="Hello there"))
    assert bot.reply(conversation.id).body == "Hello there"


def test_openrouter_error_falls_back_and_tells_the_team(llm):
    conversation = ask("shipping to Canada?")
    ArticleFactory(workspace=conversation.workspace, title="Shipping", body="We ship to Canada.")
    llm(openrouter.OpenRouterError("OpenRouter credits or key limit ran out (Insufficient credits).", 402))
    message = bot.reply(conversation.id)
    assert "help center" in message.body
    assert conversation.messages.filter(is_note=True, body__contains="Insufficient credits").exists()


def test_never_ending_tool_loop_falls_back(llm):
    conversation = ask("hi")
    llm(*[assistant(tool_call("search_knowledge_base", {"query": "x"})) for _ in range(bot.MAX_STEPS)])
    assert "teammate" in bot.reply(conversation.id).body


def test_without_llm_settings_uses_keyword_search(llm):
    conversation = ask("What is your refund policy?", ready=False)
    article = ArticleFactory(workspace=conversation.workspace, title="Refund policy", body="30 days.")
    fake = llm()
    message = bot.reply(conversation.id)
    assert fake.requests == []
    assert "help center" in message.body
    assert f'"articleId": {article.id}' in json.dumps(message.a2ui)


def test_without_llm_and_no_match_offers_a_person():
    conversation = ask("zzz qqq", ready=False)
    assert "teammate" in bot.reply(conversation.id).body
