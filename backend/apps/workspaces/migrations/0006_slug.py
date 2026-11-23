import django.core.validators
from django.db import migrations, models
from django.utils.text import slugify


def give_each_workspace_a_slug(apps, schema_editor):
    """Existing workspaces get a slug from their name, numbered where two names collide."""
    Workspace = apps.get_model("workspaces", "Workspace")
    taken = set()
    for workspace in Workspace.objects.order_by("id"):
        base = slugify(workspace.name)[:54].strip("-") or "workspace"
        slug, number = base, 2
        while slug in taken:
            slug = f"{base}-{number}"
            number += 1
        taken.add(slug)
        workspace.slug = slug
        workspace.save(update_fields=["slug"])


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0005_timezone"),
    ]

    operations = [
        # Not unique yet: every existing row starts with the same empty value.
        migrations.AddField(
            model_name="workspace",
            name="slug",
            field=models.CharField(max_length=60, blank=True, default=""),
        ),
        migrations.RunPython(give_each_workspace_a_slug, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="workspace",
            name="slug",
            field=models.SlugField(
                blank=True,
                max_length=60,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        "^[a-z0-9]+(?:-[a-z0-9]+)*$",
                        "Lowercase letters and digits, with single hyphens between words.",
                    )
                ],
            ),
        ),
    ]
