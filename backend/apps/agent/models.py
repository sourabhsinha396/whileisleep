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
    body (POST). `{visitor.KEY}` placeholders (`{visitor.email}`, `{visitor.external_id}`,
    any attribute) take the visitor's details, never the model's, so the model can't ask
    about someone else, and only details the host site verified (see http_tools).
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
    # Fill {visitor.KEY} placeholders from unverified attributes too (an email typed into a
    # form). Only for tools where knowing the value reveals nothing private.
    allow_unverified_identity = models.BooleanField(default=False)
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


class Turn(models.Model):
    """What happened after one visitor message: which stage of the pipeline answered it, and
    what that cost.

    The pipeline (apps.agent.pipeline) tries the cheapest way to answer first: a rule in
    code, then the AI. `stage` says where it stopped, so a workspace can see how much of its
    traffic never needed the model, and `steps` says what was looked up on the way.
    """

    class Stage(models.TextChoices):
        RULE = "rule"  # a rule's fixed reply answered; no model call
        GUARD = "guard"  # a limit stopped the AI and a person was asked for
        AI = "ai"  # the model answered
        FALLBACK = "fallback"  # the model was unavailable; a help center search answered
        NONE = "none"  # nothing replied: the AI is off or a person has the conversation

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="turns")
    conversation = models.ForeignKey("conversations.Conversation", on_delete=models.CASCADE, related_name="turns")
    # The visitor message that started the turn, and what was sent back.
    trigger = models.ForeignKey("conversations.Message", null=True, on_delete=models.SET_NULL, related_name="+")
    reply = models.ForeignKey("conversations.Message", null=True, on_delete=models.SET_NULL, related_name="+")
    stage = models.CharField(max_length=10, choices=Stage.choices)
    # The rule that matched, whether it answered or only instructed the AI.
    rule = models.ForeignKey(Rule, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")

    model = models.CharField(max_length=200, blank=True)
    llm_calls = models.PositiveSmallIntegerField(default=0)
    input_tokens = models.PositiveIntegerField(default=0)
    # The part of input_tokens read from the provider's prompt cache.
    cached_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    # US dollars, when the provider reports it.
    cost = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    # In order: [{"type": "retrieval", ...}, {"type": "tool", "name": ..., "result": ...}].
    steps = models.JSONField(default=list, blank=True)
    # Why the AI couldn't answer, when it couldn't (a rejected key, no credits).
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["workspace", "created_at"], name="turn_workspace_time")]

    def __str__(self):
        return f"{self.stage} turn in conversation {self.conversation_id}"
