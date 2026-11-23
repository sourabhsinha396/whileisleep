"""Typing indicators: a throttled POST from each side, heard live by the other."""

import pytest

from apps.realtime import bus

from .conftest import Api
from .factories import AuthTokenFactory, ConversationFactory, MembershipFactory, UserFactory, VisitorFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def conversation(workspace):
    return ConversationFactory(workspace=workspace, visitor=VisitorFactory(workspace=workspace))


def typing_events(listener):
    return [e["data"] for e in listener.events() if e["event"] == "typing"]


def test_the_visitor_typing_reaches_the_inbox_once_per_burst(conversation, anon, listen):
    inbox = listen(bus.workspace_channel(conversation.workspace_id))
    anon.visitor_token = conversation.visitor.token
    path = f"/widget/{conversation.workspace.public_key}/typing"

    assert anon.post(path).status_code == 200
    assert anon.post(path).status_code == 200  # within the throttle window: not sent again

    assert typing_events(inbox) == [{"conversation_id": conversation.id, "sender": "visitor", "name": ""}]


def test_a_visitor_without_a_conversation_types_into_nothing(workspace, anon, listen):
    visitor = VisitorFactory(workspace=workspace)
    inbox = listen(bus.workspace_channel(workspace.id))
    anon.visitor_token = visitor.token
    assert anon.post(f"/widget/{workspace.public_key}/typing").status_code == 200
    assert inbox.events() == []


def test_typing_needs_the_visitor_token(conversation, anon):
    assert anon.post(f"/widget/{conversation.workspace.public_key}/typing").status_code == 401


def test_a_teammate_typing_reaches_the_widget_with_their_first_name(conversation, api, membership, listen):
    membership.user.first_name = "Priya"
    membership.user.save()
    widget = listen(bus.visitor_channel(conversation.visitor_id))

    response = api.post(f"/workspaces/{conversation.workspace_id}/conversations/{conversation.id}/typing")

    assert response.status_code == 200
    assert typing_events(widget) == [{"conversation_id": conversation.id, "sender": "agent", "name": "Priya"}]


def test_two_teammates_are_throttled_separately(conversation, api, listen):
    widget = listen(bus.visitor_channel(conversation.visitor_id))
    colleague = UserFactory(first_name="Sam")
    MembershipFactory(user=colleague, workspace=conversation.workspace, role="agent")
    other = Api(token=AuthTokenFactory(user=colleague).key)

    path = f"/workspaces/{conversation.workspace_id}/conversations/{conversation.id}/typing"
    api.post(path)
    other.post(path)
    assert len(typing_events(widget)) == 2


def test_only_members_can_send_typing(conversation):
    stranger = Api(token=AuthTokenFactory().key)
    response = stranger.post(f"/workspaces/{conversation.workspace_id}/conversations/{conversation.id}/typing")
    assert response.status_code == 404
