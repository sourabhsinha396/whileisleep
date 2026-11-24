"""The "Get started" guide: each step is done when the thing itself is there."""

import pytest

from apps.conversations.models import Message

from .conftest import Api
from .factories import (
    ArticleFactory,
    AuthTokenFactory,
    ConversationFactory,
    MembershipFactory,
    MessageFactory,
    VisitorFactory,
    WorkspaceFactory,
)

pytestmark = pytest.mark.django_db


def done(api, workspace) -> list[str]:
    response = api.get(f"/workspaces/{workspace.id}/setup")
    assert response.status_code == 200
    return [step["key"] for step in response.json() if step["done"]]


def test_a_new_workspace_has_every_step_ahead_of_it(api, workspace):
    assert api.get(f"/workspaces/{workspace.id}/setup").json() == [
        {"key": "install", "done": False},
        {"key": "ai", "done": False},
        {"key": "article", "done": False},
        {"key": "chat", "done": False},
        {"key": "storage", "done": False},
    ]


def test_installed_once_the_widget_loads_on_a_site(api, anon, workspace):
    anon.post(f"/widget/{workspace.public_key}/session", {"url": "https://shop.example.com/"})
    assert done(api, workspace) == ["install"]


def test_the_test_page_is_not_an_installation(api, anon, workspace):
    url = f"https://app.example.com/demo?key={workspace.public_key}"
    anon.post(f"/widget/{workspace.public_key}/session", {"url": url})
    anon.post(f"/widget/{workspace.public_key}/session", {"url": ""})
    assert done(api, workspace) == []
    # A customer's own page called /demo is.
    anon.post(f"/widget/{workspace.public_key}/session", {"url": "https://shop.example.com/demo"})
    assert done(api, workspace) == ["install"]


def test_ai_needs_both_a_key_and_a_model(api, workspace):
    api.patch("/organization", {"openrouter_api_key": "sk-or-v1-abcdefgh1234"})
    assert done(api, workspace) == []
    api.patch("/organization", {"llm_model": "x/y"})
    assert done(api, workspace) == ["ai"]


def test_a_draft_article_does_not_count(api, workspace):
    article = ArticleFactory(workspace=workspace, published=False)
    assert done(api, workspace) == []
    article.published = True
    article.save()
    assert done(api, workspace) == ["article"]


def test_chatted_once_a_visitor_writes(api, workspace):
    visitor = VisitorFactory(workspace=workspace, current_url="")
    conversation = ConversationFactory(workspace=workspace, visitor=visitor)
    MessageFactory(conversation=conversation, sender=Message.Sender.AGENT)
    assert done(api, workspace) == []
    MessageFactory(conversation=conversation, sender=Message.Sender.VISITOR)
    assert done(api, workspace) == ["chat"]


def test_another_workspace_does_not_count(api, workspace):
    other = WorkspaceFactory()
    ArticleFactory(workspace=other)
    MessageFactory(conversation__workspace=other)
    assert done(api, workspace) == []


def test_only_members_see_it(workspace):
    agent = MembershipFactory(workspace=workspace, role="agent").user
    assert Api(token=AuthTokenFactory(user=agent).key).get(f"/workspaces/{workspace.id}/setup").status_code == 200
    stranger = MembershipFactory().user
    assert Api(token=AuthTokenFactory(user=stranger).key).get(f"/workspaces/{workspace.id}/setup").status_code == 404
    assert Api().get(f"/workspaces/{workspace.id}/setup").status_code == 401
