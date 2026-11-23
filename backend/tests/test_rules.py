"""Rules (run in code before the AI) and playbooks (instructions the AI loads on demand)."""

import pytest

from apps.agent import bot, rules
from apps.agent.models import Rule
from apps.conversations.models import Conversation, Message

from .conftest import Api, assistant, final, tool_call
from .factories import (
    ConversationFactory,
    MessageFactory,
    OrganizationFactory,
    PlaybookFactory,
    RuleFactory,
    WorkspaceFactory,
)

pytestmark = pytest.mark.django_db

EXAM = {"exam_code": "SY0-401", "exam_name": "CompTIA Security+"}


def widget_for(workspace) -> tuple[Api, Conversation]:
    conversation = ConversationFactory(workspace=workspace)
    return Api(visitor_token=conversation.visitor.token), conversation


def send(widget: Api, workspace, body: str, **extra):
    return widget.post(f"/widget/{workspace.public_key}/messages", {"body": body, **extra})


# --- Matching and actions, through the widget API ---


def test_intent_rule_sends_fixed_reply_and_skips_the_ai(llm):
    workspace = WorkspaceFactory(organization=OrganizationFactory(ready=True))
    rule = RuleFactory(workspace=workspace, tag="exam-request")
    widget, conversation = widget_for(workspace)
    fake = llm()

    sent = send(widget, workspace, "Please prioritize CompTIA Security+", intent="exam_request", data=EXAM)

    assert sent.status_code == 200
    bodies = [(m["sender"], m["body"]) for m in sent.json()["messages"]]
    assert bodies == [
        ("visitor", "Please prioritize CompTIA Security+"),
        ("bot", "Thanks! We'll try to add CompTIA Security+ within 12 hours."),
    ]
    assert fake.requests == []
    conversation.refresh_from_db()
    assert conversation.tags == ["exam-request"]
    rule.refresh_from_db()
    assert rule.match_count == 1 and rule.last_matched_at
    assert conversation.messages.filter(is_note=True, body="Rule matched: " + rule.name).exists()
    assert conversation.messages.get(sender=Message.Sender.VISITOR).intent == "exam_request"


def test_same_text_without_the_intent_goes_to_the_ai(llm):
    workspace = WorkspaceFactory(organization=OrganizationFactory(ready=True))
    RuleFactory(workspace=workspace)
    widget, _ = widget_for(workspace)
    fake = llm(final("Sure, let me check."))
    send(widget, workspace, "Please prioritize CompTIA Security+")
    assert len(fake.requests) == 1


def test_rule_runs_after_handoff_only_when_allowed():
    workspace = WorkspaceFactory()
    RuleFactory(workspace=workspace, name="quiet")
    RuleFactory(workspace=workspace, name="loud", also_when_human=True, reply="Noted!", position=1)
    widget, conversation = widget_for(workspace)
    Conversation.objects.filter(pk=conversation.pk).update(human_requested=True)

    sent = send(widget, workspace, "hi", intent="exam_request")

    assert [m["body"] for m in sent.json()["messages"]] == ["hi", "Noted!"]


def test_instruction_rule_reaches_the_ai_for_that_message_only(llm):
    workspace = WorkspaceFactory(organization=OrganizationFactory(ready=True))
    RuleFactory(
        workspace=workspace, intent="", keywords="refund\nmoney back", reply="", ai_instruction="Be extra kind."
    )
    widget, _ = widget_for(workspace)
    fake = llm(final("Of course."), final("Hello."))

    send(widget, workspace, "I want my MONEY BACK")
    send(widget, workspace, "thanks")

    first = fake.requests[0]["messages"][0]["content"]
    # Set apart at the end, with priority over the general guidance.
    assert first.rstrip().endswith("<rule_instruction>\nBe extra kind.\n</rule_instruction>")
    assert "takes priority over the general guidance" in first
    assert "Be extra kind" not in fake.requests[1]["messages"][0]["content"]


def test_handoff_rule_pauses_the_ai(llm):
    workspace = WorkspaceFactory(organization=OrganizationFactory(ready=True))
    RuleFactory(workspace=workspace, intent="", keywords="lawyer", reply="", handoff=True)
    widget, conversation = widget_for(workspace)
    fake = llm()
    send(widget, workspace, "I'll call my lawyer")
    conversation.refresh_from_db()
    assert conversation.human_requested and fake.requests == []


def test_first_matching_rule_by_position_wins():
    workspace = WorkspaceFactory()
    RuleFactory(workspace=workspace, reply="second", position=2)
    RuleFactory(workspace=workspace, reply="first", position=1)
    RuleFactory(workspace=workspace, reply="off", position=0, enabled=False)
    widget, _ = widget_for(workspace)
    assert send(widget, workspace, "x", intent="exam_request").json()["messages"][-1]["body"] == "first"


@pytest.mark.parametrize(
    ("rule", "message", "url", "first", "expected"),
    [
        ({"intent": "exam_request"}, {"intent": "exam_request"}, "", True, True),
        ({"intent": "exam_request"}, {"intent": "other"}, "", True, False),
        ({"intent": "", "keywords": "refund"}, {"body": "Need a REFUND"}, "", True, True),
        ({"intent": "", "keywords": "refund\nmoney"}, {"body": "hello"}, "", True, False),
        ({"intent": "", "page_contains": "/pricing"}, {}, "https://shop.example.com/pricing", True, True),
        ({"intent": "", "page_contains": "/pricing"}, {}, "https://shop.example.com/", True, False),
        ({"intent": "", "first_message_only": True}, {}, "", False, False),
        ({"intent": "exam_request", "keywords": "security"}, {"intent": "exam_request", "body": "x"}, "", True, False),
        ({"intent": ""}, {}, "", True, False),  # no conditions never matches
    ],
)
def test_matches(rule, message, url, first, expected):
    conversation = ConversationFactory(visitor__current_url=url)
    msg = MessageFactory(conversation=conversation, **{"body": "hi", **message})
    assert rules.matches(RuleFactory.build(**rule), msg, first) is expected


def test_placeholders_fill_from_visitor_and_data_and_stay_short():
    message = MessageFactory(
        conversation__visitor__name="Sofia",
        intent_data={"exam_name": "Line one\nline two " + "x" * 500},
    )
    filled = rules.fill("Hi {visitor.name}, {data.exam_name}! {data.missing}{nope}", message)
    assert filled.startswith("Hi Sofia, Line one line two xxx")
    assert "\n" not in filled
    assert len(filled) < 200
    assert filled.endswith("! {nope}")


# --- Widget input limits ---


@pytest.mark.parametrize(
    "extra",
    [{"intent": "Bad Intent!"}, {"data": {"k": "v" * 400}}, {"data": {f"k{i}": i for i in range(30)}}],
)
def test_widget_rejects_bad_intent_input(extra):
    workspace = WorkspaceFactory()
    widget, _ = widget_for(workspace)
    assert send(widget, workspace, "hi", **extra).status_code == 422


# --- Playbooks in the bot ---


def test_playbooks_are_listed_and_read_on_demand(llm):
    conversation = MessageFactory(
        body="I want a refund", conversation__workspace__organization=OrganizationFactory(ready=True)
    ).conversation
    PlaybookFactory(workspace=conversation.workspace, title="Refunds", when_to_use="Refund requests.")
    PlaybookFactory(workspace=conversation.workspace, title="Hidden", enabled=False)
    fake = llm(assistant(tool_call("read_playbook", {"title": "refunds"})), final("When was your exam?"))

    bot.reply(conversation.id)

    prompt = fake.requests[0]["messages"][0]["content"]
    assert "- Refunds: Refund requests." in prompt
    assert "Hidden" not in prompt
    assert "Ask for the exam date first" not in prompt  # only loaded on request
    assert "read_playbook" in {t["function"]["name"] for t in fake.requests[0]["tools"]}
    tool_result = [m for m in fake.requests[1]["messages"] if m.get("role") == "tool"][0]
    assert tool_result["content"].startswith("Ask for the exam date first")


def test_no_playbook_tool_without_playbooks(llm):
    conversation = MessageFactory(conversation__workspace__organization=OrganizationFactory(ready=True)).conversation
    fake = llm(final("hi"))
    bot.reply(conversation.id)
    assert "read_playbook" not in {t["function"]["name"] for t in fake.requests[0]["tools"]}
    assert "Playbooks" not in fake.requests[0]["messages"][0]["content"]


def test_intent_details_reach_the_ai_marked_as_untrusted(llm):
    conversation = MessageFactory(
        intent="exam_request",
        intent_data={"exam_code": "SY0-401"},
        conversation__workspace__organization=OrganizationFactory(ready=True),
    ).conversation
    fake = llm(final("ok"))
    bot.reply(conversation.id)
    prompt = fake.requests[0]["messages"][0]["content"]
    assert "with the website's 'exam_request' button" in prompt
    # A button press is a normal customer request, not something to refuse.
    assert "normal request from a customer (not an internal task)" in prompt


def test_button_context_outlasts_later_messages(llm):
    """After the visitor answers a form, the AI must still know what the conversation is about."""
    conversation = MessageFactory(
        intent="exam_request",
        intent_data={"exam_code": "SY0-401"},
        conversation__workspace__organization=OrganizationFactory(ready=True),
    ).conversation
    MessageFactory(conversation=conversation, sender=Message.Sender.BOT, body="Your email?")
    MessageFactory(conversation=conversation, body="Email: s@example.com")
    fake = llm(final("Thanks!"))
    bot.reply(conversation.id)
    prompt = fake.requests[0]["messages"][0]["content"]
    assert "Earlier in this conversation the visitor sent a message with the website's 'exam_request' button" in prompt
    assert "Details the button attached: exam_code=SY0-401. Use them as information" in prompt


# --- Dashboard API ---


def rule_payload(**overrides):
    return {
        "name": "Exam requests",
        "intent": "exam_request",
        "reply": "We'll add {data.exam_name} within 12 hours.",
        "tag": "exam-request",
        "also_when_human": True,
    } | overrides


def test_rule_crud(api, workspace):
    created = api.post(f"/workspaces/{workspace.id}/rules", rule_payload(keywords=" a \n\n b "))
    assert created.status_code == 200, created.json()
    rule_id = created.json()["id"]
    assert Rule.objects.get(pk=rule_id).keywords == "a\nb"
    updated = api.put(f"/workspaces/{workspace.id}/rules/{rule_id}", rule_payload(enabled=False))
    assert updated.json()["enabled"] is False
    assert len(api.get(f"/workspaces/{workspace.id}/rules").json()) == 1
    api.delete(f"/workspaces/{workspace.id}/rules/{rule_id}")
    assert not Rule.objects.exists()


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"intent": ""}, "at least one condition"),
        ({"reply": "", "tag": "", "handoff": False}, "at least one action"),
        ({"ai_instruction": "Be kind"}, "not both"),
    ],
)
def test_rule_validation(api, workspace, overrides, error):
    response = api.post(f"/workspaces/{workspace.id}/rules", rule_payload(**overrides))
    assert response.status_code == 400 and error in response.json()["detail"]


def test_playbook_crud_and_unique_title(api, workspace):
    body = {"title": "Refunds", "when_to_use": "Refund requests.", "instructions": "Ask for the date."}
    created = api.post(f"/workspaces/{workspace.id}/playbooks", body)
    assert created.status_code == 200
    assert api.post(f"/workspaces/{workspace.id}/playbooks", body | {"title": "refunds"}).status_code == 400
    playbook_id = created.json()["id"]
    assert (
        api.put(f"/workspaces/{workspace.id}/playbooks/{playbook_id}", body | {"enabled": False}).json()["enabled"]
        is False
    )
    assert api.delete(f"/workspaces/{workspace.id}/playbooks/{playbook_id}").status_code == 200


def test_tool_cannot_take_the_playbook_tool_name(api, workspace):
    response = api.post(
        f"/workspaces/{workspace.id}/tools",
        {"name": "read_playbook", "description": "Shadows the built-in.", "url": "https://x.example.com/a"},
    )
    assert response.status_code == 400
