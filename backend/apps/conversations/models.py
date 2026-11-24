import secrets

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from apps.workspaces.models import Bucket, Workspace


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
    # Set when the visitor starts a new chat; the widget hides conversations quiet since then.
    chat_cleared_at = models.DateTimeField(null=True, blank=True)
    # What we know about this person, with who said so: {"plan": {"value": "pro", "source":
    # "verified"}}. Read and written through apps.conversations.attributes; `name` and
    # `email` above mirror the attributes of the same name.
    attributes = models.JSONField(default=dict, blank=True)
    # The host site's own id for this user, from a signed identity token
    # (apps.conversations.identity). Empty for anonymous visitors.
    external_id = models.CharField(max_length=200, blank=True)
    # When a signed token last vouched for this visitor.
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["workspace", "external_id"],
                condition=~models.Q(external_id=""),
                name="one_visitor_per_external_id",
            )
        ]

    def __str__(self):
        return self.display_name

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None

    @property
    def display_name(self) -> str:
        return self.name or self.email or f"Visitor {self.pk}"

    @property
    def is_online(self) -> bool:
        from apps.realtime import presence

        return presence.is_online(self)


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
    # What we learned in this conversation (order_number, topic), same shape as
    # Visitor.attributes.
    attributes = models.JSONField(default=dict, blank=True)
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


class Attachment(models.Model):
    """A file in the customer's bucket, sent with a message (apps.conversations.attachments)."""

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="+")
    # Empty until the message it was uploaded for is sent.
    message = models.ForeignKey(Message, on_delete=models.CASCADE, null=True, blank=True, related_name="attachments")
    # Who uploaded it: a visitor or a teammate.
    visitor = models.ForeignKey(Visitor, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    # The bucket it is in; empty once that bucket is disconnected. `url` keeps working then.
    bucket = models.ForeignKey(Bucket, on_delete=models.SET_NULL, null=True, blank=True, related_name="attachments")
    path = models.CharField(max_length=200)
    url = models.CharField(max_length=600)
    # What it was called on the sender's device.
    name = models.CharField(max_length=120)
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    # Pictures only, so the space for one is there before it loads.
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.name


@receiver(post_delete, sender=Attachment)
def delete_attachment_file(sender, instance, **kwargs):
    from apps.knowledge.models import delete_from_bucket_later

    if instance.bucket_id:
        delete_from_bucket_later(instance.bucket_id, instance.path)
