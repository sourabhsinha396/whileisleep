"""Everything a plugin may use of whileisleep. Plugins import from here and nowhere else in
`apps`, so the rest can change without breaking them (tests/test_plugins.py checks ours)."""

from django.conf import settings
from django.contrib.auth import get_user_model

from apps.conversations.models import Conversation, Message
from apps.conversations.services import reply_as, set_human_requested, set_status
from apps.conversations.signals import AI_RESUMED, MESSAGE, PERSON_REQUESTED, REOPENED, RESOLVED, Event
from whileisleep import outbound

from .models import Integration, Thread
from .plugin import (
    BadRequest,
    Connection,
    Field,
    Job,
    Option,
    Plugin,
    PluginError,
    Received,
    WebhookRequest,
)

__all__ = [
    "AI_RESUMED",
    "MESSAGE",
    "PERSON_REQUESTED",
    "REOPENED",
    "RESOLVED",
    "BadRequest",
    "Connection",
    "Conversation",
    "Event",
    "Field",
    "Integration",
    "Job",
    "Message",
    "Option",
    "Plugin",
    "PluginError",
    "Received",
    "Thread",
    "WebhookRequest",
    "add_note",
    "display_name",
    "find_thread",
    "give_to_ai",
    "inbox_url",
    "integrations_of_account",
    "link_thread",
    "needs_person",
    "outbound",
    "reopen",
    "reply",
    "resolve",
    "teammate",
    "thread_of",
    "transcript",
]

# --- Looking things up ---


def integrations_of_account(plugin: Plugin, account_id: str):
    """Every workspace's connection to this account: one Slack can serve several sites."""
    return Integration.objects.filter(plugin=plugin.id, account_id=account_id)


def thread_of(integration: Integration, conversation: Conversation) -> Thread | None:
    return Thread.objects.filter(integration=integration, conversation=conversation).first()


def find_thread(plugin: Plugin, account_id: str, external_id: str) -> Thread | None:
    """The thread a webhook is about, with its integration and conversation."""
    return (
        Thread.objects.filter(
            integration__plugin=plugin.id, integration__account_id=account_id, external_id=external_id
        )
        .select_related("integration__workspace", "conversation__visitor", "conversation__workspace")
        .first()
    )


def link_thread(integration: Integration, conversation: Conversation, external_id: str, **data) -> Thread:
    return Thread.objects.create(integration=integration, conversation=conversation, external_id=external_id, data=data)


def teammate(workspace, email: str):
    """The member of the workspace with this email, if there is one. Only they may act for it."""
    if not email:
        return None
    return (
        get_user_model().objects.filter(email__iexact=email, is_active=True, memberships__workspace=workspace).first()
    )


def needs_person(conversation: Conversation) -> bool:
    """Nobody but the team will answer: it was handed over, or the AI is off."""
    return conversation.human_requested or not conversation.workspace.ai_enabled


def inbox_url(conversation: Conversation) -> str:
    return f"{settings.SITE_URL}/w/{conversation.workspace.slug}/inbox?c={conversation.pk}"


def display_name(user) -> str:
    return user.first_name or user.email


def transcript(conversation: Conversation, limit: int, up_to: int | None = None) -> list[Message]:
    """The newest messages the visitor can see, oldest first, ending with the message `up_to`."""
    rows = conversation.messages.filter(is_note=False).exclude(sender=Message.Sender.SYSTEM)
    if up_to is not None:
        rows = rows.filter(pk__lte=up_to)
    rows = rows.select_related("author").prefetch_related("attachments").order_by("-id")[:limit]
    return list(rows)[::-1]


# --- Acting for a teammate ---
# Each takes the integration it came through, which is then not told about it again.


def reply(integration: Integration, conversation: Conversation, user, text: str) -> Message:
    """Sends the visitor a message from this teammate."""
    return reply_as(user, conversation, text, origin=integration.origin)


def add_note(integration: Integration, conversation: Conversation, user, text: str) -> Message:
    """Only the team sees it."""
    return reply_as(user, conversation, text, is_note=True, origin=integration.origin)


def resolve(integration: Integration, conversation: Conversation, user) -> None:
    set_status(conversation, Conversation.Status.RESOLVED, by=user, origin=integration.origin)


def reopen(integration: Integration, conversation: Conversation, user) -> None:
    set_status(conversation, Conversation.Status.OPEN, by=user, origin=integration.origin)


def give_to_ai(integration: Integration, conversation: Conversation, user) -> None:
    set_human_requested(conversation, False, by=user, origin=integration.origin)
