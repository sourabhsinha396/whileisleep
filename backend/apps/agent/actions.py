"""Handles A2UI action events the widget sends back when a visitor presses a button."""

from django.db import transaction

from apps.conversations import signals
from apps.conversations.models import Conversation, Message
from apps.conversations.services import add_message, request_human
from apps.knowledge.models import Article

from . import a2ui, choices, forms, pipeline
from .bot import will_reply


class ActionError(Exception):
    pass


def handle(conversation: Conversation, name: str, context: dict, surface_id: str = "") -> dict:
    visitor = conversation.visitor
    if name == "open_article":
        article = Article.objects.filter(
            workspace=conversation.workspace, published=True, pk=context.get("articleId")
        ).first()
        if article is None:
            raise ActionError("Article not found.")
        return {"article": {"id": article.id, "title": article.title, "body": article.body}}

    if name == "talk_to_human":
        if conversation.human_requested:
            return {}
        request_human(conversation)
        form_ui, form_meta = (None, None) if visitor.email else forms.attach(a2ui.AWAY_FORM)
        add_message(
            conversation, Message.Sender.BOT, "Sure, a teammate will reply here soon.", a2ui=form_ui, form=form_meta
        )
        return {}

    if name == "submit_form":
        submit_form(conversation, surface_id, context.get("fields"))
        return {}

    if name == "choose":
        choose(conversation, surface_id, context.get("choice"))
        return {}

    raise ActionError(f"Unknown action {name}.")


def choose(conversation: Conversation, surface_id: str, index) -> None:
    """The visitor pressed one of the bot's choices: its words become their next message."""
    with transaction.atomic():
        # One press at a time, so that two quick ones can't both answer the question.
        locked = Conversation.objects.select_for_update().get(pk=conversation.pk)
        messages = locked.messages.filter(is_note=False)
        message = messages.filter(form__surface_id=surface_id).first() if surface_id else None
        label = choices.picked(message.form, index) if message else None
        if label is None:
            raise ActionError("This choice isn't here anymore.")
        people = (Message.Sender.VISITOR, Message.Sender.AGENT)
        if messages.filter(sender__in=people, pk__gt=message.pk).exists():
            raise ActionError("The chat has moved on. Please write your answer instead.")
        answer = add_message(conversation, Message.Sender.VISITOR, label)
    if instruction := message.form.get("instruction"):
        # The question was part of following this, so rules don't get a second look.
        pipeline.handle(conversation, answer, choice_instruction(instruction), run_rules=False)
    else:
        pipeline.handle(conversation, answer)


def choice_instruction(instruction: str) -> str:
    return (
        "The visitor just picked one of the choices from your previous message. You showed them while "
        f"following this instruction from the business, which still applies:\n{instruction}"
    )


def submit_form(conversation: Conversation, surface_id: str, values) -> None:
    """The visitor's answers to a form one of the bot's messages carried.

    They become the visitor's next message (so the team and the AI see them), and an email
    or name also lands on the visitor. The AI then replies, or, when it won't (off, or a
    person took over), a short thank-you does.
    """
    message = (
        conversation.messages.filter(sender=Message.Sender.BOT, form__surface_id=surface_id).first()
        if surface_id
        else None
    )
    if message is None or "fields" not in message.form:
        raise ActionError("This form isn't here anymore.")
    form = message.form
    if form.get("submitted"):
        raise ActionError("You already sent this form.")
    try:
        answers = forms.check(form, values)
    except forms.FormError as error:
        raise ActionError(str(error)) from error

    message.form = {**form, "submitted": True}
    message.save(update_fields=["form"])
    visitor = conversation.visitor
    changed = forms.remember(conversation, form, answers)
    answer = add_message(conversation, Message.Sender.VISITOR, forms.as_text(form, answers))
    if changed:
        signals.announce(signals.CONTACT_UPDATED, conversation, data={"changed": list(changed)})
        add_message(
            conversation,
            Message.Sender.SYSTEM,
            f"Saved the visitor's {' and '.join(changed)} from a form.",
            is_note=True,
        )

    if will_reply(conversation):
        # The answers continue what the form was for, so rules don't get a second look.
        pipeline.handle(conversation, answer, followup_instruction(form), run_rules=False)
    else:
        visitor.refresh_from_db(fields=["email"])
        thanks = f"Thanks! We'll also reply to {visitor.email}." if "email" in changed else "Thanks, we got it."
        add_message(conversation, Message.Sender.BOT, thanks)


def followup_instruction(form: dict) -> str:
    """What the AI is told when a form it showed comes back, so it finishes the job instead of
    treating the answers as a new, context-free message."""
    title = f' ("{form["title"]}")' if form.get("title") else ""
    parts = [
        f"The visitor just filled in the form from your previous message{title}; their answers are "
        "their last message. Thank them, confirm what happens next, and don't ask for those details again."
    ]
    if form.get("instruction"):
        parts.append(
            "You showed that form while following this instruction from the business, which still "
            f"applies:\n{form['instruction']}"
        )
    return "\n\n".join(parts)
