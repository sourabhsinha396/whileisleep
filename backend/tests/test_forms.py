"""Forms the AI adds to its replies, compiled to A2UI, and what visitors send back."""

import pytest

from apps.agent import a2ui, bot, forms
from apps.conversations.models import Message

from .conftest import Api, assistant, final, tool_call
from .factories import ConversationFactory, MessageFactory, OrganizationFactory

pytestmark = pytest.mark.django_db

EMAIL_FORM = {
    "title": "So we can tell you when it's live:",
    "fields": [{"name": "email", "label": "Email", "type": "email", "required": True}],
    "submit_label": "Notify me",
}


# --- normalize ---


def test_normalize_keeps_a_good_spec():
    spec = {
        "title": "  Details  ",
        "fields": [
            {"name": "email", "label": "Email", "type": "email", "required": True},
            {"name": "level", "label": "Level", "type": "choice", "options": ["Beginner", "Pro", "Pro"]},
        ],
    }
    assert forms.normalize(spec) == {
        "title": "Details",
        "fields": [
            {"name": "email", "label": "Email", "type": "email", "required": True},
            {"name": "level", "label": "Level", "type": "choice", "required": False, "options": ["Beginner", "Pro"]},
        ],
        "submit_label": "Send",
    }


@pytest.mark.parametrize(
    "spec",
    [
        None,
        "a form",
        {"fields": []},
        {"fields": [{"name": "Bad Name!", "label": "x", "type": "text"}]},
        {"fields": [{"name": "x", "label": "x", "type": "file"}]},
        {"fields": [{"name": "x", "label": "x", "type": "choice", "options": ["only one"]}]},
    ],
)
def test_normalize_drops_unusable_specs(spec):
    assert forms.normalize(spec) is None


def test_normalize_limits_fields_and_dedupes_names():
    spec = {"fields": [{"name": f"f{i % 7}", "label": "x", "type": "text"} for i in range(20)]}
    names = [f["name"] for f in forms.normalize(spec)["fields"]]
    assert names == ["f0", "f1", "f2", "f3", "f4", "f5"]


# --- compile to A2UI ---


def test_form_compiles_to_a_valid_a2ui_surface():
    spec = forms.normalize(
        {
            "title": "Details",
            "fields": [
                {"name": "email", "label": "Email", "type": "email", "required": True},
                {"name": "notes", "label": "Notes", "type": "long_text"},
                {"name": "level", "label": "Level", "type": "choice", "options": ["A", "B"]},
            ],
            "submit_label": "Send it",
        }
    )
    create, update = a2ui.form("form_1", spec)
    assert create == {
        "version": "1.0",
        "createSurface": {
            "surfaceId": "form_1",
            "catalogId": a2ui.CATALOG_ID,
            "dataModel": {"fields": {"email": "", "notes": "", "level": ""}},
        },
    }
    components = {c["id"]: c for c in update["updateComponents"]["components"]}
    assert components["root"]["children"] == ["title", "f_email", "f_notes", "f_level", "submit"]
    assert components["f_email"] == {
        "id": "f_email",
        "component": "TextField",
        "label": "Email *",
        "variant": "shortText",
        "value": {"@path": "/fields/email"},
    }
    assert components["f_notes"]["variant"] == "longText"
    assert components["f_level"]["component"] == "ChoicePicker"
    assert components["f_level"]["options"] == [{"label": "A", "value": "A"}, {"label": "B", "value": "B"}]
    assert components["submit"]["action"] == {
        "event": {"name": "submit_form", "context": {"fields": {"@path": "/fields"}}}
    }
    # Every child reference points at a component in the surface.
    for component in components.values():
        for child in component.get("children", []) + ([component["child"]] if "child" in component else []):
            assert child in components


# --- the AI adds a form ---


def ask(body="Please add CompTIA Cloud+"):
    return MessageFactory(body=body, conversation__workspace__organization=OrganizationFactory(ready=True)).conversation


def test_ai_reply_can_carry_a_form(llm):
    conversation = ask()
    answer = {
        "reply": "We'll add it within 12 hours.",
        "article_ids": [],
        "offer_human": False,
        "form": {
            "title": "Where should we tell you?",
            "fields": [{"name": "email", "label": "Email", "type": "email", "required": True}],
        },
    }
    fake = llm(assistant(tool_call("reply_to_visitor", answer, id="call_final")))

    message = bot.reply(conversation.id)

    assert message.body == "We'll add it within 12 hours."
    assert message.form["fields"][0]["name"] == "email"
    assert message.form["submitted"] is False
    surface_ids = [m["createSurface"]["surfaceId"] for m in message.a2ui if "createSurface" in m]
    assert surface_ids == [message.form["surface_id"]]
    # The model is told about forms and offered the schema.
    reply_tool = next(t for t in fake.requests[0]["tools"] if t["function"]["name"] == "reply_to_visitor")
    assert "form" in reply_tool["function"]["parameters"]["properties"]
    assert "add a form to reply_to_visitor" in fake.requests[0]["messages"][0]["content"]


def test_unusable_form_is_dropped_not_shown(llm):
    conversation = ask()
    bad = final("Sure.")
    bad["tool_calls"][0]["function"]["arguments"] = (
        '{"reply": "Sure.", "article_ids": [], "offer_human": false, "form": {"fields": "email please"}}'
    )
    llm(bad)
    message = bot.reply(conversation.id)
    assert message.body == "Sure." and message.form is None and message.a2ui is None


# --- submitting ---


@pytest.fixture
def form_chat():
    """A conversation whose last bot message carries EMAIL_FORM, and a way to submit it."""
    conversation = ConversationFactory(workspace__ai_enabled=False)
    ui, meta = forms.attach(forms.normalize(EMAIL_FORM))
    message = MessageFactory(conversation=conversation, sender=Message.Sender.BOT, body="Sure!", a2ui=ui, form=meta)
    widget = Api(visitor_token=conversation.visitor.token)

    def submit(fields, surface=meta["surface_id"]):
        return widget.post(
            f"/widget/{conversation.workspace.public_key}/actions",
            {"name": "submit_form", "surfaceId": surface, "context": {"fields": fields}},
        )

    return conversation, message, submit


def test_submit_saves_answers_as_the_visitors_message(form_chat):
    conversation, message, submit = form_chat
    assert submit({"email": "sofia@example.com", "sneaky": "extra"}).status_code == 200
    conversation.visitor.refresh_from_db()
    assert conversation.visitor.email == "sofia@example.com"
    visitor_messages = conversation.messages.filter(sender=Message.Sender.VISITOR)
    assert visitor_messages.last().body == "Email: sofia@example.com"
    assert conversation.messages.filter(is_note=True, body__contains="Saved the visitor's email").exists()
    message.refresh_from_db()
    assert message.form["submitted"] is True


def test_submitted_form_shows_as_sent(form_chat):
    conversation, message, submit = form_chat
    submit({"email": "sofia@example.com"})
    rows = Api(visitor_token=conversation.visitor.token).get(f"/widget/{conversation.workspace.public_key}/messages")
    sent = next(m for m in rows.json()["messages"] if m["id"] == message.id)
    assert sent["form_submitted"] is True


@pytest.mark.parametrize(
    ("fields", "error"),
    [
        ({}, "Please fill in Email."),
        ({"email": "not-an-email"}, "doesn't look like an email"),
        ("email", "came back empty"),
        ({"email": "a" * 490 + "@example.com"}, "too long (at most 500 characters)"),
    ],
)
def test_bad_answers_are_refused_with_a_reason(form_chat, fields, error):
    _, _, submit = form_chat
    response = submit(fields)
    assert response.status_code == 400 and error in response.json()["detail"]


def test_form_can_be_sent_once(form_chat):
    _, _, submit = form_chat
    submit({"email": "sofia@example.com"})
    assert "already sent" in submit({"email": "other@example.com"}).json()["detail"]


def test_unknown_or_foreign_form_is_refused(form_chat):
    conversation, _, submit = form_chat
    assert submit({"email": "a@example.com"}, surface="form_nope").status_code == 400
    # A form from another visitor's conversation can't be submitted here.
    other = ConversationFactory(workspace=conversation.workspace)
    _, meta = forms.attach(forms.normalize(EMAIL_FORM))
    MessageFactory(conversation=other, sender=Message.Sender.BOT, form=meta)
    assert submit({"email": "a@example.com"}, surface=meta["surface_id"]).status_code == 400


def test_submit_wakes_the_ai_with_the_answers(llm):
    conversation = ConversationFactory(workspace__organization=OrganizationFactory(ready=True))
    MessageFactory(conversation=conversation, body="Add Cloud+ please")
    ui, meta = forms.attach(forms.normalize(EMAIL_FORM))
    MessageFactory(conversation=conversation, sender=Message.Sender.BOT, body="Sure! Your email?", a2ui=ui, form=meta)
    fake = llm(final("Thanks, we'll email you."))

    Api(visitor_token=conversation.visitor.token).post(
        f"/widget/{conversation.workspace.public_key}/actions",
        {"name": "submit_form", "surfaceId": meta["surface_id"], "context": {"fields": {"email": "s@example.com"}}},
    )

    assert fake.requests[0]["messages"][-1] == {"role": "user", "content": "Email: s@example.com"}
    assert conversation.messages.filter(sender=Message.Sender.BOT).last().body == "Thanks, we'll email you."


def test_form_answers_continue_the_rule_that_asked_for_them(llm):
    """The rule's instruction rides on the form, so the AI's follow-up still follows it."""
    workspace_org = OrganizationFactory(ready=True)
    conversation = ConversationFactory(workspace__organization=workspace_org)
    MessageFactory(conversation=conversation, body="Please prioritize Cloud+", intent="exam_request")
    answer = {
        "reply": "We'll add it in 12 hours. Your email?",
        "article_ids": [],
        "offer_human": False,
        "form": EMAIL_FORM,
    }
    fake = llm(assistant(tool_call("reply_to_visitor", answer, id="call_final")), final("Thanks, we'll email you."))
    bot.reply(conversation.id, instruction="Promise 12 hours and get their email.")
    form = conversation.messages.filter(sender=Message.Sender.BOT).last().form
    assert form["instruction"] == "Promise 12 hours and get their email."

    Api(visitor_token=conversation.visitor.token).post(
        f"/widget/{conversation.workspace.public_key}/actions",
        {"name": "submit_form", "surfaceId": form["surface_id"], "context": {"fields": {"email": "s@example.com"}}},
    )

    followup = fake.requests[1]["messages"][0]["content"]
    assert "just filled in the form from your previous message" in followup
    assert "don't ask for those details again" in followup
    assert "Promise 12 hours and get their email." in followup


def test_name_and_choice_answers():
    conversation = ConversationFactory()
    spec = forms.normalize(
        {
            "fields": [
                {"name": "name", "label": "Name", "type": "text"},
                {"name": "level", "label": "Level", "type": "choice", "options": ["A", "B"]},
                {"name": "phone", "label": "Phone", "type": "phone"},
            ]
        }
    )
    with pytest.raises(forms.FormError, match="Pick one of the options"):
        forms.check(spec, {"level": "C"})
    with pytest.raises(forms.FormError, match="phone number"):
        forms.check(spec, {"phone": "call me"})
    answers = forms.check(spec, {"name": "Sofia", "level": "B", "phone": "+44 20 7946 0000"})
    assert forms.update_visitor(conversation.visitor, spec, answers) == ["name"]
    assert forms.as_text(spec, answers) == "Name: Sofia\nLevel: B\nPhone: +44 20 7946 0000"
