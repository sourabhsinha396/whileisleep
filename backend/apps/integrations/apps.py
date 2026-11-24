from django.apps import AppConfig
from django.conf import settings
from django.core import checks


class IntegrationsConfig(AppConfig):
    name = "apps.integrations"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self):
        from . import deliveries, registry  # noqa: F401  (starts listening)

        # A plugin that can't load stops the server now, not when someone needs it.
        registry.plugins()


@checks.register
def plugin_options(app_configs, **kwargs):
    """Says so instead of leaving a plugin silently off: options half set, or misspelled."""
    from . import registry

    warnings = []
    known = {plugin.option_key(name) for plugin in registry.plugins().values() for name in plugin.server_options}
    for key in sorted(set(settings.PLUGIN_OPTIONS) - known):
        warnings.append(checks.Warning(f"{key} isn't an option of any plugin here.", id="integrations.W001"))
    for plugin in registry.plugins().values():
        missing = plugin.missing_options
        if missing and len(missing) < len(plugin.server_options):
            warnings.append(
                checks.Warning(
                    f"{plugin.name} is off until these are set: {', '.join(missing)}.", id="integrations.W002"
                )
            )
    return warnings
