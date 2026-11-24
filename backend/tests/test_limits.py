"""Rate limits, AI caps, the history window, pinned facts, and fresh conversations."""

from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.agent import bot, forms
from apps.conversations import limits
from apps.conversations.models import Conversation, Message

from .conftest import Api, final
from .factories import ConversationFactory, MessageFactory, OrganizationFactory, VisitorFactory, WorkspaceFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def low_limits(settings):
    settings.RATE_LIMITS = {
        "messages_per_visitor_per_minute": 3,
        "messages_per_ip_per_minute": 5,
        "new_visitors_per_ip_per_hour": 2,
    }


def send(visitor, body="hi"):
    widget = Api(visitor_token=visitor.token)
    return widget.post(f"/widget/{visitor.workspace.public_key}/messages", {"body": body})


# --- Rate limits ---


def test_visitor_message_rate(low_limits):
    visitor = VisitorFactory(workspace__ai_enabled=False)
    assert [send(visitor).status_code for _ in range(4)] == [200, 200, 200, 429]
    assert "too quickly" in send(visitor).json()["detail"]


def test_ip_limit_catches_rotating_visitors(low_limits):
    workspace = WorkspaceFactory(ai_enabled=False)
    codes = [send(VisitorFactory(workspace=workspace)).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


def test_new_visitors_per_ip(low_limits):
    workspace = WorkspaceFactory()
    codes = [Api().post(f"/widget/{workspace.public_key}/session", {}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_a_forged_forwarded_header_does_not_dodge_the_ip_limit(low_limits):
    workspace = WorkspaceFactory()
    codes = [
        Client()
        .post(
            f"/api/v1/widget/{workspace.public_key}/session",
            data="{}",
            content_type="application/json",
            headers={"X-Forwarded-For": f"198.51.100.{n}"},
        )
        .status_code
        for n in range(3)
    ]
    assert codes == [200, 200, 429]


def test_returning_visitor_is_not_a_new_visitor(low_limits):
    workspace = WorkspaceFactory()
    first = Api().post(f"/widget/{workspace.public_key}/session", {}).json()["token"]
    returning = Api(visitor_token=first)
    assert all(returning.post(f"/widget/{workspace.public_key}/session", {}).status_code == 200 for _ in range(5))


def test_ai_cap_per_visitor_hands_off_to_a_person(llm):
    visitor = VisitorFactory(
        workspace__organization=OrganizationFactory(ready=True), workspace__ai_replies_per_visitor=2
    )
    fake = llm(final("one"), final("two"))
    send(visitor, "q1")
    send(visitor, "q2")
    reply = send(visitor, "q3").json()["messages"][-1]["body"]
    assert len(fake.requests) == 2
    assert reply == "Thanks! A teammate will reply here soon."
    conversation = Conversation.objects.get(visitor=visitor)
    assert conversation.human_requested
    assert conversation.messages.filter(is_note=True, body__contains="daily AI reply limit").exists()


def test_ai_cap_per_workspace(llm):
    workspace = WorkspaceFactory(organization=OrganizationFactory(ready=True), ai_replies_per_day=3)
    fake = llm(final("a"), final("b"), final("c"))
    for _ in range(4):
        send(VisitorFactory(workspace=workspace))
    assert len(fake.requests) == 3


def test_a_visitor_past_their_cap_uses_up_nothing_of_the_workspaces():
    conversation = ConversationFactory(workspace__ai_replies_per_visitor=1, workspace__ai_replies_per_day=2)
    assert [limits.allow_ai_reply(conversation) for _ in range(4)] == [True, False, False, False]
    other = ConversationFactory(workspace=conversation.workspace)
    assert limits.allow_ai_reply(other)


def test_the_organizations_cap_counts_all_its_workspaces():
    organization = OrganizationFactory(ai_replies_per_day=2)
    allowed = [
        limits.allow_ai_reply(ConversationFactory(workspace=WorkspaceFactory(organization=organization)))
        for _ in range(3)
    ]
    assert allowed == [True, True, False]
    assert limits.allow_ai_reply(ConversationFactory())


def test_a_workspace_past_its_cap_uses_up_nothing_of_the_organizations():
    organization = OrganizationFactory(ai_replies_per_day=2)
    small = WorkspaceFactory(organization=organization, ai_replies_per_day=1)
    assert [limits.allow_ai_reply(ConversationFactory(workspace=small)) for _ in range(4)] == [
        True,
        False,
        False,
        False,
    ]
    assert limits.allow_ai_reply(ConversationFactory(workspace=WorkspaceFactory(organization=organization)))


def test_the_organizations_owner_sets_and_removes_its_cap(api):
    assert api.get("/organization").json()["ai_replies_per_day"] is None
    assert api.patch("/organization", {"ai_replies_per_day": 500}).json()["ai_replies_per_day"] == 500
    # Saving something else leaves it.
    assert api.patch("/organization", {"name": "Acme"}).json()["ai_replies_per_day"] == 500
    assert api.patch("/organization", {"ai_replies_per_day": 0}).status_code == 422
    assert api.patch("/organization", {"ai_replies_per_day": None}).json()["ai_replies_per_day"] is None


def test_owners_set_the_ai_caps(api, workspace):
    path = f"/workspaces/{workspace.id}"
    assert (workspace.ai_replies_per_visitor, workspace.ai_replies_per_day) == (50, 2000)
    saved = api.patch(path, {"ai_replies_per_visitor": 5, "ai_replies_per_day": 100}).json()
    assert (saved["ai_replies_per_visitor"], saved["ai_replies_per_day"]) == (5, 100)
    for bad in (0, -1, 1.5, "many", 1_000_001):
        assert api.patch(path, {"ai_replies_per_day": bad}).status_code == 422
    assert api.patch(path, {"ai_replies_per_day": None}).json()["ai_replies_per_day"] == 100


def test_without_an_llm_there_is_no_ai_cap():
    visitor = VisitorFactory(workspace__ai_replies_per_visitor=1)
    for i in range(3):
        assert send(visitor, f"q{i}").json()["messages"][-1]["sender"] == "bot"
    assert not Conversation.objects.get(visitor=visitor).human_requested


# --- History window ---


def test_history_keeps_recent_turns_within_the_budget(settings):
    settings.HISTORY_BUDGET_CHARS = 250
    settings.HISTORY_MIN_MESSAGES = 2
    conversation = ConversationFactory()
    for i in range(10):
        sender = Message.Sender.VISITOR if i % 2 == 0 else Message.Sender.BOT
        MessageFactory(conversation=conversation, sender=sender, body=f"{i}:" + "x" * 48)
    MessageFactory(conversation=conversation, body="latest question")
    kept = [m.body.split(":")[0] for m in bot.recent_messages(conversation)]
    assert kept == ["6", "7", "8", "9", "latest question"]


def test_history_always_keeps_the_last_few_and_clips_huge_messages(settings):
    settings.HISTORY_BUDGET_CHARS = 10
    settings.HISTORY_MIN_MESSAGES = 2
    settings.HISTORY_MESSAGE_CHARS = 20
    conversation = ConversationFactory()
    MessageFactory(conversation=conversation, body="old")
    MessageFactory(conversation=conversation, sender=Message.Sender.BOT, body="y" * 100)
    MessageFactory(conversation=conversation, body="z" * 100)
    # Kept: the last two messages (over budget, but the minimum), each clipped. The bot's goes
    # too, because a history must start with the visitor.
    assert [m.body[:1] for m in bot.recent_messages(conversation)] == ["y", "z"]
    assert bot.chat_history(conversation) == [{"role": "user", "content": "z" * 20 + " …[cut]"}]


# --- Pinned facts ---


def test_facts_pin_who_where_and_what(llm):
    conversation = ConversationFactory(
        workspace__organization=OrganizationFactory(ready=True),
        visitor__name="Sofia",
        visitor__email="sofia@example.com",
        visitor__current_url="https://shop.example.com/exams?q=cloud",
        visitor__page_title="Exams",
        tags=["exam-request"],
    )
    MessageFactory(
        conversation=conversation, body="Add Cloud+", intent="exam_request", intent_data={"exam_code": "CV0-001"}
    )
    ui, meta = forms.attach(
        forms.normalize({"title": "Pick a level", "fields": [{"name": "level", "label": "Level", "type": "text"}]})
    )
    MessageFactory(conversation=conversation, sender=Message.Sender.BOT, body="Which level?", a2ui=ui, form=meta)
    MessageFactory(conversation=conversation, body="hmm")
    fake = llm(final("ok"))

    bot.reply(conversation.id)

    prompt = fake.requests[0]["messages"][0]["content"]
    facts = prompt.split("## About this conversation\n", 1)[1]
    assert "- The visitor's name is Sofia." in facts
    assert "- We already have the visitor's email; don't ask for it again." in facts
    assert "sofia@example.com" not in prompt  # the address itself stays out of the prompt
    assert "- They are on this page: Exams (https://shop.example.com/exams?q=cloud)." in facts
    assert "Earlier in this conversation the visitor sent a message with the website's 'exam_request' button" in facts
    assert 'Your last message showed a form ("Pick a level") the visitor hasn\'t sent yet.' in facts
    assert "- Tags on this conversation: exam-request." in facts


def test_facts_when_we_know_little(llm):
    conversation = MessageFactory(
        conversation__workspace__organization=OrganizationFactory(ready=True), conversation__visitor__current_url=""
    ).conversation
    fake = llm(final("ok"))
    bot.reply(conversation.id)
    facts = fake.requests[0]["messages"][0]["content"].split("## About this conversation\n", 1)[1]
    assert "We don't have the visitor's email yet." in facts
    assert "name is" not in facts and "page" not in facts


# --- Fresh conversations ---


def test_writing_after_a_quiet_day_starts_a_new_conversation(settings):
    settings.CONVERSATION_IDLE_HOURS = 24
    visitor = VisitorFactory(workspace__ai_enabled=False)
    old = ConversationFactory(workspace=visitor.workspace, visitor=visitor)
    Conversation.objects.filter(pk=old.pk).update(last_message_at=timezone.now() - timedelta(hours=25))

    send(visitor, "back again")

    newest = Conversation.objects.filter(visitor=visitor).order_by("-id").first()
    assert newest.pk != old.pk
    assert list(newest.messages.values_list("body", flat=True)) == ["back again"]


def test_writing_within_the_day_continues_the_conversation():
    visitor = VisitorFactory(workspace__ai_enabled=False)
    current = ConversationFactory(workspace=visitor.workspace, visitor=visitor)
    send(visitor, "one more thing")
    assert Conversation.objects.filter(visitor=visitor).count() == 1
    assert current.messages.get().body == "one more thing"
