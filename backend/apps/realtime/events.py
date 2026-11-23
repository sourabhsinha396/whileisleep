"""What the widget and the inbox hear about, as it happens.

Every event is {"event": name, "data": {...}} on a channel from apps.realtime.bus:

- message: a message was added. The visitor's channel gets only what the widget shows.
- conversation: its status, hand-off or unread flag changed. The inbox gets the whole row,
  the widget only whether a person has taken over.
- status: what the AI is doing right now ("Searching the help center"), from the steps a
  Turn records; empty text when it is done.
- typing: someone is typing. The visitor's typing goes to the team and a teammate's to
  the visitor. No text, only who.
- presence: a visitor came online or left (apps.realtime.presence).

Events are published once the database transaction commits, so a browser that reacts by
reading the API finds what the event announced.
"""

from django.core.cache import cache
from django.db import transaction

from apps.conversations.models import Conversation, Message

from . import bus


def after_commit(function) -> None:
    transaction.on_commit(function)


def visible_to_visitor(message: Message) -> bool:
    return not message.is_note and message.sender != Message.Sender.SYSTEM


def message_added(message: Message) -> None:
    def send():
        # Imported here: serializers ask apps.realtime.presence whether visitors are online.
        from apps.conversations.serializers import message_out

        conversation = message.conversation
        data = {"conversation_id": conversation.id, "message": message_out(message)}
        bus.publish([bus.workspace_channel(conversation.workspace_id)], "message", data)
        if visible_to_visitor(message):
            bus.publish([bus.visitor_channel(conversation.visitor_id)], "message", data)

    after_commit(send)


def conversation_changed(conversation: Conversation) -> None:
    def send():
        from apps.conversations.serializers import conversation_row

        last = conversation.messages.filter(is_note=False).order_by("-id").first()
        bus.publish(
            [bus.workspace_channel(conversation.workspace_id)], "conversation", conversation_row(conversation, last)
        )
        bus.publish(
            [bus.visitor_channel(conversation.visitor_id)],
            "conversation",
            {"id": conversation.id, "human_requested": conversation.human_requested},
        )

    after_commit(send)


def bot_status(conversation: Conversation, text: str) -> None:
    data = {"conversation_id": conversation.id, "text": text}
    channels = [bus.workspace_channel(conversation.workspace_id), bus.visitor_channel(conversation.visitor_id)]
    after_commit(lambda: bus.publish(channels, "status", data))


# Browsers send typing at most every few seconds; this many seconds between events is enough
# to keep the other side's indicator on, and stops a misbehaving client from flooding.
TYPING_EVERY_SECONDS = 2


def typing(conversation: Conversation, sender: str, name: str = "", who: str = "") -> bool:
    """`sender` is "visitor" or "agent"; each side hears only the other. `who` tells apart
    teammates typing in the same conversation. Returns False when throttled."""
    if not cache.add(f"typing:{conversation.id}:{sender}:{who}", 1, timeout=TYPING_EVERY_SECONDS):
        return False
    data = {"conversation_id": conversation.id, "sender": sender, "name": name}
    channel = (
        bus.workspace_channel(conversation.workspace_id)
        if sender == Message.Sender.VISITOR
        else bus.visitor_channel(conversation.visitor_id)
    )
    after_commit(lambda: bus.publish([channel], "typing", data))
    return True
