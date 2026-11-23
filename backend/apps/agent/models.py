from django.core.validators import RegexValidator
from django.db import models

from apps.workspaces.models import Workspace

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
    # Sent with every call, e.g. {"Authorization": "Bearer ..."}. Never shown to visitors or the model.
    headers = models.JSONField(default=dict, blank=True)
    enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="unique_tool_name_per_workspace")]

    def __str__(self):
        return self.name
