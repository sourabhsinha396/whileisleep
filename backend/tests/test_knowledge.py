"""Articles are split into passages; search finds passages with Postgres full-text search."""

import pytest
from django.core.management import call_command

from apps.knowledge import chunking, search
from apps.knowledge.models import Article, Chunk

from .conftest import Api
from .factories import ArticleFactory, WorkspaceFactory

# --- Splitting (no database) ---


def test_sections_become_passages_that_remember_their_headings():
    body = (
        "Intro paragraph.\n\n"
        "# Refunds\n\nWe refund within 30 days.\n\n"
        "## Digital products\n\nNo refunds after download.\n\n"
        "# Shipping\n\nWe ship worldwide."
    )
    assert chunking.split(body) == [
        chunking.Piece("", "Intro paragraph."),
        chunking.Piece("Refunds", "We refund within 30 days."),
        chunking.Piece("Refunds > Digital products", "No refunds after download."),
        chunking.Piece("Shipping", "We ship worldwide."),
    ]


def test_a_sibling_heading_replaces_the_previous_one_at_its_level():
    body = "# A\n\n## A1\n\none\n\n## A2\n\ntwo\n\n# B\n\nthree"
    assert [piece.heading for piece in chunking.split(body)] == ["A > A1", "A > A2", "B"]


def test_a_heading_right_after_text_still_starts_a_section():
    assert chunking.split("first\n# Next\nsecond") == [chunking.Piece("", "first"), chunking.Piece("Next", "second")]


def test_short_paragraphs_share_a_passage():
    assert chunking.split("One.\n\nTwo.\n\nThree.") == [chunking.Piece("", "One.\n\nTwo.\n\nThree.")]


def test_a_long_section_is_split_between_paragraphs():
    paragraph = "word " * 150  # about 750 characters
    pieces = chunking.split(f"# Guide\n\n{paragraph}\n\n{paragraph}\n\n{paragraph}")
    assert len(pieces) == 3
    assert all(piece.heading == "Guide" and len(piece.text) <= chunking.MAX_CHARS for piece in pieces)


def test_a_huge_paragraph_is_cut_at_sentence_ends():
    sentence = "This sentence is exactly forty characters. "
    pieces = chunking.split(sentence * 100)
    assert len(pieces) > 1
    assert all(len(piece.text) <= chunking.MAX_CHARS for piece in pieces)
    assert all(piece.text.endswith(".") for piece in pieces)


def test_text_without_sentence_ends_is_cut_hard_and_nothing_is_lost():
    blob = "x" * (chunking.MAX_CHARS * 2 + 10)
    pieces = chunking.split(blob)
    assert [len(piece.text) for piece in pieces] == [chunking.MAX_CHARS, chunking.MAX_CHARS, 10]


@pytest.mark.parametrize("body", ["", "   \n\n  ", None])
def test_an_empty_body_has_no_passages(body):
    assert chunking.split(body) == []


def test_windows_line_endings_are_handled():
    assert chunking.split("# A\r\n\r\ntext\r\n") == [chunking.Piece("A", "text")]


# --- Indexing ---

pytestmark_db = pytest.mark.django_db


@pytestmark_db
def test_saving_an_article_indexes_it():
    article = ArticleFactory(title="Refund policy", body="# Rules\n\nWithin 30 days.\n\n# Exceptions\n\nGift cards.")
    chunks = list(Chunk.objects.filter(article=article))
    assert [(c.position, c.title, c.heading) for c in chunks] == [
        (0, "Refund policy", "Rules"),
        (1, "Refund policy", "Exceptions"),
    ]
    assert all(c.workspace_id == article.workspace_id and c.search for c in chunks)


@pytestmark_db
def test_editing_an_article_replaces_its_passages():
    article = ArticleFactory(body="We ship by sea.")
    article.body = "We ship by air."
    article.save()
    assert [c.text for c in Chunk.objects.filter(article=article)] == ["We ship by air."]
    assert search.search(article.workspace, "sea") == []


@pytestmark_db
def test_an_article_with_only_a_title_can_still_be_found():
    article = ArticleFactory(title="Opening hours", body="")
    assert search.search(article.workspace, "opening hours") == [article]


@pytestmark_db
def test_deleting_an_article_removes_its_passages():
    article = ArticleFactory()
    article.delete()
    assert Chunk.objects.count() == 0


@pytestmark_db
def test_reindex_command_rebuilds_everything():
    article = ArticleFactory(body="Refunds within 30 days.")
    Chunk.objects.all().delete()
    call_command("reindex_knowledge")
    assert search.search(article.workspace, "refunds") == [article]


# --- Search ---


@pytestmark_db
def test_search_understands_word_forms():
    article = ArticleFactory(title="Returns", body="You can return shipped items for a refund.")
    # "refunds", "shipping", "returned": none of these exact words is in the article.
    for query in ("refunds", "shipping", "returned"):
        assert search.search(article.workspace, query) == [article], query


@pytestmark_db
def test_a_question_matches_without_every_word():
    article = ArticleFactory(title="Refund policy", body="Refunds are made within 30 days.")
    assert search.search(article.workspace, "how long do refunds usually take please?") == [article]


@pytestmark_db
def test_title_matches_outrank_body_matches():
    workspace = WorkspaceFactory()
    mention = ArticleFactory(workspace=workspace, title="Gift cards", body="Gift cards can't be used for shipping.")
    about = ArticleFactory(workspace=workspace, title="Shipping", body="We send parcels worldwide.")
    assert search.search(workspace, "shipping") == [about, mention]


@pytestmark_db
def test_more_matching_words_rank_higher():
    workspace = WorkspaceFactory()
    partial = ArticleFactory(workspace=workspace, title="A", body="We ship to many countries.")
    full = ArticleFactory(workspace=workspace, title="B", body="We ship to Canada in five days.")
    assert search.search(workspace, "ship to canada") == [full, partial]


@pytestmark_db
def test_search_stays_inside_the_workspace_and_skips_unpublished():
    workspace = WorkspaceFactory()
    ArticleFactory(title="Refunds elsewhere", body="refund")
    ArticleFactory(workspace=workspace, title="Draft refunds", body="refund", published=False)
    assert search.search(workspace, "refund") == []


@pytestmark_db
@pytest.mark.parametrize("query", ["", "   ", "the and of", "a", "?!", "hi", "thanks"])
def test_queries_with_nothing_to_search_for_find_nothing(query):
    workspace = WorkspaceFactory()
    ArticleFactory(workspace=workspace, title="The and of a hi thanks", body="the and of a hi thanks")
    assert search.search(workspace, query) == []


@pytestmark_db
@pytest.mark.parametrize("query", ["refund & | ! ( ) : * <->", "'; DROP TABLE knowledge_chunk; --", "a:*b", "\\"])
def test_search_operators_in_a_query_are_just_text(query):
    workspace = WorkspaceFactory()
    ArticleFactory(workspace=workspace, title="Refund policy", body="x")
    search.search(workspace, query)  # must not raise
    assert Chunk.objects.count() == 1


@pytestmark_db
def test_other_scripts_are_searchable():
    article = ArticleFactory(title="धनवापसी नीति", body="धनवापसी 30 दिनों के भीतर।")
    assert search.search(article.workspace, "धनवापसी") == [article]


@pytestmark_db
def test_each_article_appears_once():
    article = ArticleFactory(title="Refunds", body="# One\n\nrefund\n\n# Two\n\nrefund\n\n# Three\n\nrefund")
    assert search.search(article.workspace, "refund", limit=5) == [article]


@pytestmark_db
def test_prefix_search_finds_words_being_typed():
    article = ArticleFactory(title="Refund policy", body="x")
    assert search.search(article.workspace, "refu") == []
    assert search.search(article.workspace, "refu", prefix=True) == [article]
    assert search.search(article.workspace, "policy refu", prefix=True) == [article]


# --- Passages for the AI ---


@pytestmark_db
def test_passages_return_the_matching_section_not_the_whole_article():
    article = ArticleFactory(
        title="Store policies",
        body="# Refunds\n\nRefunds within 30 days.\n\n# Shipping\n\nWe ship to Canada in 5 days.",
    )
    [best, *_] = search.passages(article.workspace, "do you ship to Canada?")
    assert best.text == "We ship to Canada in 5 days."
    assert best.label == "Store policies > Shipping"
    assert best.article_id == article.id


@pytestmark_db
def test_passages_respect_the_size_budget():
    workspace = WorkspaceFactory()
    for n in range(6):
        ArticleFactory(workspace=workspace, title=f"Refund note {n}", body="refund " * 100)
    found = search.passages(workspace, "refund", budget_chars=1500)
    assert 1 <= len(found) < 6
    assert sum(len(p.text) for p in found) <= 1500


@pytestmark_db
def test_the_first_passage_is_kept_even_when_it_is_over_budget():
    article = ArticleFactory(title="Refunds", body="refund " * 100)
    assert len(search.passages(article.workspace, "refund", budget_chars=10)) == 1


@pytestmark_db
def test_one_article_cannot_take_every_slot():
    workspace = WorkspaceFactory()
    sections = "\n\n".join(f"# Part {n}\n\nrefund details {n}" for n in range(6))
    long_one = ArticleFactory(workspace=workspace, title="Refund handbook", body=sections)
    other = ArticleFactory(workspace=workspace, title="Refund form", body="refund form link")
    found = search.passages(workspace, "refund", limit=6)
    assert [p.article_id for p in found].count(long_one.id) == search.PER_ARTICLE
    assert other.id in [p.article_id for p in found]


@pytestmark_db
def test_passages_follow_the_configured_default_budget(settings):
    settings.KNOWLEDGE_BUDGET_CHARS = 700
    workspace = WorkspaceFactory()
    for n in range(4):
        ArticleFactory(workspace=workspace, title=f"Refund {n}", body="refund " * 90)
    assert len(search.passages(workspace, "refund")) == 1


# --- Through the APIs ---


@pytestmark_db
def test_widget_help_search_matches_while_typing():
    workspace = WorkspaceFactory()
    article = ArticleFactory(workspace=workspace, title="Shipping to Canada", body="5 to 8 days.")
    found = Api().get(f"/widget/{workspace.public_key}/articles", q="shipp").json()
    assert [row["id"] for row in found] == [article.id]


@pytestmark_db
def test_editing_through_the_api_updates_search(api, workspace):
    created = api.post(f"/workspaces/{workspace.id}/articles", {"title": "Hours", "body": "Open 9 to 5."}).json()
    api.put(f"/workspaces/{workspace.id}/articles/{created['id']}", {"title": "Hours", "body": "Open at noon."})
    assert search.search(workspace, "noon") == [Article.objects.get(pk=created["id"])]
    assert search.search(workspace, "9") == []
