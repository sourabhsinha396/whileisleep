import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.workspaces.models import Workspace


def new_visitor_token() -> str:
    return "vt_" + secrets.token_urlsafe(24)


class Visitor(models.Model):
    """Someone browsing a workspace's website with the widget loaded."""

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="visitors")
    # Secret kept in the visitor's browser; it proves which visitor is calling.
    token = models.CharField(max_length=64, unique=True, default=new_visitor_token)
    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    current_url = models.CharField(max_length=1000, blank=True)
    page_title = models.CharField(max_length=300, blank=True)
    referrer = models.CharField(max_length=1000, blank=True)
    user_agent = models.CharField(max_length=400, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return self.display_name

    @property
    def display_name(self) -> str:
        return self.name or self.email or f"Visitor {self.pk}"

    @property
    def is_online(self) -> bool:
        return (timezone.now() - self.last_seen).total_seconds() < settings.ONLINE_WINDOW_SECONDS


class Conversation(models.Model):
    class Status(models.TextChoices):
        OPEN = "open"
        RESOLVED = "resolved"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="conversations")
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="conversations")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    assignee = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    # True once the visitor asks for a person or a teammate replies. The bot then stays quiet.
    human_requested = models.BooleanField(default=False)
    # A visitor message the team hasn't opened yet.
    unread = models.BooleanField(default=True)
    # Labels set by rules ("exam-request") or the team.
    tags = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-last_message_at"]

    def __str__(self):
        return f"#{self.pk} with {self.visitor}"


class Message(models.Model):
    class Sender(models.TextChoices):
        VISITOR = "visitor"
        AGENT = "agent"  # a human teammate
        BOT = "bot"  # the AI agent
        SYSTEM = "system"

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    sender = models.CharField(max_length=10, choices=Sender.choices)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    body = models.TextField(blank=True)
    # Optional A2UI v1.0 messages (createSurface, updateComponents...) the widget renders under the body.
    a2ui = models.JSONField(null=True, blank=True)
    # Internal notes are for teammates only and never reach the visitor.
    is_note = models.BooleanField(default=False)
    # Set by a button on the host site that opened the chat with this text: what the visitor
    # wants ("exam_request") and details ({"exam_code": "SY0-401"}). Visitor-supplied: treat
    # as untrusted input.
    intent = models.CharField(max_length=64, blank=True)
    intent_data = models.JSONField(default=dict, blank=True)
    # A bot message's form (apps.agent.forms spec) plus {"surface_id", "submitted"}, to check
    # the visitor's answers and stop a second submission.
    form = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.sender}: {self.body[:40]}"
