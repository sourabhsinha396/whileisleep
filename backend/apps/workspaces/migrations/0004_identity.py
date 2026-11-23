import whileisleep.fields
from django.db import migrations

from apps.workspaces.models import new_identity_secret


def give_each_workspace_a_secret(apps, schema_editor):
    """A default on AddField would hand every existing workspace the same secret."""
    Workspace = apps.get_model("workspaces", "Workspace")
    for workspace in Workspace.objects.filter(identity_secret=""):
        workspace.identity_secret = new_identity_secret()
        workspace.save(update_fields=["identity_secret"])


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0003_encrypt_secrets"),
    ]

    operations = [
        migrations.AddField(
            model_name="workspace",
            name="identity_secret",
            field=whileisleep.fields.EncryptedTextField(blank=True, default=""),
        ),
        migrations.RunPython(give_each_workspace_a_secret, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="workspace",
            name="identity_secret",
            field=whileisleep.fields.EncryptedTextField(default=new_identity_secret),
        ),
    ]
