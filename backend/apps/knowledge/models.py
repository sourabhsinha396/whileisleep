from django.db import models

from apps.workspaces.models import Workspace


class Article(models.Model):
    """Knowledge base article. Shown in the widget and given to the AI agent as context."""

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="articles")
    title = models.CharField(max_length=200)
    body = models.TextField(help_text="Markdown")
    published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title
