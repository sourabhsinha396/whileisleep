from django.core.validators import RegexValidator
from django.db import models

from apps.workspaces.models import Workspace
from whileisleep.fields import EncryptedJSONField

tool_name = RegexValidator(
    r"^[a-z][a-z0-9_]{1,63}$", "Lowercase letters, digits and underscores, starting with a letter."
)


class Tool(models.Model):
    """An HTTP endpoint on the workspace's own site that the AI agent may call to look up
    live data ("search_products", "get_order_status"...), so it answers from facts.

    The agent fills the inputs described by `input_schema`. `{name}` placeholders in the
    URL take the input of that name. Other inputs go in the query string (GET) or a JSON
    body (POST). `{visitor.email}`, `{visitor.name}` and `{visitor.id}` placeholders take
    the visitor's details, never the model's, so the model can't ask about someone else.
    """

    class Method(models.TextChoices):
        GET = "GET"
        POST = "POST"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="tools")
    name = models.CharField(max_length=64, validators=[tool_name])
    # What the model reads to decide when to call it: what it returns and when to use it.
    description = models.TextField()
    method = models.CharField(max_length=4, choices=Method.choices, default=Method.GET)
    url = models.CharField(max_length=1000)
    # JSON Schema of the inputs, e.g. {"type": "object", "properties": {"q": {"type": "string"}}}.
    input_schema = models.JSONField(default=dict, blank=True)
    # Sent with every call, e.g. {"Authorization": "Bearer ..."}. Encrypted in the database and
    # never shown to visitors, the dashboard or the model.
    headers = EncryptedJSONField(blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="unique_tool_name_per_workspace")]

    def __str__(self):
        return self.name


class Rule(models.Model):
    """When a visitor message meets the conditions, act in code before (or instead of) the AI.

    Rules are checked in `position` order and the first match wins. All the conditions that
    are set must hold; empty ones are ignored. Use them for replies that must be exact or
    always happen, e.g. "exam_request → we'll add it within 12 hours".
    """

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="rules")
    name = models.CharField(max_length=120)
    enabled = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)

    # Conditions
    # The label a button on the host site attached to the message (window.whileisleep.open(text, {intent})).
    intent = models.CharField(max_length=64, blank=True)
    # One per line; the message must contain any of them (case-insensitive).
    keywords = models.TextField(blank=True)
    # The visitor's current page URL must contain this.
    page_contains = models.CharField(max_length=300, blank=True)
    first_message_only = models.BooleanField(default=False)

    # Actions
    # A fixed reply, sent instead of the AI's. {visitor.name}, {visitor.email} and {data.KEY}
    # (from the message's intent data) are filled in.
    reply = models.TextField(blank=True)
    # Without a fixed reply: an extra instruction the AI follows for this message only.
    ai_instruction = models.TextField(blank=True)
    tag = models.CharField(max_length=40, blank=True)
    handoff = models.BooleanField(default=False, help_text="Flag the conversation for a person.")
    # Also run after a person took over the conversation (the AI is paused then).
    also_when_human = models.BooleanField(default=False)

    match_count = models.PositiveIntegerField(default=0)
    last_matched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.name

    @property
    def keyword_list(self) -> list[str]:
        return [k.strip().lower() for k in self.keywords.splitlines() if k.strip()]


class Playbook(models.Model):
    """Written instructions for one kind of conversation ("Refund requests"). The AI sees only
    the title and `when_to_use` in every prompt, and reads the full instructions with the
    read_playbook tool when a conversation calls for them, so many playbooks stay cheap."""

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="playbooks")
    title = models.CharField(max_length=120)
    when_to_use = models.CharField(max_length=300)
    instructions = models.TextField()
    enabled = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        constraints = [models.UniqueConstraint(fields=["workspace", "title"], name="unique_playbook_title")]

    def __str__(self):
        return self.title
