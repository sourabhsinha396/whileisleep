"""What an endpoint is sent. People build on this (docs/webhooks.md): add to it, never change or
remove what is there."""

from apps.integrations.sdk import (
    AI_RESUMED,
    CONTACT_UPDATED,
    MESSAGE,
    PERSON_REQUESTED,
    REOPENED,
    RESOLVED,
    STARTED,
    Event,
    Message,
    Option,
    attributes_of,
    email_is_verified,
    inbox_url,
    needs_person,
)

TYPES = {
    STARTED: "conversation.started",
    PERSON_REQUESTED: "conversation.needs_person",
    RESOLVED: "conversation.resolved",
    REOPENED: "conversation.reopened",
    AI_RESUMED: "conversation.returned_to_ai",
    CONTACT_UPDATED: "contact.updated",
}
MESSAGE_CREATED, NOTE_CREATED = "message.created", "note.created"

CHOICES = (
    Option("conversation.started", "A chat starts"),
    Option("conversation.needs_person", "A chat needs a person"),
    Option("contact.updated", "A visitor leaves their name, email or phone"),
    Option("conversation.resolved", "A chat is resolved"),
    Option("conversation.reopened", "A chat is reopened"),
    Option("conversation.returned_to_ai", "A chat is given back to the AI"),
    Option(MESSAGE_CREATED, "Every message"),
    Option(NOTE_CREATED, "Every internal note"),
)
DEFAULT = "conversation.started,conversation.needs_person,contact.updated,conversation.resolved"

FROM = {Message.Sender.VISITOR: "visitor", Message.Sender.BOT: "ai", Message.Sender.AGENT: "teammate"}


def type_of(event: Event) -> str:
    """Empty: nothing anyone is told about."""
    if event.name != MESSAGE:
        return TYPES.get(event.name, "")
    if event.message.sender not in FROM:
        return ""
    return NOTE_CREATED if event.message.is_note else MESSAGE_CREATED


def build(event: Event) -> dict:
    conversation = event.conversation
    data = {"conversation": conversation_out(conversation), "contact": contact_out(conversation.visitor)}
    if event.message:
        data["message"] = message_out(event.message)
    if event.by:
        data["by"] = person_out(event.by)
    # "reason" a person is needed, which details "changed".
    data |= event.data
    return {
        "id": f"msg_{event.id}",
        "type": type_of(event),
        "created_at": event.at.isoformat(),
        "workspace": workspace_out(conversation.workspace),
        "data": data,
    }


def workspace_out(workspace) -> dict:
    return {"id": workspace.pk, "name": workspace.name, "slug": workspace.slug}


def person_out(user) -> dict:
    return {"name": user.first_name, "email": user.email}


def conversation_out(conversation) -> dict:
    return {
        "id": conversation.pk,
        "url": inbox_url(conversation),
        "status": conversation.status,
        "needs_person": needs_person(conversation),
        "assignee": person_out(conversation.assignee) if conversation.assignee else None,
        "tags": conversation.tags or [],
        "attributes": attributes_of(conversation),
        "created_at": conversation.created_at.isoformat(),
    }


def contact_out(visitor) -> dict:
    return {
        "id": visitor.pk,
        # Your own id for them, from a signed identity token.
        "external_id": visitor.external_id,
        "name": visitor.name,
        "email": visitor.email,
        "email_verified": email_is_verified(visitor),
        "attributes": attributes_of(visitor),
        "page": {"url": visitor.current_url, "title": visitor.page_title},
    }


def message_out(message: Message) -> dict:
    return {
        "id": message.pk,
        "from": FROM[message.sender],
        "author": person_out(message.author) if message.author else None,
        "text": message.body,
        "attachments": [
            {"name": f.name, "url": f.url, "content_type": f.content_type, "size": f.size}
            for f in message.attachments.all()
        ],
        "created_at": message.created_at.isoformat(),
    }
