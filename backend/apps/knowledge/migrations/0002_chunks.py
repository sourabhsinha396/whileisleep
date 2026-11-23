import django.contrib.postgres.indexes
import django.contrib.postgres.search
import django.db.models.deletion
from django.conf import settings
from django.contrib.postgres.search import SearchVector
from django.db import migrations, models

from apps.knowledge import chunking


def index_existing_articles(apps, schema_editor):
    """Articles written before passages existed get theirs now (as indexing.index_article does)."""
    Article = apps.get_model("knowledge", "Article")
    Chunk = apps.get_model("knowledge", "Chunk")
    for article in Article.objects.iterator():
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
    config = settings.SEARCH_LANGUAGE
    Chunk.objects.update(
        search=SearchVector("title", weight="A", config=config)
        + SearchVector("heading", weight="A", config=config)
        + SearchVector("text", weight="B", config=config)
    )


class Migration(migrations.Migration):
    dependencies = [
        ("knowledge", "0001_initial"),
        ("workspaces", "0004_identity"),
    ]

    operations = [
        migrations.CreateModel(
            name="Chunk",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("position", models.PositiveIntegerField()),
                ("title", models.CharField(max_length=200)),
                ("heading", models.CharField(blank=True, max_length=500)),
                ("text", models.TextField(blank=True)),
                ("search", django.contrib.postgres.search.SearchVectorField(null=True)),
                (
                    "article",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="chunks", to="knowledge.article"
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="workspaces.workspace"
                    ),
                ),
            ],
            options={
                "ordering": ["article_id", "position"],
                "indexes": [django.contrib.postgres.indexes.GinIndex(fields=["search"], name="chunk_search_gin")],
            },
        ),
        migrations.RunPython(index_existing_articles, migrations.RunPython.noop),
    ]
