from django.db import migrations, models


def forget_removed(apps, schema_editor):
    """Three simple patterns were replaced by drawn ones."""
    apps.get_model("workspaces", "Workspace").objects.filter(background__in=["dots", "grid", "stripes"]).update(
        background="plain"
    )


class Migration(migrations.Migration):
    dependencies = [("workspaces", "0010_appearance")]

    operations = [
        migrations.RunPython(forget_removed, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="workspace",
            name="background",
            field=models.CharField(
                choices=[
                    ("plain", "Plain"),
                    ("bubbles", "Bubbles"),
                    ("confetti", "Confetti"),
                    ("chat", "Chat"),
                    ("night", "Night"),
                    ("stars", "Stars"),
                    ("leaves", "Leaves"),
                    ("petals", "Petals"),
                    ("waves", "Waves"),
                    ("hexagons", "Hexagons"),
                    ("triangles", "Triangles"),
                    ("diamonds", "Diamonds"),
                    ("circuit", "Circuit"),
                ],
                db_default="plain",
                default="plain",
                max_length=16,
            ),
        ),
    ]
