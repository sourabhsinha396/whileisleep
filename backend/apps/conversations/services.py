from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.realtime import events

from . import attributes, signals
from .models import Attachment, Conversation, Message, Visitor


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
    attachments: list[Attachment] = (),
    origin: str = "",
) -> Message:
    """`origin` is what it came through, if not the widget or the dashboard (signals.Event)."""
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
    if attachments:
        # Before anyone hears about the message. A file sent twice at once goes with the first.
        Attachment.objects.filter(pk__in=[a.pk for a in attachments], message=None).update(message=message)
    conversation.last_message_at = message.created_at
    fields = ["last_message_at"]
    reopened = False
    if sender == Message.Sender.VISITOR:
        conversation.unread = True
        fields.append("unread")
        # A visitor writing again reopens a resolved conversation.
        if conversation.status == Conversation.Status.RESOLVED:
            conversation.status = Conversation.Status.OPEN
            fields.append("status")
            reopened = True
    elif sender == Message.Sender.AGENT and not is_note:
        # A teammate answered: the bot steps aside for this conversation.
        conversation.human_requested = True
        fields.append("human_requested")
    conversation.save(update_fields=fields)
    events.message_added(message)
    events.conversation_changed(conversation)
    if reopened:
        signals.announce(signals.REOPENED, conversation, origin=origin)
    signals.announce(signals.MESSAGE, conversation, message=message, by=author, origin=origin)
    return message


def start_conversation(visitor: Visitor, *, by=None, **fields) -> Conversation:
    conversation = Conversation.objects.create(workspace=visitor.workspace, visitor=visitor, **fields)
    signals.announce(signals.STARTED, conversation, by=by)
    return conversation


def reply_as(user, conversation: Conversation, body: str, *, is_note=False, attachments=(), origin="") -> Message:
    """A teammate writes to the visitor, or a note for the team. Answering takes the conversation."""
    message = add_message(
        conversation,
        Message.Sender.AGENT,
        body,
        author=user,
        is_note=is_note,
        attachments=attachments,
        origin=origin,
    )
    if not is_note and conversation.assignee_id is None:
        conversation.assignee = user
        conversation.save(update_fields=["assignee"])
    return message


def request_human(conversation: Conversation, reason: str = "") -> None:
    """Hands the conversation to the team: the AI stays quiet until they give it back."""
    if conversation.human_requested:
        return
    conversation.human_requested = True
    conversation.unread = True
    conversation.save(update_fields=["human_requested", "unread"])
    note = "Visitor asked for a person." + (f" Reason: {reason}" if reason else "")
    add_message(conversation, Message.Sender.SYSTEM, note, is_note=True)
    signals.announce(signals.PERSON_REQUESTED, conversation, data={"reason": reason})


def set_status(conversation: Conversation, status: str, *, by=None, origin: str = "") -> None:
    if conversation.status == status:
        return
    conversation.status = status
    conversation.save(update_fields=["status"])
    events.conversation_changed(conversation)
    name = signals.RESOLVED if status == Conversation.Status.RESOLVED else signals.REOPENED
    signals.announce(name, conversation, by=by, origin=origin)


def set_human_requested(conversation: Conversation, requested: bool, *, by=None, origin: str = "") -> None:
    """A teammate takes the conversation from the AI, or gives it back."""
    if conversation.human_requested == requested:
        return
    conversation.human_requested = requested
    conversation.save(update_fields=["human_requested"])
    events.conversation_changed(conversation)
    if not requested:
        signals.announce(signals.AI_RESUMED, conversation, by=by, origin=origin)


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
