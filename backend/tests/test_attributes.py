"""Attributes: named values about a visitor or a conversation, each with its source."""

import pytest

from apps.agent import bot
from apps.conversations import attributes
from apps.conversations.attributes import Source
from apps.conversations.models import Visitor

from .conftest import Api
from .factories import ConversationFactory, VisitorFactory, WorkspaceFactory

pytestmark = pytest.mark.django_db


def test_set_and_get_with_source():
    visitor = VisitorFactory()
    assert attributes.set_attribute(visitor, "plan", "pro", Source.HOST)
    visitor.refresh_from_db()
    assert attributes.get(visitor, "plan") == "pro"
    assert attributes.source_of(visitor, "plan") == Source.HOST
    assert attributes.get(visitor, "missing") is None
    assert attributes.get(visitor, "missing", "free") == "free"


def test_name_and_email_also_fill_their_columns():
    visitor = VisitorFactory()
    changed = attributes.set_many(visitor, {"name": "Sofia  Rossi", "email": "Sofia@Example.com"}, Source.VISITOR)
    assert changed == ["name", "email"]
    visitor = Visitor.objects.get(pk=visitor.pk)
    assert (visitor.name, visitor.email) == ("Sofia Rossi", "sofia@example.com")


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("Plan", "pro"),  # keys are lowercase
        ("9lives", "x"),
        ("has space", "x"),
        ("plan", ""),  # nothing to store
        ("plan", None),
        ("plan", ["a"]),  # only single values
        ("plan", {"a": 1}),
        ("email", "not-an-email"),
    ],
)
def test_bad_keys_and_values_are_skipped(key, value):
    visitor = VisitorFactory()
    assert attributes.set_many(visitor, {key: value}, Source.HOST) == []
    assert visitor.attributes == {}


def test_numbers_and_booleans_keep_their_type():
    conversation = ConversationFactory()
    attributes.set_many(conversation, {"seats": 12, "trial": False, "price": 9.5}, Source.RULE)
    assert attributes.flat(conversation) == {
        "conversation.seats": 12,
        "conversation.trial": False,
        "conversation.price": 9.5,
    }


def test_long_text_is_cut_and_whitespace_collapsed():
    visitor = VisitorFactory()
    attributes.set_attribute(visitor, "note", "a\n\n b " + "x" * 500, Source.HOST)
    assert attributes.get(visitor, "note").startswith("a b xxx")
    assert len(attributes.get(visitor, "note")) == attributes.MAX_VALUE_CHARS


def test_a_less_trusted_source_cannot_overwrite_a_more_trusted_one():
    visitor = VisitorFactory()
    attributes.set_attribute(visitor, "email", "real@example.com", Source.VERIFIED)
    # The visitor types someone else's address into a form; the AI "extracts" another.
    assert not attributes.set_attribute(visitor, "email", "victim@example.com", Source.VISITOR)
    assert not attributes.set_attribute(visitor, "email", "other@example.com", Source.AI)
    assert not attributes.set_attribute(visitor, "email", "teammate@example.com", Source.AGENT)
    visitor = Visitor.objects.get(pk=visitor.pk)
    assert visitor.email == "real@example.com"
    assert attributes.is_verified(visitor, "email")


def test_the_same_or_a_more_trusted_source_can_overwrite():
    visitor = VisitorFactory()
    attributes.set_attribute(visitor, "email", "typo@example.com", Source.VISITOR)
    assert attributes.set_attribute(visitor, "email", "fixed@example.com", Source.VISITOR)
    assert attributes.set_attribute(visitor, "email", "signed@example.com", Source.VERIFIED)
    assert attributes.get(visitor, "email") == "signed@example.com"


def test_the_ai_cannot_overwrite_what_the_visitor_typed():
    conversation = ConversationFactory()
    attributes.set_attribute(conversation, "order_number", "A-100", Source.VISITOR)
    assert not attributes.set_attribute(conversation, "order_number", "A-999", Source.AI)
    assert attributes.get(conversation, "order_number") == "A-100"


def test_setting_the_same_value_again_changes_nothing():
    visitor = VisitorFactory()
    attributes.set_attribute(visitor, "plan", "pro", Source.HOST)
    assert attributes.set_many(visitor, {"plan": "pro"}, Source.HOST) == []


def test_there_is_a_cap_on_how_many_attributes_fit():
    visitor = VisitorFactory()
    attributes.set_many(visitor, {f"k{n}": n for n in range(attributes.MAX_KEYS + 5)}, Source.HOST)
    assert len(visitor.attributes) == attributes.MAX_KEYS
    # Existing keys can still be updated when full.
    assert attributes.set_attribute(visitor, "k0", "new", Source.HOST)


def test_remove_clears_the_column_too():
    visitor = VisitorFactory()
    attributes.set_attribute(visitor, "email", "a@example.com", Source.VISITOR)
    assert attributes.remove(visitor, "email")
    visitor = Visitor.objects.get(pk=visitor.pk)
    assert visitor.email == "" and visitor.attributes == {}
    assert not attributes.remove(visitor, "email")


def test_flat_names_both_scopes():
    conversation = ConversationFactory()
    attributes.set_attribute(conversation.visitor, "plan", "pro", Source.VERIFIED)
    attributes.set_attribute(conversation, "topic", "billing", Source.RULE)
    assert attributes.flat(conversation) == {"contact.plan": "pro", "conversation.topic": "billing"}


# --- Where attributes come from ---


def test_identify_stores_what_the_host_page_says_as_unverified():
    workspace = WorkspaceFactory()
    session = Api().post(
        f"/widget/{workspace.public_key}/session",
        {"name": "Sofia", "email": "sofia@example.com", "attributes": {"plan": "pro", "seats": 3}},
    )
    assert session.status_code == 200
    visitor = Visitor.objects.get()
    assert visitor.email == "sofia@example.com"
    assert attributes.get(visitor, "plan") == "pro" and attributes.get(visitor, "seats") == 3
    assert {attributes.source_of(visitor, key) for key in ("name", "email", "plan")} == {Source.HOST}


def test_a_heartbeat_without_details_keeps_what_we_know():
    workspace = WorkspaceFactory()
    widget = Api()
    token = widget.post(f"/widget/{workspace.public_key}/session", {"email": "sofia@example.com"}).json()["token"]
    Api(visitor_token=token).post(f"/widget/{workspace.public_key}/session", {"url": "https://shop.example.com/x"})
    assert Visitor.objects.get().email == "sofia@example.com"


# --- What the AI is told ---


def test_the_ai_sees_attributes_but_not_private_values():
    conversation = ConversationFactory()
    attributes.set_many(conversation.visitor, {"plan": "pro", "phone": "+44 20 7946 0000"}, Source.HOST)
    attributes.set_attribute(conversation, "order_number", "A-100", Source.VISITOR)
    facts = "\n".join(bot.conversation_facts(conversation))
    assert "We know the visitor's plan: pro." in facts
    assert "We know this conversation's order number: A-100." in facts
    assert "We already have the visitor's phone" in facts
    assert "7946" not in facts


# --- Dashboard ---


def test_inbox_shows_attributes_with_their_source(api, workspace):
    conversation = ConversationFactory(workspace=workspace)
    attributes.set_attribute(conversation.visitor, "plan", "pro", Source.VERIFIED)
    attributes.set_attribute(conversation, "topic", "billing", Source.RULE)
    row = api.get(f"/workspaces/{workspace.id}/conversations/{conversation.id}").json()
    assert row["attributes"] == [{"key": "topic", "value": "billing", "source": "rule"}]
    assert row["visitor"]["attributes"] == [{"key": "plan", "value": "pro", "source": "verified"}]


def test_a_teammate_can_set_and_remove_attributes(api, workspace):
    conversation = ConversationFactory(workspace=workspace)
    visitor = conversation.visitor
    base = f"/workspaces/{workspace.id}/visitors/{visitor.id}/attributes"
    saved = api.put(f"{base}/company", {"value": "Acme"})
    assert saved.json() == [{"key": "company", "value": "Acme", "source": "agent"}]
    assert api.delete(f"{base}/company").json() == []

    on_conversation = f"/workspaces/{workspace.id}/conversations/{conversation.id}/attributes"
    assert api.put(f"{on_conversation}/priority", {"value": 2}).json() == [
        {"key": "priority", "value": 2, "source": "agent"}
    ]
    assert api.delete(f"{on_conversation}/priority").json() == []


def test_a_teammate_cannot_change_a_verified_value(api, workspace):
    visitor = VisitorFactory(workspace=workspace)
    attributes.set_attribute(visitor, "email", "real@example.com", Source.VERIFIED)
    response = api.put(f"/workspaces/{workspace.id}/visitors/{visitor.id}/attributes/email", {"value": "x@example.com"})
    assert response.status_code == 400 and "verified" in response.json()["detail"]


def test_bad_attribute_names_and_values_are_rejected(api, workspace):
    visitor = VisitorFactory(workspace=workspace)
    base = f"/workspaces/{workspace.id}/visitors/{visitor.id}/attributes"
    assert api.put(f"{base}/Bad-Name", {"value": "x"}).status_code == 400
    assert api.put(f"{base}/email", {"value": "nope"}).status_code == 400


def test_attributes_of_another_workspace_are_out_of_reach(api):
    visitor = VisitorFactory()
    path = f"/workspaces/{visitor.workspace_id}/visitors/{visitor.id}/attributes/plan"
    assert api.put(path, {"value": "pro"}).status_code == 404
