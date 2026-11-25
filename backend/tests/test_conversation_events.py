"""What conversations announce to other apps (apps.conversations.signals)."""

import pytest

from apps.conversations import services, signals
from apps.conversations.models import Conversation, Message

from .factories import ConversationFactory, RuleFactory, UserFactory, VisitorFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def conversation(workspace):
    return ConversationFactory(workspace=workspace, visitor=VisitorFactory(workspace=workspace))


@pytest.fixture
def path(conversation):
    return f"/workspaces/{conversation.workspace_id}/conversations/{conversation.id}"


@pytest.fixture
def heard():
    events = []

    def listen(event, **kwargs):
        events.append(event)

    signals.happened.connect(listen)
    yield events
    signals.happened.disconnect(listen)


def names(events):
    return [e.name for e in events]


def test_a_message_says_who_wrote_it_and_where_it_came_from(conversation, heard):
    user = UserFactory()
    message = services.reply_as(user, conversation, "Hello", origin="integration:7")
    (event,) = heard
    assert (event.name, event.message, event.by, event.origin) == ("message", message, user, "integration:7")
    assert event.conversation == conversation


def test_a_visitor_writing_to_a_resolved_conversation_reopens_it_first(conversation, heard):
    services.set_status(conversation, Conversation.Status.RESOLVED)
    heard.clear()
    services.add_message(conversation, Message.Sender.VISITOR, "One more thing")
    assert names(heard) == ["reopened", "message"]


def test_a_teammates_reply_reads_the_conversation_and_a_note_does_not(conversation):
    services.add_message(conversation, Message.Sender.VISITOR, "Hello?")
    services.reply_as(UserFactory(), conversation, "Looking into it", is_note=True)
    conversation.refresh_from_db()
    assert conversation.unread
    services.reply_as(UserFactory(), conversation, "Hi!")
    conversation.refresh_from_db()
    assert not conversation.unread


def test_asking_for_a_person_is_announced_once_with_the_reason(conversation, heard):
    services.request_human(conversation, "wants a refund")
    services.request_human(conversation, "again")
    asked = [e for e in heard if e.name == "person_requested"]
    assert [e.data for e in asked] == [{"reason": "wants a refund"}]


def test_a_rule_s_hand_off_is_announced(conversation, anon, workspace, heard):
    RuleFactory(workspace=workspace, keywords=["refund"], handoff=True)
    anon.visitor_token = conversation.visitor.token
    assert anon.post(f"/widget/{workspace.public_key}/messages", {"body": "a refund please"}).status_code == 200
    assert "person_requested" in names(heard)


def test_changes_from_the_inbox_are_announced_with_who_made_them(api, membership, path, heard):
    api.patch(path, {"status": "resolved"})
    api.patch(path, {"status": "open"})
    api.patch(path, {"human_requested": True})
    api.patch(path, {"human_requested": False})
    # Taking a chat from the AI needs no alert: that teammate is already there.
    assert names(heard) == ["resolved", "reopened", "ai_resumed"]
    assert {e.by for e in heard} == {membership.user}


def test_saving_what_is_already_so_announces_nothing(api, path, heard):
    assert api.patch(path, {"status": "open", "human_requested": False}).status_code == 200
    assert heard == []


def test_a_change_that_is_refused_changes_nothing(api, conversation, path, heard):
    assert api.patch(path, {"human_requested": True, "assignee_id": 999999}).status_code == 400
    conversation.refresh_from_db()
    assert not conversation.human_requested and heard == []


def test_answering_takes_the_conversation_but_a_note_does_not(conversation, membership):
    services.reply_as(membership.user, conversation, "note", is_note=True)
    assert conversation.assignee is None
    services.reply_as(membership.user, conversation, "hi")
    assert conversation.assignee == membership.user and conversation.human_requested
