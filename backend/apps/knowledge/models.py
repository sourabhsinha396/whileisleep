from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver

from apps.workspaces.models import Workspace
from whileisleep import images
from whileisleep.folders import article_image


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


class ArticleImage(models.Model):
    """A picture uploaded for an article. The article shows it with Markdown: ![alt](url)."""

    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name="images")
    file = models.FileField(upload_to=article_image, max_length=200)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.file.name


@receiver(post_delete, sender=ArticleImage)
def delete_image_file(sender, instance, **kwargs):
    """Unless the text was copied into another article, which then shows the picture too."""
    copies = Article.objects.filter(
        workspace_id=instance.article.workspace_id, body__contains=instance.file.name
    ).exclude(pk=instance.article_id)
    if not copies.exists():
        images.delete_later(instance.file.name)


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
