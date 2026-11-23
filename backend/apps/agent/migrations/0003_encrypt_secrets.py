import whileisleep.fields
from django.db import migrations


def encrypt_existing(apps, schema_editor):
    """Rows saved before this migration hold plain JSON; saving them again encrypts it."""
    Tool = apps.get_model("agent", "Tool")
    for tool in Tool.objects.all():
        tool.save(update_fields=["headers"])


class Migration(migrations.Migration):
    dependencies = [
        ("agent", "0002_rule_playbook"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tool",
            name="headers",
            field=whileisleep.fields.EncryptedJSONField(blank=True, default=dict),
        ),
        migrations.RunPython(encrypt_existing, migrations.RunPython.noop),
    ]
