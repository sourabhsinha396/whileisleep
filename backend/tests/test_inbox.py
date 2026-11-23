from datetime import timedelta

import pytest
from django.utils import timezone

from apps.conversations.models import Conversation, Message

from .factories import ConversationFactory, MessageFactory, UserFactory, VisitorFactory

pytestmark = pytest.mark.django_db


def test_list_open_conversations_with_preview(api, workspace):
    conversation = ConversationFactory(workspace=workspace)
    MessageFactory(conversation=conversation, body="Where is my order?")
    MessageFactory(conversation=conversation, body="secret note", is_note=True, sender=Message.Sender.AGENT)
    ConversationFactory(workspace=workspace, status=Conversation.Status.RESOLVED)

    rows = api.get(f"/workspaces/{workspace.id}/conversations").json()

    assert [r["id"] for r in rows] == [conversation.id]
    assert rows[0]["preview"] == "Where is my order?"
    assert len(api.get(f"/workspaces/{workspace.id}/conversations", status="all").json()) == 2


def test_opening_marks_read_and_shows_notes(api, workspace):
    conversation = ConversationFactory(workspace=workspace)
    MessageFactory(conversation=conversation, sender=Message.Sender.AGENT, body="note", is_note=True)
    detail = api.get(f"/workspaces/{workspace.id}/conversations/{conversation.id}").json()
    assert detail["messages"][0]["is_note"] is True
    conversation.refresh_from_db()
    assert conversation.unread is False


def test_reply_assigns_and_silences_the_bot(api, workspace, membership):
    conversation = ConversationFactory(workspace=workspace)
    sent = api.post(f"/workspaces/{workspace.id}/conversations/{conversation.id}/messages", {"body": "On it!"})
    assert sent.json()["sender"] == "agent"
    conversation.refresh_from_db()
    assert conversation.assignee == membership.user
    assert conversation.human_requested is True


def test_note_does_not_silence_the_bot(api, workspace):
    conversation = ConversationFactory(workspace=workspace)
    api.post(f"/workspaces/{workspace.id}/conversations/{conversation.id}/messages", {"body": "hm", "is_note": True})
    conversation.refresh_from_db()
    assert conversation.human_requested is False


def test_resolve(api, workspace):
    conversation = ConversationFactory(workspace=workspace)
    updated = api.patch(f"/workspaces/{workspace.id}/conversations/{conversation.id}", {"status": "resolved"})
    assert updated.json()["status"] == "resolved"


def test_cannot_assign_outsider(api, workspace):
    conversation = ConversationFactory(workspace=workspace)
    outsider = UserFactory()
    response = api.patch(f"/workspaces/{workspace.id}/conversations/{conversation.id}", {"assignee_id": outsider.id})
    assert response.status_code == 400


def test_visitors_online_filter(api, workspace):
    online = VisitorFactory(workspace=workspace)
    VisitorFactory(workspace=workspace, last_seen=timezone.now() - timedelta(minutes=10))
    rows = api.get(f"/workspaces/{workspace.id}/visitors", online="true").json()
    assert [v["id"] for v in rows] == [online.id]
    assert rows[0]["online"] is True
    assert len(api.get(f"/workspaces/{workspace.id}/visitors").json()) == 2


def test_message_a_visitor_first(api, workspace):
    visitor = VisitorFactory(workspace=workspace)
    started = api.post(f"/workspaces/{workspace.id}/visitors/{visitor.id}/conversations", {"body": "Need help?"})
    assert started.status_code == 200
    assert Conversation.objects.get().messages.get().body == "Need help?"
