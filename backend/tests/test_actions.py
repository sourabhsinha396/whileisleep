"""A2UI action events sent back by the widget."""

import pytest

from .conftest import Api
from .factories import ArticleFactory, ConversationFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def chat():
    conversation = ConversationFactory()
    widget = Api(visitor_token=conversation.visitor.token)
    key = conversation.workspace.public_key

    def act(name, surface="s1", **context):
        return widget.post(f"/widget/{key}/actions", {"name": name, "surfaceId": surface, "context": context})

    return conversation, act


def test_open_article(chat):
    conversation, act = chat
    article = ArticleFactory(workspace=conversation.workspace, title="Returns")
    assert act("open_article", articleId=article.id).json()["article"]["title"] == "Returns"


def test_open_article_from_another_workspace(chat):
    _, act = chat
    assert act("open_article", articleId=ArticleFactory().id).status_code == 400


def test_talk_to_human_asks_for_email_with_a_form(chat):
    conversation, act = chat
    act("talk_to_human")
    conversation.refresh_from_db()
    assert conversation.human_requested
    last = conversation.messages.filter(is_note=False).last()
    assert last.form["fields"][0]["type"] == "email"
    components = last.a2ui[1]["updateComponents"]["components"]
    assert any(c["component"] == "TextField" for c in components)

    # Sending it saves the email; no AI is coming, so a thank-you confirms it.
    sent = act("submit_form", surface=last.form["surface_id"], fields={"email": "sofia@example.com"})
    assert sent.status_code == 200
    conversation.visitor.refresh_from_db()
    assert conversation.visitor.email == "sofia@example.com"
    assert conversation.messages.filter(is_note=False).last().body == "Thanks! We'll also reply to sofia@example.com."

    # Pressing again doesn't add more messages.
    count = conversation.messages.count()
    act("talk_to_human")
    assert conversation.messages.count() == count


def test_talk_to_human_skips_the_form_when_email_is_known(chat):
    conversation, act = chat
    conversation.visitor.email = "known@example.com"
    conversation.visitor.save()
    act("talk_to_human")
    assert conversation.messages.filter(is_note=False).last().form is None


def test_legacy_save_email(chat):
    conversation, act = chat
    assert act("save_email", email="sofia@example.com").status_code == 200
    conversation.visitor.refresh_from_db()
    assert conversation.visitor.email == "sofia@example.com"
    assert act("save_email", email="nope").status_code == 400


def test_unknown_action(chat):
    _, act = chat
    assert act("launch_rockets").status_code == 400
