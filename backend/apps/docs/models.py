from django.db import models


class DocPage(models.Model):
    """What a superuser changed on one page of the docs. The pages themselves are files in the frontend."""

    page = models.SlugField(max_length=100, unique=True)
    # Markdown shown instead of the file's. Empty: the file's.
    body = models.TextField(blank=True)
    # The video at the top. Empty: none.
    youtube_id = models.CharField(max_length=11, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.page
