"""Rules (run in code before the AI) and playbooks (instructions the AI loads on demand)."""

from datetime import UTC, datetime

import pytest

from apps.agent import bot, rules
from apps.agent.models import Rule
from apps.conversations import attributes
from apps.conversations.models import Conversation, Message

from .conftest import Api, assistant, final, tool_call
from .factories import (
    AuthTokenFactory,
    ConversationFactory,
    MembershipFactory,
    MessageFactory,
    OrganizationFactory,
    PlaybookFactory,
    RuleFactory,
    VisitorFactory,
    WorkspaceFactory,
    cond,
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
    RuleFactory(workspace=workspace, keywords=["refund", "money back"], instruct="Be extra kind.")
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
    RuleFactory(workspace=workspace, keywords=["lawyer"], handoff=True)
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


# --- What a rule can look at ---


def facts(conversation=None, at=None, **message):
    conversation = conversation or ConversationFactory()
    msg = MessageFactory(conversation=conversation, **{"body": "hi", **message})
    return rules.context_for(conversation, msg, rules.is_first_message(conversation, msg), at)


def test_facts_about_the_message_and_the_page():
    conversation = ConversationFactory(
        visitor__current_url="https://shop.example.com/pricing", visitor__page_title="Pricing"
    )
    context = facts(conversation, body="Need a REFUND", intent="exam_request", intent_data={"exam_code": "SY0-401"})
    assert context["message.text"] == "Need a REFUND"
    assert context["message.intent"] == "exam_request"
    assert context["message.data.exam_code"] == "SY0-401"
    assert context["message.is_first"] is True
    assert context["page.url"] == "https://shop.example.com/pricing" and context["page.title"] == "Pricing"


def test_only_the_first_visitor_message_is_first():
    conversation = ConversationFactory()
    MessageFactory(conversation=conversation, sender=Message.Sender.BOT, body="Hi! How can we help?")
    assert facts(conversation)["message.is_first"] is True
    assert facts(conversation)["message.is_first"] is False


def test_facts_about_the_visitor_and_the_conversation():
    conversation = ConversationFactory(tags=["vip"], human_requested=True)
    attributes.set_attribute(conversation.visitor, "plan", "pro", attributes.Source.HOST)
    attributes.set_attribute(conversation, "topic", "billing", attributes.Source.RULE)
    context = facts(conversation)
    assert context["contact.plan"] == "pro" and context["conversation.topic"] == "billing"
    assert context["contact.verified"] is False
    assert context["conversation.tags"] == ["vip"] and context["conversation.has_human"] is True


def test_time_is_local_to_the_workspace():
    conversation = ConversationFactory(workspace__timezone="Asia/Kolkata")
    # Friday 20:00 UTC is Saturday 01:30 in India.
    context = facts(conversation, at=datetime(2026, 11, 20, 20, 0, tzinfo=UTC))
    assert (context["time.hour"], context["time.weekday"]) == (1, "sat")


@pytest.mark.parametrize(
    ("conditions", "expected"),
    [
        ({"all": [cond("message.intent", "equals", "exam_request")]}, True),
        ({"all": [cond("message.intent", "equals", "other")]}, False),
        ({"all": [cond("message.text", "contains_any", ["refund", "money"])]}, True),
        ({"all": [cond("message.text", "has_word", "fund")]}, False),
        ({"all": [cond("page.url", "contains", "/pricing"), cond("message.is_first", "equals", True)]}, True),
        ({"all": [cond("page.url", "contains", "/pricing"), cond("contact.plan", "equals", "pro")]}, False),
        ({"any": [cond("contact.plan", "equals", "pro"), cond("message.text", "contains", "refund")]}, True),
        ({"not": cond("conversation.tags", "equals", "vip")}, True),
    ],
)
def test_matches(conditions, expected):
    conversation = ConversationFactory(visitor__current_url="https://shop.example.com/pricing")
    context = facts(conversation, body="Need a REFUND", intent="exam_request")
    assert rules.matches(RuleFactory.build(conditions=conditions), context) is expected


def test_an_office_hours_rule(llm):
    """The kind of decision that needs no model: outside 9 to 18, say when we're back."""
    workspace = WorkspaceFactory(organization=OrganizationFactory(ready=True), timezone="Europe/Berlin")
    closed = {
        "any": [cond("time.hour", "lt", 9), cond("time.hour", "gte", 18), cond("time.weekday", "in", ["sat", "sun"])]
    }
    rule = RuleFactory(workspace=workspace, conditions=closed, reply="We're back at 9:00.")
    conversation = ConversationFactory(workspace=workspace)
    message = MessageFactory(conversation=conversation, body="anyone there?")
    night = rules.context_for(conversation, message, True, at=datetime(2026, 11, 23, 22, 0, tzinfo=UTC))
    noon = rules.context_for(conversation, message, True, at=datetime(2026, 11, 23, 11, 0, tzinfo=UTC))
    assert rules.matches(rule, night) and not rules.matches(rule, noon)


# --- Actions ---


def test_actions_run_in_order_and_set_attributes(llm):
    workspace = WorkspaceFactory(organization=OrganizationFactory(ready=True))
    RuleFactory(
        workspace=workspace,
        conditions={"all": [cond("message.text", "has_any_word", ["invoice", "billing"])]},
        actions=[
            {"type": "tag", "value": "billing"},
            {"type": "set_attribute", "scope": "conversation", "key": "topic", "value": "billing"},
            {"type": "set_attribute", "scope": "contact", "key": "segment", "value": "payer"},
            {"type": "instruct", "text": "Link the billing portal for {contact.name}."},
        ],
    )
    visitor = VisitorFactory(workspace=workspace)
    attributes.set_attribute(visitor, "name", "Sofia", attributes.Source.HOST)
    conversation = ConversationFactory(workspace=workspace, visitor=visitor)
    fake = llm(final("Here it is."))

    send(Api(visitor_token=visitor.token), workspace, "Where is my invoice?")

    conversation.refresh_from_db()
    visitor.refresh_from_db()
    assert conversation.tags == ["billing"]
    assert attributes.get(conversation, "topic") == "billing"
    assert attributes.source_of(visitor, "segment") == attributes.Source.RULE
    assert "Link the billing portal for Sofia." in fake.requests[0]["messages"][0]["content"]


def test_a_rule_cannot_overwrite_a_verified_attribute():
    workspace = WorkspaceFactory()
    RuleFactory(
        workspace=workspace,
        actions=[
            {"type": "set_attribute", "scope": "contact", "key": "plan", "value": "free"},
            {"type": "reply", "text": "ok"},
        ],
    )
    visitor = VisitorFactory(workspace=workspace)
    attributes.set_attribute(visitor, "plan", "pro", attributes.Source.VERIFIED)
    ConversationFactory(workspace=workspace, visitor=visitor)
    send(Api(visitor_token=visitor.token), workspace, "x", intent="exam_request")
    visitor.refresh_from_db()
    assert attributes.get(visitor, "plan") == "pro"


def test_a_later_rule_can_use_what_an_earlier_message_set():
    """Attributes are how rules build on each other across messages."""
    workspace = WorkspaceFactory()
    RuleFactory(
        workspace=workspace,
        position=1,
        conditions={"all": [cond("conversation.topic", "equals", "billing"), cond("message.text", "has_word", "yes")]},
        reply="Great, opening the billing form.",
    )
    RuleFactory(
        workspace=workspace,
        position=2,
        conditions={"all": [cond("message.text", "has_word", "invoice")]},
        actions=[
            {"type": "set_attribute", "scope": "conversation", "key": "topic", "value": "billing"},
            {"type": "reply", "text": "Is this about billing?"},
        ],
    )
    widget, _ = widget_for(workspace)
    first = send(widget, workspace, "invoice please").json()["messages"][-1]["body"]
    second = send(widget, workspace, "yes").json()["messages"][-1]["body"]
    assert (first, second) == ("Is this about billing?", "Great, opening the billing form.")


def test_placeholders_fill_from_the_facts_and_stay_short():
    conversation = ConversationFactory()
    attributes.set_attribute(conversation.visitor, "name", "Sofia", attributes.Source.HOST)
    attributes.set_attribute(conversation, "topic", "billing", attributes.Source.RULE)
    context = facts(conversation, intent_data={"exam_name": "Line one\nline two " + "x" * 500})
    filled = rules.fill(
        "Hi {contact.name}, {message.data.exam_name}! About {conversation.topic}. {contact.missing}{nope} {a.b}",
        context,
    )
    assert filled.startswith("Hi Sofia, Line one line two xxx")
    assert "\n" not in filled
    assert "About billing." in filled
    # Unknown attribute: empty. Not a placeholder of ours: left alone.
    assert filled.endswith(". {nope} {a.b}")
    assert len(filled) < 250


def test_older_placeholder_names_still_fill():
    conversation = ConversationFactory()
    attributes.set_attribute(conversation.visitor, "name", "Sofia", attributes.Source.HOST)
    context = facts(conversation, intent_data={"exam_name": "Security+"})
    assert rules.fill("Hi {visitor.name}, {data.exam_name}", context) == "Hi Sofia, Security+"


# --- Trying a rule on past messages ---


def test_backtest_counts_matches_and_shows_examples():
    workspace = WorkspaceFactory()
    conversation = ConversationFactory(workspace=workspace)
    MessageFactory(conversation=conversation, body="I want a refund")
    MessageFactory(conversation=conversation, body="hello")
    MessageFactory(conversation=conversation, sender=Message.Sender.BOT, body="refund policy is...")
    MessageFactory(body="refund in another workspace")
    result = rules.backtest(workspace, {"all": [cond("message.text", "has_word", "refund")]})
    assert (result["checked"], result["matched"]) == (2, 1)
    assert [sample["text"] for sample in result["samples"]] == ["I want a refund"]


def test_backtest_knows_which_message_was_first():
    workspace = WorkspaceFactory()
    conversation = ConversationFactory(workspace=workspace)
    MessageFactory(conversation=conversation, body="first")
    MessageFactory(conversation=conversation, body="second")
    result = rules.backtest(workspace, {"all": [cond("message.is_first", "equals", True)]})
    assert [sample["text"] for sample in result["samples"]] == ["first"]


def test_backtest_endpoint(api, workspace):
    MessageFactory(conversation=ConversationFactory(workspace=workspace), body="refund please")
    path = f"/workspaces/{workspace.id}/rules/backtest"
    tried = api.post(path, {"conditions": {"all": [cond("message.text", "contains", "refund")]}})
    assert tried.status_code == 200 and tried.json()["matched"] == 1
    assert api.post(path, {"conditions": {"all": []}}).status_code == 400
    assert api.post(path, {"conditions": {"all": [cond("secrets.key", "exists")]}}).status_code == 400


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
        "conditions": {"all": [cond("message.intent", "equals", "exam_request")]},
        "actions": [
            {"type": "tag", "value": "exam-request"},
            {"type": "reply", "text": "We'll add {message.data.exam_name} within 12 hours."},
        ],
        "also_when_human": True,
    } | overrides


def test_rule_crud(api, workspace):
    created = api.post(f"/workspaces/{workspace.id}/rules", rule_payload())
    assert created.status_code == 200, created.json()
    rule_id = created.json()["id"]
    assert Rule.objects.get(pk=rule_id).conditions == rule_payload()["conditions"]
    updated = api.put(f"/workspaces/{workspace.id}/rules/{rule_id}", rule_payload(enabled=False))
    assert updated.json()["enabled"] is False
    listed = api.get(f"/workspaces/{workspace.id}/rules").json()
    assert len(listed) == 1 and listed[0]["actions"] == rule_payload()["actions"]
    api.delete(f"/workspaces/{workspace.id}/rules/{rule_id}")
    assert not Rule.objects.exists()


REPLY = {"type": "reply", "text": "Hi"}


@pytest.mark.parametrize(
    ("overrides", "error"),
    [
        ({"conditions": {"all": []}}, "at least one condition"),
        ({"conditions": {"all": [cond("message.text", "matches", ".*")]}}, "Unknown operator"),
        ({"conditions": {"all": [cond("secrets.key", "exists")]}}, "Unknown field"),
        ({"actions": []}, "at least one action"),
        ({"actions": [REPLY, {"type": "instruct", "text": "Be kind"}]}, "not both"),
        ({"actions": [REPLY, REPLY]}, "only one reply"),
        ({"actions": [{"type": "email_ceo"}]}, "needs a type"),
        ({"actions": [{"type": "reply", "text": "  "}]}, "needs text"),
        ({"actions": [{"type": "tag", "value": "x" * 41}]}, "needs a tag"),
        ({"actions": [{"type": "set_attribute", "scope": "galaxy", "key": "a", "value": 1}]}, "needs a scope"),
        ({"actions": [{"type": "set_attribute", "scope": "contact", "key": "Bad Key", "value": 1}]}, "Attribute names"),
        (
            {"actions": [{"type": "set_attribute", "scope": "contact", "key": "email", "value": "nope"}]},
            "can't be stored",
        ),
        ({"actions": [{"type": "handoff"}] * 11}, "at most 10"),
    ],
)
def test_rule_validation(api, workspace, overrides, error):
    response = api.post(f"/workspaces/{workspace.id}/rules", rule_payload(**overrides))
    assert response.status_code == 400 and error in response.json()["detail"], response.json()


def test_only_owners_change_rules(workspace):
    agent = MembershipFactory(workspace=workspace, role="agent")
    as_agent = Api(token=AuthTokenFactory(user=agent.user).key)
    assert as_agent.get(f"/workspaces/{workspace.id}/rules").status_code == 200
    assert as_agent.post(f"/workspaces/{workspace.id}/rules", rule_payload()).status_code == 404


def test_timezone_is_set_and_checked(api, workspace):
    assert api.patch(f"/workspaces/{workspace.id}", {"timezone": "Asia/Kolkata"}).json()["timezone"] == "Asia/Kolkata"
    assert api.patch(f"/workspaces/{workspace.id}", {"timezone": "Mars/Olympus"}).status_code == 400


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
