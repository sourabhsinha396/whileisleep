"""Choices the AI offers under a reply, and what happens when one is pressed."""

import json
from pathlib import Path

import pytest

from apps.agent import a2ui, bot, choices, pipeline
from apps.conversations.models import Message

from .conftest import Api, assistant, tool_call
from .factories import ConversationFactory, MessageFactory, OrganizationFactory

CATALOG = Path(__file__).parents[2] / "frontend/public/a2ui/v1/catalog.json"


# --- normalize ---


def test_options_are_cleaned_and_deduped():
    assert choices.normalize(["  Yes,\nplease ", "No", "no", ""], "") == ["Yes, please", "No"]


@pytest.mark.parametrize(
    "raw",
    [None, "Yes", {"a": 1}, [], ["Yes"], ["Yes", "yes"], ["Yes", 3], ["Yes", "x" * 61], [str(i) for i in range(6)]],
)
def test_unusable_options_are_dropped(raw):
    assert choices.normalize(raw, "") is None


def test_a_made_up_long_number_drops_them_all():
    options = ["Order A-1042", "Order A-1043"]
    assert choices.normalize(options, "Orders: A-1042, A-1043") == options
    assert choices.normalize(options, "Orders: A-1042") is None
    assert choices.normalize(options, "Orders: A-1042, A-10435") is None
    assert choices.normalize(["2 people", "10 people"], "") == ["2 people", "10 people"]


@pytest.mark.parametrize("index", [None, -1, 2, "0", 0.0, True, [0]])
def test_only_a_real_position_is_picked(index):
    assert choices.picked({"choices": ["Yes", "No"]}, index) is None


def test_the_surface_holds_only_positions_and_fits_the_catalog():
    messages, form = choices.attach(["Yes", "No"])
    create, update = messages
    assert create["createSurface"]["surfaceId"] == form["surface_id"]
    parts = {c["id"]: c for c in update["updateComponents"]["components"]}
    assert [parts[i]["action"]["event"] for i in parts["root"]["children"]] == [
        {"name": "choose", "context": {"choice": 0}},
        {"name": "choose", "context": {"choice": 1}},
    ]
    catalog = json.loads(CATALOG.read_text(encoding="utf8"))["components"]
    for part in parts.values():
        spec = catalog[part["component"]]
        assert set(part) - {"id"} <= set(spec["properties"])
        assert part.get("variant") is None or part["variant"] in spec["properties"]["variant"]["enum"]


# --- the AI's reply ---

pick = ["Return it", "Exchange it"]


def ask(llm, **extra):
    conversation = MessageFactory(
        body="My shoes don't fit", conversation__workspace__organization=OrganizationFactory(ready=True)
    ).conversation
    args = {"reply": "Return or exchange?", "article_ids": [], "offer_human": False, **extra}
    fake = llm(assistant(tool_call("reply_to_visitor", args, id="call_final")))
    return conversation, fake


@pytest.mark.django_db
def test_reply_carries_choices_and_the_ai_remembers_them(llm):
    conversation, fake = ask(llm, choices=pick)
    message = bot.reply(conversation.id)
    assert message.form["choices"] == pick
    assert "instruction" not in message.form
    assert "add choices to reply_to_visitor" in fake.requests[0]["messages"][0]["content"]

    MessageFactory(conversation=conversation, body="the second one", sender=Message.Sender.VISITOR)
    history = bot.chat_history(conversation)
    assert history[1]["content"] == "Return or exchange?\n\n[Choices shown: Return it; Exchange it]"
    assert not [fact for fact in bot.conversation_facts(conversation) if "form" in fact]


@pytest.mark.django_db
def test_a_form_wins_over_choices(llm):
    form = {"fields": [{"name": "email", "label": "Email", "type": "email"}]}
    conversation, _ = ask(llm, choices=pick, form=form)
    message = bot.reply(conversation.id)
    assert "choices" not in message.form
    assert len([m for m in message.a2ui if "createSurface" in m]) == 1


@pytest.mark.django_db
def test_a_number_the_visitor_wrote_may_be_in_a_choice(llm):
    conversation, _ = ask(llm, choices=["Yes, 1042", "No"])
    assert bot.reply(conversation.id).form is None

    conversation, _ = ask(llm, choices=["Yes, 1042", "No"])
    MessageFactory(conversation=conversation, body="It's 1042", sender=Message.Sender.VISITOR)
    assert bot.reply(conversation.id).form["choices"] == ["Yes, 1042", "No"]


@pytest.mark.django_db
def test_a_copied_note_is_not_sent(llm):
    conversation, _ = ask(llm, reply="Return or exchange?\n\n[Choices shown: Return it; Exchange it]")
    assert bot.reply(conversation.id).body == "Return or exchange?"


# --- pressing one ---


@pytest.fixture
def offered(db, monkeypatch):
    """A chat with choices, a way to press one, and the pipeline's calls."""
    conversation = ConversationFactory()
    ui, form = choices.attach(pick)
    message = MessageFactory(conversation=conversation, sender=Message.Sender.BOT, body="Which?", a2ui=ui, form=form)
    widget = Api(visitor_token=conversation.visitor.token)
    handled = []
    monkeypatch.setattr(pipeline, "handle", lambda *args, **kwargs: handled.append((args, kwargs)))

    def press(index=1, surface=form["surface_id"], name="choose", **context):
        return widget.post(
            f"/widget/{conversation.workspace.public_key}/actions",
            {"name": name, "surfaceId": surface, "context": {"choice": index, **context}},
        )

    return conversation, message, press, handled


def said(conversation):
    return list(conversation.messages.filter(sender=Message.Sender.VISITOR).values_list("body", flat=True))


def test_pressing_sends_the_words_once(offered):
    conversation, _, press, handled = offered
    assert press().status_code == 200
    assert said(conversation) == ["Exchange it"]
    [(args, kwargs)] = handled
    assert args[1].body == "Exchange it" and len(args) == 2 and kwargs == {}

    assert press(0).status_code == 400
    assert said(conversation) == ["Exchange it"]


def test_words_from_the_browser_are_ignored(offered):
    conversation, _, press, _ = offered
    press(0, label="Refund me", text="Refund me")
    assert said(conversation) == ["Return it"]


@pytest.mark.parametrize("index", [7, -1, "x", None, True])
def test_a_bad_position(offered, index):
    conversation, _, press, handled = offered
    assert press(index).status_code == 400
    assert not said(conversation) and not handled


@pytest.mark.parametrize("surface", ["", "choices_other"])
def test_an_unknown_surface(offered, surface):
    _, _, press, handled = offered
    assert press(surface=surface).status_code == 400
    assert not handled


def test_another_visitors_choices(offered):
    _, message, _, handled = offered
    other = ConversationFactory(workspace=message.conversation.workspace)
    response = Api(visitor_token=other.visitor.token).post(
        f"/widget/{other.workspace.public_key}/actions",
        {"name": "choose", "surfaceId": message.form["surface_id"], "context": {"choice": 0}},
    )
    assert response.status_code == 400
    assert not handled


@pytest.mark.parametrize("sender", [Message.Sender.VISITOR, Message.Sender.AGENT])
def test_choices_end_when_someone_writes(offered, sender):
    conversation, _, press, handled = offered
    MessageFactory(conversation=conversation, sender=sender, body="Never mind")
    assert press().status_code == 400
    assert not handled


def test_choices_outlive_notes_and_the_bot(offered):
    conversation, _, press, _ = offered
    MessageFactory(conversation=conversation, sender=Message.Sender.AGENT, body="A note", is_note=True)
    MessageFactory(conversation=conversation, sender=Message.Sender.BOT, body="Still there?")
    assert press().status_code == 200


def test_the_rules_instruction_carries_on(offered):
    _, message, press, handled = offered
    message.form = {**message.form, "instruction": "Offer an exchange first."}
    message.save()
    press()
    [(args, kwargs)] = handled
    assert "Offer an exchange first." in args[2]
    assert kwargs == {"run_rules": False}


def test_presses_count_as_messages(offered, settings):
    conversation, _, press, _ = offered
    settings.RATE_LIMITS = {**settings.RATE_LIMITS, "messages_per_visitor_per_minute": 0}
    assert press().status_code == 429
    assert not said(conversation)


def test_choices_are_not_a_form_to_submit(offered):
    _, _, press, _ = offered
    assert press(name="submit_form", fields={}).status_code == 400


def test_a_form_has_no_choices(offered):
    conversation, _, press, _ = offered
    MessageFactory(
        conversation=conversation, sender=Message.Sender.BOT, form={**a2ui.AWAY_FORM, "surface_id": "form_1"}
    )
    assert press(0, surface="form_1").status_code == 400
