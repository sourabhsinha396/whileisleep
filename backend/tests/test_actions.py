"""A2UI action events sent back by the widget."""

import pytest

from apps.agent import a2ui

from .conftest import Api
from .factories import ArticleFactory, ConversationFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def chat():
    conversation = ConversationFactory()
    widget = Api(visitor_token=conversation.visitor.token)
    key = conversation.workspace.public_key

    def act(name, **context):
        return widget.post(f"/widget/{key}/actions", {"name": name, "surfaceId": "s1", "context": context})

    return conversation, act


def test_open_article(chat):
    conversation, act = chat
    article = ArticleFactory(workspace=conversation.workspace, title="Returns")
    assert act("open_article", articleId=article.id).json()["article"]["title"] == "Returns"


def test_open_article_from_another_workspace(chat):
    _, act = chat
    assert act("open_article", articleId=ArticleFactory().id).status_code == 400


def test_talk_to_human_asks_for_email(chat):
    conversation, act = chat
    act("talk_to_human")
    conversation.refresh_from_db()
    assert conversation.human_requested
    last = conversation.messages.filter(is_note=False).last()
    components = last.a2ui[1]["updateComponents"]["components"]
    assert any(c["component"] == "TextField" for c in components)
    # Pressing again doesn't add more messages.
    count = conversation.messages.count()
    act("talk_to_human")
    assert conversation.messages.count() == count


def test_save_email(chat):
    conversation, act = chat
    assert act("save_email", email="sofia@example.com").status_code == 200
    conversation.visitor.refresh_from_db()
    assert conversation.visitor.email == "sofia@example.com"


def test_save_bad_email(chat):
    _, act = chat
    assert act("save_email", email="nope").status_code == 400


def test_unknown_action(chat):
    _, act = chat
    assert act("launch_rockets").status_code == 400


def test_surface_shape_follows_a2ui_v1():
    messages = a2ui.email_form("email_1")
    assert messages[0] == {
        "version": "1.0",
        "createSurface": {"surfaceId": "email_1", "catalogId": a2ui.CATALOG_ID, "dataModel": {"email": ""}},
    }
    components = messages[1]["updateComponents"]["components"]
    ids = {c["id"] for c in components}
    assert "root" in ids
    # Every child reference points at a component in the surface.
    for component in components:
        for child in component.get("children", []) + ([component["child"]] if "child" in component else []):
            assert child in ids
