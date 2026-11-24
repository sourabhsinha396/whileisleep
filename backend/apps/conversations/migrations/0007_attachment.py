import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0006_identity"),
        ("workspaces", "0008_storage_bucket"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Attachment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("path", models.CharField(max_length=200)),
                ("url", models.CharField(max_length=600)),
                ("name", models.CharField(max_length=120)),
                ("content_type", models.CharField(max_length=100)),
                ("size", models.PositiveIntegerField()),
                ("width", models.PositiveIntegerField(blank=True, null=True)),
                ("height", models.PositiveIntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "bucket",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="attachments",
                        to="workspaces.bucket",
                    ),
                ),
                (
                    "message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="conversations.message",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "visitor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to="conversations.visitor",
                    ),
                ),
                (
                    "workspace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="+", to="workspaces.workspace"
                    ),
                ),
            ],
            options={"ordering": ["id"]},
        ),
    ]
