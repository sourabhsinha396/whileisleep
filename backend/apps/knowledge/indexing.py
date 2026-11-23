"""Keeps an article's passages (Chunk rows) in step with the article."""

from django.conf import settings
from django.contrib.postgres.search import SearchVector
from django.db import transaction

from . import chunking
from .models import Article, Chunk


def search_vector() -> SearchVector:
    """Title and headings count more than body text: a passage *about* refunds should
    outrank one that mentions them in passing."""
    config = settings.SEARCH_LANGUAGE
    return (
        SearchVector("title", weight="A", config=config)
        + SearchVector("heading", weight="A", config=config)
        + SearchVector("text", weight="B", config=config)
    )


@transaction.atomic
def index_article(article: Article) -> int:
    """Replaces the article's passages with fresh ones. Returns how many it has now."""
    Chunk.objects.filter(article=article).delete()
    # An article with no body still gets one passage, so its title can be found.
    pieces = chunking.split(article.body) or [chunking.Piece(heading="", text="")]
    Chunk.objects.bulk_create(
        Chunk(
            workspace_id=article.workspace_id,
            article=article,
            position=position,
            title=article.title,
            heading=piece.heading[:500],
            text=piece.text,
        )
        for position, piece in enumerate(pieces)
    )
    Chunk.objects.filter(article=article).update(search=search_vector())
    return len(pieces)


def reindex_all() -> int:
    """Rebuilds every article's passages, e.g. after changing SEARCH_LANGUAGE."""
    count = 0
    for article in Article.objects.iterator():
        index_article(article)
        count += 1
    return count
