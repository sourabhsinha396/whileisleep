import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def assign_organizations(apps, schema_editor):
    """Each existing workspace joins the organization of its first owner (made if needed)."""
    Organization = apps.get_model("workspaces", "Organization")
    Workspace = apps.get_model("workspaces", "Workspace")
    Membership = apps.get_model("workspaces", "Membership")
    for workspace in Workspace.objects.filter(organization__isnull=True):
        owner = Membership.objects.filter(workspace=workspace, role="owner").order_by("id").first()
        if owner is None:
            owner = Membership.objects.filter(workspace=workspace).order_by("id").first()
        if owner is None:
            workspace.delete()
            continue
        user = owner.user
        organization, _ = Organization.objects.get_or_create(
            owner=user, defaults={"name": f"{user.first_name or user.email}'s organization"}
        )
        workspace.organization = organization
        workspace.save(update_fields=["organization"])


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Organization",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("openrouter_api_key", models.CharField(blank=True, max_length=200)),
                ("llm_model", models.CharField(blank=True, max_length=200)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "owner",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="organization",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="workspace",
            name="organization",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="workspaces",
                to="workspaces.organization",
            ),
        ),
        migrations.RunPython(assign_organizations, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="workspace",
            name="organization",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="workspaces",
                to="workspaces.organization",
            ),
        ),
    ]
