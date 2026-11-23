"""What the API publishes on Redis for the widget's and the inbox's live streams."""

import pytest

from apps.conversations.models import Message
from apps.conversations.services import add_message
from apps.realtime import bus, events

from .factories import ConversationFactory, VisitorFactory

# Events go out when the transaction commits; the marker makes that happen at once.
pytestmark = pytest.mark.django_db


@pytest.fixture
def conversation(workspace):
    return ConversationFactory(workspace=workspace, visitor=VisitorFactory(workspace=workspace))


def channels(conversation):
    return bus.visitor_channel(conversation.visitor_id), bus.workspace_channel(conversation.workspace_id)


def test_a_reply_reaches_the_widget_and_the_inbox(conversation, listen):
    visitor_side, team_side = (listen(c) for c in channels(conversation))
    message = add_message(conversation, Message.Sender.AGENT, "Hello!")

    widget_events = visitor_side.events()
    assert [e["event"] for e in widget_events] == ["message", "conversation"]
    assert widget_events[0]["data"]["message"]["id"] == message.id
    assert widget_events[0]["data"]["message"]["body"] == "Hello!"
    # The widget learns a person has taken over, and nothing else about the conversation.
    assert widget_events[1]["data"] == {"id": conversation.id, "human_requested": True}

    inbox_events = team_side.events()
    assert [e["event"] for e in inbox_events] == ["message", "conversation"]
    row = inbox_events[1]["data"]
    assert row["id"] == conversation.id and row["preview"] == "Hello!"
    assert row["visitor"]["id"] == conversation.visitor_id


@pytest.mark.parametrize("sender, is_note", [(Message.Sender.AGENT, True), (Message.Sender.SYSTEM, False)])
def test_notes_and_system_messages_stay_with_the_team(conversation, listen, sender, is_note):
    visitor_side, team_side = (listen(c) for c in channels(conversation))
    add_message(conversation, sender, "Refund approved by finance", is_note=is_note)

    assert "message" not in visitor_side.names()
    assert team_side.names() == ["message", "conversation"]


def test_one_visitor_hears_nothing_of_another(conversation, workspace, listen):
    other = listen(bus.visitor_channel(VisitorFactory(workspace=workspace).id))
    add_message(conversation, Message.Sender.AGENT, "Hello!")
    assert other.events() == []


def test_the_visitor_sending_reaches_the_inbox(conversation, listen, anon):
    team_side = listen(channels(conversation)[1])
    anon.visitor_token = conversation.visitor.token
    response = anon.post(f"/widget/{conversation.workspace.public_key}/messages", {"body": "Where is my order?"})
    assert response.status_code == 200
    events_ = team_side.events()
    sent = [e for e in events_ if e["event"] == "message"]
    assert sent[0]["data"]["message"]["body"] == "Where is my order?"


def test_resolving_tells_the_inbox(conversation, api, listen):
    team_side = listen(channels(conversation)[1])
    api.patch(f"/workspaces/{conversation.workspace_id}/conversations/{conversation.id}", {"status": "resolved"})
    published = team_side.events()
    assert published[-1]["event"] == "conversation"
    assert published[-1]["data"]["status"] == "resolved"


def test_typing_goes_to_the_other_side(conversation, listen):
    visitor_side, team_side = (listen(c) for c in channels(conversation))

    events.typing(conversation, "visitor")
    assert visitor_side.events() == []
    assert team_side.events() == [
        {"event": "typing", "data": {"conversation_id": conversation.id, "sender": "visitor", "name": ""}}
    ]

    events.typing(conversation, "agent", "Priya")
    assert team_side.events() == []
    assert visitor_side.events()[0]["data"]["name"] == "Priya"


def test_without_redis_nothing_is_published(conversation, settings):
    # The default in tests and in a Django run with no REDIS_URL.
    assert bus.client() is None
    add_message(conversation, Message.Sender.AGENT, "Hello!")  # no error


def test_a_redis_failure_does_not_fail_the_request(conversation, monkeypatch):
    import redis

    class Broken:
        def pipeline(self, transaction=False):
            raise redis.ConnectionError("down")

    monkeypatch.setattr(bus, "client", lambda: Broken())
    message = add_message(conversation, Message.Sender.AGENT, "Hello!")
    assert Message.objects.filter(pk=message.pk).exists()
