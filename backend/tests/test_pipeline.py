"""The reply pipeline: which stage answers a visitor message, and the Turn it leaves behind."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.agent import bot, openrouter, pipeline
from apps.agent.models import Turn
from apps.agent.turns import Recorder
from apps.conversations.models import Conversation, Message

from .conftest import Api, assistant, final, tool_call
from .factories import (
    ArticleFactory,
    ConversationFactory,
    MessageFactory,
    OrganizationFactory,
    RuleFactory,
    ToolFactory,
    VisitorFactory,
    WorkspaceFactory,
)

pytestmark = pytest.mark.django_db


def workspace_with_llm(**fields):
    return WorkspaceFactory(organization=OrganizationFactory(ready=True), **fields)


def send(visitor, body="Do you ship to Canada?", **extra):
    widget = Api(visitor_token=visitor.token)
    return widget.post(f"/widget/{visitor.workspace.public_key}/messages", {"body": body, **extra})


def only_turn() -> Turn:
    return Turn.objects.get()


# --- Stage 1: rules ---


def test_a_rule_with_a_fixed_reply_answers_without_the_model(llm):
    workspace = workspace_with_llm()
    rule = RuleFactory(workspace=workspace, keywords=["opening hours"], reply="We're open 9 to 5.")
    fake = llm()

    send(VisitorFactory(workspace=workspace), "What are your opening hours?")

    turn = only_turn()
    assert turn.stage == Turn.Stage.RULE and turn.rule == rule
    assert turn.reply.body == "We're open 9 to 5."
    assert turn.trigger.body == "What are your opening hours?"
    assert (turn.llm_calls, turn.input_tokens, turn.cost) == (0, 0, None)
    assert fake.requests == []


def test_a_rule_that_only_instructs_still_goes_to_the_ai_and_is_remembered(llm):
    workspace = workspace_with_llm()
    rule = RuleFactory(workspace=workspace, keywords=["refund"], instruct="Be brief.")
    fake = llm(final("Refunds take 5 days."))

    send(VisitorFactory(workspace=workspace), "refund?")

    turn = only_turn()
    assert turn.stage == Turn.Stage.AI and turn.rule == rule
    assert "Be brief." in fake.requests[0]["messages"][0]["content"]


# --- Stage 2: nobody replies ---


def test_ai_off_is_recorded_as_no_reply(llm):
    workspace = workspace_with_llm(ai_enabled=False)
    fake = llm()
    send(VisitorFactory(workspace=workspace))
    turn = only_turn()
    assert turn.stage == Turn.Stage.NONE and turn.reply is None
    assert fake.requests == []


def test_a_conversation_a_person_took_over_is_left_alone(llm):
    workspace = workspace_with_llm()
    visitor = VisitorFactory(workspace=workspace)
    ConversationFactory(workspace=workspace, visitor=visitor, human_requested=True)
    fake = llm()
    send(visitor)
    assert only_turn().stage == Turn.Stage.NONE
    assert fake.requests == []


# --- Stage 3: limits ---


def test_past_the_ai_cap_a_person_is_asked_for(llm, settings):
    settings.RATE_LIMITS = {**settings.RATE_LIMITS, "ai_replies_per_visitor_per_day": 1}
    workspace = workspace_with_llm()
    visitor = VisitorFactory(workspace=workspace)
    fake = llm(final("Yes."))
    send(visitor, "one")
    send(visitor, "two")
    first, second = Turn.objects.order_by("id")
    assert first.stage == Turn.Stage.AI
    assert second.stage == Turn.Stage.GUARD and "teammate" in second.reply.body
    assert len(fake.requests) == 1
    assert Conversation.objects.get().human_requested


# --- Stage 4: the AI ---


def test_an_ai_turn_records_tokens_cost_and_time(llm):
    workspace = workspace_with_llm()
    usage = {"input_tokens": 900, "cached_tokens": 600, "output_tokens": 40, "cost": Decimal("0.0012")}
    llm(assistant(tool_call("search_knowledge_base", {"query": "canada"})), final("Yes, in 5 days."), usage=usage)

    send(VisitorFactory(workspace=workspace))

    turn = only_turn()
    assert turn.stage == Turn.Stage.AI
    assert turn.model == "test/model" and turn.llm_calls == 2
    assert (turn.input_tokens, turn.cached_tokens, turn.output_tokens) == (1800, 1200, 80)
    assert turn.cost == Decimal("0.0024")
    assert turn.reply.body == "Yes, in 5 days." and turn.reply.sender == Message.Sender.BOT
    assert turn.error == ""


def test_cost_stays_unknown_when_the_provider_does_not_report_it(llm):
    workspace = workspace_with_llm()
    llm(final("Hi"))
    send(VisitorFactory(workspace=workspace), "hello there")
    assert only_turn().cost is None


def test_tool_calls_are_recorded_as_steps(llm, monkeypatch):
    workspace = workspace_with_llm()
    ToolFactory(workspace=workspace, name="search_exams")
    monkeypatch.setattr(bot.http_tools, "run", lambda tool, inputs, visitor: ('[{"code":"AZ-104"}]', False))
    llm(assistant(tool_call("search_exams", {"q": "AZ-104"})), final("Yes."))

    send(VisitorFactory(workspace=workspace), "Do you have AZ-104?")

    [step] = [s for s in only_turn().steps if s["type"] == "tool"]
    assert step["name"] == "search_exams" and step["arguments"] == {"q": "AZ-104"}
    assert step["result"] == '[{"code":"AZ-104"}]' and step["is_error"] is False
    assert step["ms"] >= 0


def test_long_tool_results_are_shortened_in_the_record(llm, monkeypatch):
    workspace = workspace_with_llm()
    ToolFactory(workspace=workspace, name="dump")
    monkeypatch.setattr(bot.http_tools, "run", lambda tool, inputs, visitor: ("x" * 5000, False))
    llm(assistant(tool_call("dump", {})), final("Done."))
    send(VisitorFactory(workspace=workspace), "dump it")
    [step] = [s for s in only_turn().steps if s["type"] == "tool"]
    assert len(step["result"]) == 500


# --- Help center passages before the first model call ---


def test_matching_passages_are_in_the_first_prompt(llm):
    workspace = workspace_with_llm()
    article = ArticleFactory(
        workspace=workspace,
        title="Store policies",
        body="# Refunds\n\nRefunds within 30 days.\n\n# Shipping\n\nWe ship to Canada in 5 days.",
    )
    fake = llm(final("Yes, in 5 days.", article_ids=[article.id]))

    send(VisitorFactory(workspace=workspace), "Do you ship to Canada?")

    # One model call answered a help center question: no search round-trip.
    assert len(fake.requests) == 1
    prompt = fake.requests[0]["messages"][0]["content"]
    assert f"[article {article.id}] Store policies > Shipping" in prompt
    assert "We ship to Canada in 5 days." in prompt
    [retrieval] = [s for s in only_turn().steps if s["type"] == "retrieval"]
    assert retrieval["query"] == "Do you ship to Canada?"
    assert {"article_id": article.id, "label": "Store policies > Shipping"} in retrieval["passages"]


def test_no_match_adds_nothing_to_the_prompt(llm):
    workspace = workspace_with_llm()
    ArticleFactory(workspace=workspace, title="Refunds", body="30 days.")
    fake = llm(final("Hello!"))
    send(VisitorFactory(workspace=workspace), "hello")
    assert "From the help center" not in fake.requests[0]["messages"][0]["content"]
    [retrieval] = [s for s in only_turn().steps if s["type"] == "retrieval"]
    assert retrieval["passages"] == []


def test_passages_of_other_workspaces_and_drafts_never_reach_the_prompt(llm):
    workspace = workspace_with_llm()
    ArticleFactory(title="Shipping elsewhere", body="We ship to Canada by rocket.")
    ArticleFactory(workspace=workspace, title="Draft", body="We ship to Canada by drone.", published=False)
    fake = llm(final("Let me check."))
    send(VisitorFactory(workspace=workspace), "Do you ship to Canada?")
    prompt = fake.requests[0]["messages"][0]["content"]
    assert "rocket" not in prompt and "drone" not in prompt


def test_the_prompt_goes_from_stable_to_changing():
    """Providers cache a prompt by its beginning, so what changes per message must come last."""
    workspace = WorkspaceFactory(ai_instructions="Be kind.")
    article = ArticleFactory(workspace=workspace, title="Shipping", body="We ship to Canada.")
    found = bot.passages(workspace, "ship canada")
    assert found[0].article_id == article.id
    prompt = bot.system_prompt(workspace, (), "Offer a discount.", ["The visitor's name is Sofia."], found)
    order = [prompt.index(part) for part in ("Be kind.", "name is Sofia", "From the help center", "Offer a discount.")]
    assert order == sorted(order)


# --- Fallback ---


def test_a_failed_model_call_falls_back_and_says_why(llm):
    workspace = workspace_with_llm()
    ArticleFactory(workspace=workspace, title="Shipping", body="We ship to Canada.")
    llm(openrouter.OpenRouterError("OpenRouter credits or key limit ran out.", 402))
    send(VisitorFactory(workspace=workspace))
    turn = only_turn()
    assert turn.stage == Turn.Stage.FALLBACK
    assert "credits" in turn.error
    assert "help center" in turn.reply.body


def test_without_an_llm_every_answer_is_a_fallback(llm):
    workspace = WorkspaceFactory()
    fake = llm()
    send(VisitorFactory(workspace=workspace))
    turn = only_turn()
    assert turn.stage == Turn.Stage.FALLBACK and turn.error == "" and turn.llm_calls == 0
    assert fake.requests == []


def test_a_model_that_never_answers_is_a_fallback_with_a_reason(llm):
    workspace = workspace_with_llm()
    llm(*[assistant(tool_call("search_knowledge_base", {"query": "x"})) for _ in range(bot.MAX_STEPS)])
    send(VisitorFactory(workspace=workspace))
    turn = only_turn()
    assert turn.stage == Turn.Stage.FALLBACK and "no usable answer" in turn.error
    # The calls it did make are still counted.
    assert turn.llm_calls == bot.MAX_STEPS


# --- Several quick messages get one answer ---


def test_a_pass_whose_message_is_no_longer_the_newest_steps_aside(llm):
    workspace = workspace_with_llm()
    conversation = ConversationFactory(workspace=workspace)
    first = MessageFactory(conversation=conversation, body="hi, quick question")
    MessageFactory(conversation=conversation, body="do you ship to Canada?")
    fake = llm()

    assert bot.reply(conversation.id, trigger_id=first.id) is None

    turn = only_turn()
    assert turn.stage == Turn.Stage.SUPERSEDED and turn.trigger == first and turn.reply is None
    # It stepped aside before spending anything.
    assert fake.requests == [] and turn.llm_calls == 0


def test_the_newest_message_answers_with_everything_said(llm):
    workspace = workspace_with_llm()
    conversation = ConversationFactory(workspace=workspace)
    MessageFactory(conversation=conversation, body="hi, quick question")
    second = MessageFactory(conversation=conversation, body="do you ship to Canada?")
    fake = llm(final("Yes, we do."))

    message = bot.reply(conversation.id, trigger_id=second.id)

    assert message.body == "Yes, we do."
    assert fake.requests[0]["messages"][-1]["content"] == "hi, quick question\n\ndo you ship to Canada?"


def test_a_message_that_arrives_while_the_model_thinks_cancels_the_answer(llm, monkeypatch):
    workspace = workspace_with_llm()
    conversation = ConversationFactory(workspace=workspace)
    first = MessageFactory(conversation=conversation, body="do you ship")
    fake = llm(final("Ship where?"))
    complete = fake.complete

    def slow_model(*args):
        # The visitor finishes their sentence while the model is busy.
        MessageFactory(conversation=conversation, body="to Canada?")
        return complete(*args)

    monkeypatch.setattr(openrouter, "complete", slow_model)

    assert bot.reply(conversation.id, trigger_id=first.id) is None

    assert not conversation.messages.filter(sender=Message.Sender.BOT).exists()
    turn = only_turn()
    # Nothing was sent, but the call it made is on the record.
    assert turn.stage == Turn.Stage.SUPERSEDED and turn.llm_calls == 1 and turn.input_tokens == 100


def test_a_reply_that_runs_out_of_time_falls_back(llm, settings, monkeypatch):
    settings.REPLY_DEADLINE_SECONDS = 30
    workspace = workspace_with_llm()
    ToolFactory(workspace=workspace, name="slow_lookup")
    clock = iter([0, 0, 10, 10, 45, 45, 45, 45, 45, 45])
    monkeypatch.setattr(bot.time, "monotonic", lambda: next(clock, 45))
    monkeypatch.setattr(bot.http_tools, "run", lambda tool, inputs, visitor: ("[]", False))
    fake = llm(assistant(tool_call("slow_lookup", {})), final("Too late."))

    send(VisitorFactory(workspace=workspace), "look it up")

    turn = only_turn()
    # One model call, then the deadline passed while the tool ran: no second call.
    assert len(fake.requests) == 1 and turn.stage == Turn.Stage.FALLBACK
    assert "no usable answer" in turn.error


# --- Forms continue a turn without a second look from rules ---


def test_a_submitted_form_skips_rules_and_records_its_own_turn(llm):
    workspace = workspace_with_llm()
    RuleFactory(workspace=workspace, keywords=["email"], reply="Rule reply.")
    visitor = VisitorFactory(workspace=workspace)
    form = {"fields": [{"name": "email", "label": "Email", "type": "email", "required": True}]}
    ask_for_email = assistant(
        tool_call(
            "reply_to_visitor",
            {"reply": "Where can we reach you?", "article_ids": [], "offer_human": False, "form": form},
        )
    )
    llm(ask_for_email, final("Thanks, we'll write to you."))
    send(visitor, "notify me please")
    surface_id = Message.objects.filter(sender=Message.Sender.BOT).last().form["surface_id"]

    Api(visitor_token=visitor.token).post(
        f"/widget/{workspace.public_key}/actions",
        {"name": "submit_form", "surfaceId": surface_id, "context": {"fields": {"email": "s@example.com"}}},
    )

    turns = list(Turn.objects.order_by("id"))
    assert [turn.stage for turn in turns] == [Turn.Stage.AI, Turn.Stage.AI]
    assert turns[1].trigger.body == "Email: s@example.com"
    assert turns[1].reply.body == "Thanks, we'll write to you."


# --- The recorder ---


def test_recorder_writes_nothing_until_finished():
    conversation = ConversationFactory()
    recorder = Recorder(conversation, MessageFactory(conversation=conversation))
    recorder.step("retrieval", query="x", passages=[])
    assert Turn.objects.count() == 0
    turn = recorder.finish(Turn.Stage.NONE)
    assert turn.workspace_id == conversation.workspace_id and turn.steps == [
        {"type": "retrieval", "query": "x", "passages": []}
    ]


def test_handle_runs_inline_in_tests(llm):
    """Without a broker, Celery runs the AI stage inside the call, so tests need no waiting."""
    workspace = workspace_with_llm()
    conversation = ConversationFactory(workspace=workspace)
    message = MessageFactory(conversation=conversation, body="hello there")
    llm(final("Hi!"))
    pipeline.handle(conversation, message)
    assert only_turn().reply.body == "Hi!"


# --- Dashboard ---


def test_turns_of_a_conversation(api, workspace, llm):
    workspace.organization.openrouter_api_key = "sk-or-test-key-1234"
    workspace.organization.llm_model = "test/model"
    workspace.organization.save()
    rule = RuleFactory(workspace=workspace, keywords=["hours"], reply="9 to 5.")
    visitor = VisitorFactory(workspace=workspace)
    llm(final("Yes."))
    send(visitor, "opening hours?")
    send(visitor, "Do you ship to Canada?")
    conversation = Conversation.objects.get()

    rows = api.get(f"/workspaces/{workspace.id}/conversations/{conversation.id}/turns").json()

    assert [row["stage"] for row in rows] == ["rule", "ai"]
    assert rows[0]["rule_id"] == rule.id and rows[0]["rule_name"] == rule.name
    assert rows[1]["model"] == "test/model" and rows[1]["input_tokens"] == 100
    assert rows[1]["reply_message_id"] and rows[1]["trigger_message_id"]


def test_turns_of_another_workspace_are_hidden(api):
    conversation = ConversationFactory()
    path = f"/workspaces/{conversation.workspace_id}/conversations/{conversation.id}/turns"
    assert api.get(path).status_code == 404


def test_summary_counts_stages_and_cost(api, workspace):
    conversation = ConversationFactory(workspace=workspace)

    def turn(stage, **fields):
        Turn.objects.create(workspace=workspace, conversation=conversation, stage=stage, **fields)

    turn("rule")
    turn("rule")
    turn("guard")
    turn("none")
    turn("ai", llm_calls=2, input_tokens=1000, cached_tokens=400, output_tokens=50, cost=Decimal("0.002"))
    turn("ai", llm_calls=1, input_tokens=500, output_tokens=20, cost=Decimal("0.001"))
    turn("fallback")
    Turn.objects.create(workspace=WorkspaceFactory(), conversation=ConversationFactory(), stage="ai", llm_calls=9)

    summary = api.get(f"/workspaces/{workspace.id}/turns/summary").json()

    assert summary["turns"] == 7
    assert summary["by_stage"] == {"rule": 2, "guard": 1, "ai": 2, "fallback": 1, "superseded": 0, "none": 1}
    assert summary["replied"] == 6 and summary["replied_without_model"] == 4
    assert (summary["llm_calls"], summary["input_tokens"], summary["cached_tokens"]) == (3, 1500, 400)
    assert Decimal(summary["cost"]) == Decimal("0.003")


def test_summary_of_a_quiet_workspace_is_all_zeros(api, workspace):
    summary = api.get(f"/workspaces/{workspace.id}/turns/summary", days=7).json()
    assert summary["days"] == 7 and summary["turns"] == 0 and summary["llm_calls"] == 0
    assert Decimal(summary["cost"]) == 0


def test_summary_only_looks_back_the_days_asked_for(api, workspace):
    conversation = ConversationFactory(workspace=workspace)
    old = Turn.objects.create(workspace=workspace, conversation=conversation, stage="ai")
    Turn.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=10))
    Turn.objects.create(workspace=workspace, conversation=conversation, stage="rule")
    assert api.get(f"/workspaces/{workspace.id}/turns/summary", days=7).json()["turns"] == 1
    assert api.get(f"/workspaces/{workspace.id}/turns/summary", days=30).json()["turns"] == 2
