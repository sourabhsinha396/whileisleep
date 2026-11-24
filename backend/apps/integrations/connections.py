"""A workspace's connection to a service: making it, and what the owner chooses for it."""

from django.conf import settings
from django.db import transaction

from apps.workspaces.models import Workspace

from .models import Integration
from .plugin import Connection, Field, Plugin, PluginError

MAX_VALUE_CHARS = 2000
# How many connections of one plugin a workspace may have, where it may have several.
MAX_CONNECTIONS = 5


def redirect_uri() -> str:
    """The dashboard's page the service sends the owner back to (frontend/src/app/integrations)."""
    return f"{settings.SITE_URL}/integrations/callback"


def check_room(workspace: Workspace, plugin: Plugin) -> None:
    if plugin.many and Integration.objects.filter(workspace=workspace, plugin=plugin.id).count() >= MAX_CONNECTIONS:
        raise PluginError(f"You can have {MAX_CONNECTIONS} of these. Remove one first.")


def clean(fields: tuple[Field, ...], values: dict[str, str], options=None, saved=()) -> dict[str, str]:
    """The values of these fields, checked. `options` finds what a "select" offers; `saved` are the
    secrets there are already, which an empty value keeps."""
    result = {}
    for field in fields:
        value = str(values.get(field.name, field.default)).strip()[:MAX_VALUE_CHARS]
        if not value and field.required and not (field.kind == "secret" and field.name in saved):
            raise PluginError(f"{field.label}: this is needed.")
        if value and field.kind in ("choice", "choices", "select"):
            allowed = {o.value for o in (options(field.name) if field.kind == "select" else field.options)}
            if not set(value.split(",") if field.kind == "choices" else [value]) <= allowed:
                raise PluginError(f"{field.label}: pick from the list.")
        result[field.name] = value
    return result


def save(workspace: Workspace, plugin: Plugin, connection: Connection, user) -> Integration:
    fields = {
        "account_name": connection.account_name,
        "credentials": connection.credentials,
        "connected_by": user,
        "last_error": "",
    }
    with transaction.atomic():
        # One owner's two clicks can't make two.
        Workspace.objects.select_for_update().get(pk=workspace.pk)
        check_room(workspace, plugin)
        if not plugin.many:
            # Another account: nothing chosen or linked in the old one means anything there.
            mine = Integration.objects.filter(workspace=workspace, plugin=plugin.id)
            mine.exclude(account_id=connection.account_id).delete()
        integration, _ = Integration.objects.update_or_create(
            workspace=workspace, plugin=plugin.id, account_id=connection.account_id, defaults=fields
        )
    return integration


def options_of(plugin: Plugin, integration: Integration, name: str) -> list[dict]:
    return [{"value": o.value, "label": o.label} for o in plugin.options(integration, name)]


def save_settings(plugin: Plugin, integration: Integration, values: dict[str, str]) -> None:
    """Secrets go with the credentials, and are only replaced by a new value."""
    fields = plugin.settings_fields
    values = clean(
        fields, values, lambda name: plugin.options(integration, name), saved=set(integration.credentials or {})
    )
    secrets = {f.name: values.pop(f.name) for f in fields if f.kind == "secret"}
    integration.config = values
    integration.credentials = integration.credentials | {name: value for name, value in secrets.items() if value}
    integration.last_error = ""
    plugin.check_settings(integration)
    integration.save(update_fields=["config", "credentials", "account_name", "last_error"])
