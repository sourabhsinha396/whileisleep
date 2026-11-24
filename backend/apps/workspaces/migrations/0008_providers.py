import whileisleep.fields
from django.db import migrations, models

PROVIDERS = [
    ("openai", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("google", "Google Gemini"),
    ("openrouter", "OpenRouter"),
]


def keep_openrouter_keys(apps, schema_editor):
    """The one key there was becomes the OpenRouter key among several."""
    Organization = apps.get_model("workspaces", "Organization")
    for organization in Organization.objects.exclude(openrouter_api_key=""):
        organization.provider_keys = {"openrouter": organization.openrouter_api_key}
        organization.save(update_fields=["provider_keys"])


def restore_openrouter_keys(apps, schema_editor):
    Organization = apps.get_model("workspaces", "Organization")
    for organization in Organization.objects.exclude(provider_keys=""):
        organization.openrouter_api_key = organization.provider_keys.get("openrouter", "")
        organization.save(update_fields=["openrouter_api_key"])


class Migration(migrations.Migration):
    dependencies = [
        ("workspaces", "0007_logo"),
    ]

    operations = [
        migrations.AddField(
            model_name="organization",
            name="provider_keys",
            field=whileisleep.fields.EncryptedJSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="organization",
            name="llm_provider",
            field=models.CharField(choices=PROVIDERS, default="openrouter", max_length=20),
        ),
        migrations.AddField(
            model_name="organization",
            name="fallback_provider",
            field=models.CharField(blank=True, choices=PROVIDERS, default="", max_length=20),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="organization",
            name="fallback_model",
            field=models.CharField(blank=True, default="", max_length=200),
            preserve_default=False,
        ),
        migrations.RunPython(keep_openrouter_keys, restore_openrouter_keys),
        migrations.RemoveField(model_name="organization", name="openrouter_api_key"),
    ]
