from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
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

    def save(self, *args, **kwargs):
        """Saving an article re-indexes it for search, so the two can't drift apart."""
        super().save(*args, **kwargs)
        from .indexing import index_article

        index_article(self)


class Chunk(models.Model):
    """One passage of an article: what search finds and what the AI reads.

    Rebuilt from the article whenever it is saved (apps.knowledge.indexing); never edited
    by hand. `workspace` and `title` repeat the article's so a search needs no join.
    """

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="+")
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="chunks")
    # Order within the article.
    position = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    # The headings above the passage, e.g. "Refunds > Digital products".
    heading = models.CharField(max_length=500, blank=True)
    text = models.TextField(blank=True)
    # Postgres full-text vector of title and heading (weighted high) and text.
    search = SearchVectorField(null=True)

    class Meta:
        ordering = ["article_id", "position"]
        indexes = [GinIndex(fields=["search"], name="chunk_search_gin")]

    def __str__(self):
        return f"{self.title} #{self.position}"
