from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from . import attributes
from .models import Conversation, Message, Visitor


def add_message(
    conversation: Conversation,
    sender: str,
    body: str = "",
    *,
    author=None,
    a2ui: list | None = None,
    is_note: bool = False,
    intent: str = "",
    intent_data: dict | None = None,
    form: dict | None = None,
) -> Message:
    message = Message.objects.create(
        conversation=conversation,
        sender=sender,
        body=body,
        author=author,
        a2ui=a2ui,
        is_note=is_note,
        intent=intent,
        intent_data=intent_data or {},
        form=form,
    )
    conversation.last_message_at = message.created_at
    fields = ["last_message_at"]
    if sender == Message.Sender.VISITOR:
        conversation.unread = True
        fields.append("unread")
        # A visitor writing again reopens a resolved conversation.
        if conversation.status == Conversation.Status.RESOLVED:
            conversation.status = Conversation.Status.OPEN
            fields.append("status")
    elif sender == Message.Sender.AGENT and not is_note:
        # A teammate answered: the bot steps aside for this conversation.
        conversation.human_requested = True
        fields.append("human_requested")
    conversation.save(update_fields=fields)
    return message


def is_stale(conversation: Conversation) -> bool:
    """Quiet for so long that a new message starts a new conversation."""
    return timezone.now() - conversation.last_message_at > timedelta(hours=settings.CONVERSATION_IDLE_HOURS)


def current_conversation(visitor: Visitor) -> Conversation | None:
    """The visitor's most recent conversation, which the widget shows.

    After the visitor starts a new chat, older conversations stay hidden unless someone
    writes in them again (a teammate's late reply still reaches the visitor).
    """
    conversations = visitor.conversations.order_by("-last_message_at")
    if visitor.chat_cleared_at:
        conversations = conversations.filter(last_message_at__gt=visitor.chat_cleared_at)
    return conversations.first()


def touch_visitor(visitor: Visitor, *, details: dict | None = None, **page) -> None:
    """Records where the visitor is now. `details` are attributes the host page sent with
    identify() (name, email, plan...): unsigned, so they are stored as Source.HOST."""
    for field, value in page.items():
        if value is not None:
            setattr(visitor, field, value[: Visitor._meta.get_field(field).max_length])
    visitor.last_seen = timezone.now()
    visitor.save()
    if details:
        attributes.set_many(visitor, details, attributes.Source.HOST)
