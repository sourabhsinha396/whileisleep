"""Keyword search over a workspace's published articles. Good enough for small help centers;
swap for Postgres full-text or embeddings when a workspace has hundreds of articles."""

import re

from .models import Article

WORD = re.compile(r"[a-z0-9]+")
STOPWORDS = {
    "the", "and", "for", "you", "your", "are", "can", "how", "what", "does", "with", "have",
    "this", "that", "there", "any", "is", "do", "to", "of", "in", "on", "a", "an", "it", "my", "me", "i",
}  # fmt: skip


def words(text: str) -> set[str]:
    return {w for w in WORD.findall(text.lower()) if len(w) > 2 and w not in STOPWORDS}


def search(workspace, query: str, limit: int = 3) -> list[Article]:
    terms = words(query)
    if not terms:
        return []
    scored = []
    for article in Article.objects.filter(workspace=workspace, published=True):
        title, body = words(article.title), words(article.body)
        score = 3 * len(terms & title) + len(terms & body)
        if score:
            scored.append((score, article))
    scored.sort(key=lambda pair: (-pair[0], pair[1].title))
    return [article for _, article in scored[:limit]]
