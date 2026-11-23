from django.db import migrations, models


def copy_names_and_emails(apps, schema_editor):
    """Names and emails collected so far become attributes. Nothing signed them, so they
    are recorded as typed by the visitor."""
    Visitor = apps.get_model("conversations", "Visitor")
    for visitor in Visitor.objects.exclude(name="", email="").iterator():
        attributes = {}
        if visitor.name:
            attributes["name"] = {"value": visitor.name, "source": "visitor"}
        if visitor.email:
            attributes["email"] = {"value": visitor.email, "source": "visitor"}
        visitor.attributes = attributes
        visitor.save(update_fields=["attributes"])


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0004_visitor_chat_cleared_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="conversation",
            name="attributes",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="visitor",
            name="attributes",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(copy_names_and_emails, migrations.RunPython.noop),
    ]
