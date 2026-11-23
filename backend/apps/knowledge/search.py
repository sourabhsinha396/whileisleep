"""Search over a workspace's published articles, by passage, with Postgres full-text search.

Two callers:

- the AI, which wants a few passages that fit a size budget (`passages`), and
- the widget's Help tab, which wants matching articles (`search`), also while typing.

A visitor's question is a sentence, not a query, so the words are OR-ed and ranked: a
passage matching more of them, or matching in its title or headings, comes first. Needing
every word (AND) would find nothing for "how long do refunds usually take please".
"""

import unicodedata
from dataclasses import dataclass

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import F

from .models import Article, Chunk

# Unicode categories that are part of a word: letters, numbers and marks. Marks matter:
# Hindi and Thai write vowels as marks, and without them a word falls apart.
WORD_CATEGORIES = "LNM"
STOPWORDS = {
    "the", "and", "for", "you", "your", "are", "can", "how", "what", "does", "with", "have",
    "this", "that", "there", "any", "is", "do", "to", "of", "in", "on", "a", "an", "it", "my", "me", "i",
    "please", "thanks", "thank", "hello", "hi", "hey",
}  # fmt: skip
MAX_TERMS = 16
# At most this many passages from one article, so one long article can't fill the budget.
PER_ARTICLE = 2


@dataclass(frozen=True)
class Passage:
    article_id: int
    title: str
    heading: str
    text: str
    rank: float

    @property
    def label(self) -> str:
        """Where the passage is from: "Refund policy > Digital products"."""
        return f"{self.title} > {self.heading}" if self.heading else self.title


def terms(query: str) -> list[str]:
    """The words worth searching for, in order, without repeats."""
    # Everything that isn't part of a word (spaces, punctuation, symbols) separates words.
    spaced = "".join(ch if unicodedata.category(ch)[0] in WORD_CATEGORIES else " " for ch in query.lower())
    seen: dict[str, None] = {}
    for word in spaced.split():
        if len(word) > 1 and word not in STOPWORDS:
            seen[word] = None
    return list(seen)[:MAX_TERMS]


def ts_query(query: str, prefix: bool = False) -> SearchQuery | None:
    """`refund | policy | digital`. With `prefix`, the last word also matches as a beginning
    ("refu" finds "refund"), for search-as-you-type."""
    words = terms(query)
    if not words:
        return None
    # Quoted, and free of punctuation (see terms), so no word can act as a query operator.
    quoted = [f"'{word}'" for word in words]
    if prefix:
        quoted[-1] += ":*"
    return SearchQuery(" | ".join(quoted), search_type="raw", config=settings.SEARCH_LANGUAGE)


def ranked(workspace, query: str, prefix: bool = False):
    """Matching passages of published articles, best first, or None for an empty query."""
    ts = ts_query(query, prefix)
    if ts is None:
        return None
    return (
        Chunk.objects.filter(workspace=workspace, article__published=True, search=ts)
        .annotate(rank=SearchRank(F("search"), ts))
        .order_by("-rank", "article_id", "position")
    )


def passages(workspace, query: str, limit: int = 6, budget_chars: int | None = None) -> list[Passage]:
    """The best passages for a question, at most `limit` and within `budget_chars` of text."""
    rows = ranked(workspace, query)
    if rows is None:
        return []
    budget = settings.KNOWLEDGE_BUDGET_CHARS if budget_chars is None else budget_chars
    found: list[Passage] = []
    per_article: dict[int, int] = {}
    used = 0
    # Read a few more than needed: some are skipped for their article or their size.
    for chunk in rows[: limit * 4]:
        if per_article.get(chunk.article_id, 0) >= PER_ARTICLE:
            continue
        size = len(chunk.text)
        if found and used + size > budget:
            continue
        per_article[chunk.article_id] = per_article.get(chunk.article_id, 0) + 1
        used += size
        found.append(Passage(chunk.article_id, chunk.title, chunk.heading, chunk.text, float(chunk.rank)))
        if len(found) >= limit:
            break
    return found


def search(workspace, query: str, limit: int = 3, prefix: bool = False) -> list[Article]:
    """The best-matching articles, each once, best first.

    With `prefix` (search-as-you-type), articles whose title contains the word being typed
    fill any remaining places: full-text search stores word stems, so "shipp" is not the
    beginning of the stored "ship".
    """
    rows = ranked(workspace, query, prefix)
    if rows is None:
        return []
    ids: dict[int, None] = {}
    for article_id in rows.values_list("article_id", flat=True)[: limit * 8]:
        ids[article_id] = None
        if len(ids) >= limit:
            break
    if prefix and len(ids) < limit:
        typing = terms(query)[-1]
        by_title = Article.objects.filter(workspace=workspace, published=True, title__icontains=typing)
        for article_id in by_title.exclude(pk__in=ids).values_list("pk", flat=True)[: limit - len(ids)]:
            ids[article_id] = None
    articles = Article.objects.in_bulk(list(ids))
    return [articles[article_id] for article_id in ids if article_id in articles]
