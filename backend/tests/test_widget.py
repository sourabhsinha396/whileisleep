import pytest

from apps.conversations.models import Conversation, Message, Visitor

from .conftest import Api
from .factories import ArticleFactory, ConversationFactory, MessageFactory, WorkspaceFactory

pytestmark = pytest.mark.django_db


def start(workspace, **page) -> Api:
    widget = Api()
    session = widget.post(f"/widget/{workspace.public_key}/session", {"url": "https://shop.example.com/", **page})
    assert session.status_code == 200
    widget.visitor_token = session.json()["token"]
    return widget


def test_config_is_public():
    workspace = WorkspaceFactory(greeting="Ask us anything")
    assert Api().get(f"/widget/{workspace.public_key}/config").json()["greeting"] == "Ask us anything"


def test_unknown_workspace_key():
    assert Api().get("/widget/ws_nope/config").status_code == 404


def test_session_creates_then_resumes_visitor():
    workspace = WorkspaceFactory()
    widget = start(workspace, title="Home")
    again = widget.post(f"/widget/{workspace.public_key}/session", {"url": "https://shop.example.com/cart"})
    assert again.json()["token"] == widget.visitor_token
    visitor = Visitor.objects.get()
    assert visitor.current_url == "https://shop.example.com/cart"
    assert visitor.is_online


def test_visitor_token_is_per_workspace():
    widget = start(WorkspaceFactory())
    other = WorkspaceFactory()
    assert widget.get(f"/widget/{other.public_key}/messages").status_code == 401


def test_first_message_opens_a_conversation_and_bot_answers():
    workspace = WorkspaceFactory()
    ArticleFactory(workspace=workspace, title="Shipping to Canada", body="We ship to Canada in 5 to 8 days.")
    widget = start(workspace)

    sent = widget.post(f"/widget/{workspace.public_key}/messages", {"body": "Do you ship to Canada?"})

    assert sent.status_code == 200
    senders = [m["sender"] for m in sent.json()["messages"]]
    assert senders == ["visitor", "bot"]
    conversation = Conversation.objects.get()
    assert conversation.unread


def test_bot_stays_quiet_when_ai_is_off():
    workspace = WorkspaceFactory(ai_enabled=False)
    widget = start(workspace)
    sent = widget.post(f"/widget/{workspace.public_key}/messages", {"body": "Hello?"})
    assert [m["sender"] for m in sent.json()["messages"]] == ["visitor"]


def test_messages_hide_internal_notes():
    workspace = WorkspaceFactory()
    widget = start(workspace)
    conversation = ConversationFactory(workspace=workspace, visitor=Visitor.objects.get())
    MessageFactory(conversation=conversation, sender=Message.Sender.AGENT, body="Hi!")
    MessageFactory(conversation=conversation, sender=Message.Sender.AGENT, body="VIP customer", is_note=True)
    MessageFactory(conversation=conversation, sender=Message.Sender.SYSTEM, body="Bot looked up", is_note=True)

    bodies = [m["body"] for m in widget.get(f"/widget/{workspace.public_key}/messages").json()["messages"]]

    assert bodies == ["Hi!"]


def test_messages_after_id_returns_only_new_ones():
    workspace = WorkspaceFactory()
    widget = start(workspace)
    conversation = ConversationFactory(workspace=workspace, visitor=Visitor.objects.get())
    first = MessageFactory(conversation=conversation, sender=Message.Sender.AGENT)
    second = MessageFactory(conversation=conversation, sender=Message.Sender.AGENT)
    got = widget.get(f"/widget/{workspace.public_key}/messages", after=first.id).json()["messages"]
    assert [m["id"] for m in got] == [second.id]


def test_visitor_message_reopens_resolved_conversation():
    workspace = WorkspaceFactory(ai_enabled=False)
    widget = start(workspace)
    ConversationFactory(workspace=workspace, visitor=Visitor.objects.get(), status=Conversation.Status.RESOLVED)
    widget.post(f"/widget/{workspace.public_key}/messages", {"body": "One more thing"})
    assert Conversation.objects.get().status == Conversation.Status.OPEN


def test_article_search_and_read():
    workspace = WorkspaceFactory()
    article = ArticleFactory(workspace=workspace, title="Refund policy", body="Refunds within 30 days.")
    ArticleFactory(workspace=workspace, title="Draft", body="refund secrets", published=False)
    found = Api().get(f"/widget/{workspace.public_key}/articles", q="refund").json()
    assert [a["id"] for a in found] == [article.id]
    assert Api().get(f"/widget/{workspace.public_key}/articles/{article.id}").json()["body"].startswith("Refunds")
