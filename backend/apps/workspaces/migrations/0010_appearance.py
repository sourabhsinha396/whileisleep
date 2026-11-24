from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("workspaces", "0009_providers")]

    operations = [
        migrations.AddField(
            model_name="workspace",
            name="background",
            field=models.CharField(
                choices=[
                    ("plain", "Plain"),
                    ("dots", "Dots"),
                    ("grid", "Grid"),
                    ("stripes", "Stripes"),
                    ("bubbles", "Bubbles"),
                ],
                db_default="plain",
                default="plain",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="workspace",
            name="color_mode",
            field=models.CharField(
                choices=[("light", "Light"), ("dark", "Dark"), ("auto", "Auto")],
                db_default="light",
                default="light",
                max_length=8,
            ),
        ),
    ]
