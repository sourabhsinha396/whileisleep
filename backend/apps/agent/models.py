from django.core.validators import RegexValidator
from django.db import models

from apps.workspaces.models import Workspace
from whileisleep.fields import EncryptedJSONField

tool_name = RegexValidator(
    r"^[a-z][a-z0-9_]{1,63}$", "Lowercase letters, digits and underscores, starting with a letter."
)


server_name = RegexValidator(r"^[a-z][a-z0-9]{1,23}$", "2 to 24 lowercase letters and digits, starting with a letter.")


class McpServer(models.Model):
    """A Model Context Protocol server the workspace connected. Its tools become Tool rows
    (apps.agent.mcp_tools), each switched on by the owner before the AI may call it."""

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="mcp_servers")
    # Short and plain: it starts the name of every tool from this server ("stripe__refund").
    name = models.CharField(max_length=24, validators=[server_name])
    url = models.CharField(max_length=1000)
    # Sent with every request, e.g. {"Authorization": "Bearer ..."}. Encrypted in the database.
    headers = EncryptedJSONField(blank=True)
    enabled = models.BooleanField(default=True)
    # Which generation of the protocol the server speaks ("modern" or "legacy"), learned on
    # first contact so later calls skip the probe. See apps.agent.mcp.
    era = models.CharField(max_length=10, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    # Why the last sync failed, for the dashboard. Empty when it worked.
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="unique_mcp_server_name")]

    def __str__(self):
        return self.name


class Tool(models.Model):
    """Something the AI agent may call to look up live data or act ("search_products",
    "get_order_status"...), so it answers from facts. Two kinds:

    - an HTTP endpoint on the workspace's own site, described by the fields below, or
    - a tool on a connected MCP server (`mcp_server` is set; `url` and `method` are unused).

    For HTTP tools:

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
    url = models.CharField(max_length=1000, blank=True)
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

    # --- For tools that come from an MCP server (see apps.agent.mcp_tools) ---
    mcp_server = models.ForeignKey(McpServer, null=True, blank=True, on_delete=models.CASCADE, related_name="tools")
    # The tool's name on the server; `name` above is the server's name plus this.
    remote_name = models.CharField(max_length=200, blank=True)
    # The server's own claim that the tool changes nothing. A hint for the owner.
    read_only = models.BooleanField(default=False)
    # A hash of the name, description and schema the server sends now, and of the ones the
    # owner approved by switching the tool on. When they differ the tool isn't offered.
    definition_hash = models.CharField(max_length=64, blank=True)
    approved_hash = models.CharField(max_length=64, blank=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="unique_tool_name_per_workspace")]

    def __str__(self):
        return self.name

    @property
    def needs_review(self) -> bool:
        """An MCP tool whose definition changed since the owner approved it (or never was)."""
        return self.mcp_server_id is not None and self.approved_hash != self.definition_hash


class Rule(models.Model):
    """When a visitor message meets the conditions, act in code before (or instead of) the AI.

    Rules are checked in `position` order and the first match wins. Use them for replies
    that must be exact or always happen, e.g. "exam_request → we'll add it within 12 hours".
    apps.agent.rules explains and runs them.
    """

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="rules")
    name = models.CharField(max_length=120)
    enabled = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)

    # When it applies: a condition tree, e.g. {"all": [{"field": "message.intent", "op":
    # "equals", "value": "exam_request"}]}. See apps.agent.conditions.
    conditions = models.JSONField(default=dict)
    # What it does, in order: [{"type": "tag", "value": "exam-request"}, {"type": "reply",
    # "text": "..."}]. See apps.agent.rules.
    actions = models.JSONField(default=list)
    # Also run after a person took over the conversation (the AI is paused then).
    also_when_human = models.BooleanField(default=False)

    match_count = models.PositiveIntegerField(default=0)
    last_matched_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]

    def __str__(self):
        return self.name


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
        SUPERSEDED = "superseded"  # the visitor wrote again first; the newer message's turn answers
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
