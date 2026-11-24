from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.conversations.models import Conversation, Message
from apps.workspaces.models import Workspace
from whileisleep.fields import EncryptedJSONField


class Integration(models.Model):
    """A workspace's connection to one outside service, through a plugin (apps.integrations.plugin)."""

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="integrations")
    # The plugin's id. One that is no longer installed stays here, unused.
    plugin = models.CharField(max_length=40)
    # The account at the other end: its id there, which webhooks name, and what people call it.
    account_id = models.CharField(max_length=200, blank=True)
    account_name = models.CharField(max_length=200, blank=True)
    # Secret: encrypted in the database, and the API never returns them.
    credentials = EncryptedJSONField(blank=True)
    # What the owner chose on the plugin's settings page.
    config = models.JSONField(default=dict, blank=True)
    # Why it isn't working, for the dashboard. Empty when it is.
    last_error = models.TextField(blank=True)
    connected_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["plugin"]
        indexes = [models.Index(fields=["plugin", "account_id"], name="integration_account")]
        constraints = [
            models.UniqueConstraint(fields=["workspace", "plugin", "account_id"], name="one_integration_per_account")
        ]

    def __str__(self):
        return f"{self.plugin} of {self.workspace}"

    @property
    def origin(self) -> str:
        """How events say they came through this integration."""
        return f"integration:{self.pk}"


class Thread(models.Model):
    """Where a conversation is in the outside service, so replies there find their way back."""

    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="threads")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="+")
    external_id = models.CharField(max_length=200)
    # Whatever else the plugin needs to remember about it.
    data = models.JSONField(default=dict, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["integration", "conversation"], name="one_thread_per_conversation"),
            models.UniqueConstraint(fields=["integration", "external_id"], name="unique_thread_external_id"),
        ]

    def __str__(self):
        return f"{self.external_id} for {self.conversation}"


class Delivery(models.Model):
    """One event on its way to an integration. Written with the event, and sent by a worker. What
    arrived is deleted, or kept a few days for a plugin that keeps a log."""

    class Status(models.TextChoices):
        PENDING = "pending"
        FAILED = "failed"  # given up on; kept a while to see what went wrong
        SENT = "sent"

    integration = models.ForeignKey(Integration, on_delete=models.CASCADE, related_name="deliveries")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="+")
    # An apps.conversations.signals.Event, taken apart.
    event = models.CharField(max_length=40)
    message = models.ForeignKey(Message, null=True, on_delete=models.CASCADE, related_name="+")
    by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    data = models.JSONField(default=dict)
    status = models.CharField(max_length=10, choices=Status, default=Status.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    due_at = models.DateTimeField(default=timezone.now)
    # How it went: the service's answer, or what is wrong.
    detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["status", "due_at"], name="delivery_due")]

    def __str__(self):
        return f"{self.event} to {self.integration}"
