"""Model → response dicts shared by the dashboard and widget APIs."""

from apps.accounts.models import photo_url

from . import attributes
from .models import Conversation, Message, Visitor


def visitor_out(visitor: Visitor, conversation_id: int | None = None, online: bool | None = None) -> dict:
    """`online` when the caller already knows (lists ask Redis once for every row)."""
    return {
        "id": visitor.id,
        "name": visitor.display_name,
        "email": visitor.email,
        "verified": visitor.is_verified,
        "attributes": attributes.listing(visitor),
        "online": visitor.is_online if online is None else online,
        "current_url": visitor.current_url,
        "page_title": visitor.page_title,
        "referrer": visitor.referrer,
        "user_agent": visitor.user_agent,
        "first_seen": visitor.first_seen,
        "last_seen": visitor.last_seen,
        "conversation_id": conversation_id,
    }


def message_out(message: Message) -> dict:
    author = message.author
    return {
        "id": message.id,
        "sender": message.sender,
        "author_name": (author.first_name or author.email) if author else "",
        "author_photo": photo_url(author) if author else "",
        "body": message.body,
        "a2ui": message.a2ui,
        "is_note": message.is_note,
        "intent": message.intent,
        # The widget shows a sent form disabled.
        "form_submitted": bool(message.form and message.form.get("submitted")),
        "created_at": message.created_at,
    }


def conversation_row(conversation: Conversation, last: Message | None = None, online: bool | None = None) -> dict:
    return {
        "id": conversation.id,
        "status": conversation.status,
        "unread": conversation.unread,
        "human_requested": conversation.human_requested,
        "tags": conversation.tags or [],
        "attributes": attributes.listing(conversation),
        "assignee_id": conversation.assignee_id,
        "last_message_at": conversation.last_message_at,
        "preview": (last.body[:140] if last else ""),
        "visitor": visitor_out(conversation.visitor, conversation.id, online),
    }
