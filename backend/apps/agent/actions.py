"""Handles A2UI action events the widget sends back when a visitor presses a button."""

import uuid

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from apps.conversations.models import Conversation, Message
from apps.conversations.services import add_message
from apps.knowledge.models import Article

from . import a2ui
from .bot import request_human


class ActionError(Exception):
    pass


def handle(conversation: Conversation, name: str, context: dict) -> dict:
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
        form = None if visitor.email else a2ui.email_form(f"email_{uuid.uuid4().hex[:12]}")
        add_message(conversation, Message.Sender.BOT, "Sure, a teammate will reply here soon.", a2ui=form)
        return {}

    if name == "save_email":
        email = str(context.get("email", "")).strip()
        try:
            validate_email(email)
        except ValidationError as error:
            raise ActionError("That doesn't look like an email address.") from error
        visitor.email = email
        visitor.save(update_fields=["email"])
        add_message(conversation, Message.Sender.BOT, f"Thanks! We'll also reply to {email}.")
        return {}

    raise ActionError(f"Unknown action {name}.")
