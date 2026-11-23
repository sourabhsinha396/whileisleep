"""The AI's live status ("Searching the help center"), announced from the steps a Turn records."""

import pytest

from apps.agent import bot, http_tools
from apps.agent.turns import status_text
from apps.realtime import bus

from .conftest import assistant, final, tool_call
from .factories import MessageFactory, OrganizationFactory, ToolFactory

pytestmark = pytest.mark.django_db


def ask(body: str, ready: bool = True):
    return MessageFactory(
        body=body, conversation__workspace__organization=OrganizationFactory(ready=ready)
    ).conversation


def statuses(listener) -> list[str]:
    return [e["data"]["text"] for e in listener.events() if e["event"] == "status"]


def test_the_visitor_sees_each_step_then_the_status_clears(llm, listen, monkeypatch):
    conversation = ask("Where is order 1234?")
    ToolFactory(workspace=conversation.workspace, name="get_order_v2", url="https://shop.example.com/api/orders")
    monkeypatch.setattr(http_tools, "run", lambda tool, inputs, visitor: ('{"status": "shipped"}', False))
    llm(assistant(tool_call("get_order_v2", {"id": "1234"})), final("It has shipped."))
    widget = listen(bus.visitor_channel(conversation.visitor_id))

    bot.reply(conversation.id)

    assert statuses(widget) == [
        "Searching the help center",
        "Writing a reply",
        # The workspace's tool by a generic name: its real name is internal.
        "Looking that up",
        "Writing a reply",
        "",
    ]


def test_the_inbox_sees_the_same_status(llm, listen):
    conversation = ask("Hi")
    llm(final("Hello!"))
    inbox = listen(bus.workspace_channel(conversation.workspace_id))
    bot.reply(conversation.id)
    assert statuses(inbox) == ["Searching the help center", "Writing a reply", ""]


def test_the_fallback_announces_its_search(listen):
    conversation = ask("refunds", ready=False)
    widget = listen(bus.visitor_channel(conversation.visitor_id))
    bot.reply(conversation.id)
    assert statuses(widget) == ["Searching the help center", ""]


@pytest.mark.parametrize(
    "kind, name, text",
    [
        ("retrieval", "", "Searching the help center"),
        ("tool", "search_knowledge_base", "Searching the help center"),
        ("tool", "read_playbook", "Checking our guidelines"),
        ("tool", "handoff_to_human", "Getting a teammate"),
        ("tool", "lookup_customer", "Looking that up"),
        ("model", "", "Writing a reply"),
        ("something_new", "", ""),
    ],
)
def test_status_text(kind, name, text):
    assert status_text(kind, name) == text
