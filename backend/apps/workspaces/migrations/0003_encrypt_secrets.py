import whileisleep.fields
from django.db import migrations


def encrypt_existing(apps, schema_editor):
    """Keys saved before this migration are plain text; saving them again encrypts them."""
    Organization = apps.get_model("workspaces", "Organization")
    for organization in Organization.objects.exclude(openrouter_api_key=""):
        organization.save(update_fields=["openrouter_api_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0002_organization"),
    ]

    operations = [
        migrations.AlterField(
            model_name="organization",
            name="openrouter_api_key",
            field=whileisleep.fields.EncryptedTextField(blank=True),
        ),
        migrations.RunPython(encrypt_existing, migrations.RunPython.noop),
    ]
