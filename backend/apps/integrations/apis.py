"""Dashboard APIs for a workspace's integrations, and the address services send webhooks to.
Members read; owners connect and change them."""

import logging

from django.conf import settings
from django.core import signing
from django.core.cache import cache
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts.security import token_auth
from apps.workspaces.models import Workspace
from apps.workspaces.services import member_workspace, owner_workspace

from . import registry, tasks
from .models import Integration
from .plugin import BadRequest, Connection, Field, Plugin, PluginError, WebhookRequest

log = logging.getLogger(__name__)
router = Router(tags=["integrations"])

# How long an owner has to allow the connection at the service.
STATE_SECONDS = 900
STATE_SALT = "integrations.authorize"
# How long a webhook's job is remembered, so a repeat does nothing. Services give up sooner.
SEEN_SECONDS = 6 * 3600
MAX_VALUE_CHARS = 2000


class OptionOut(Schema):
    value: str
    label: str


class FieldOut(Schema):
    name: str
    label: str
    kind: str
    help: str
    placeholder: str
    options: list[OptionOut]
    default: str
    required: bool


class IntegrationOut(Schema):
    plugin: str
    name: str
    description: str
    notice: str
    icon: str
    # Whether this server has what the plugin needs, and what it lacks.
    available: bool
    missing_options: list[str]
    # Connecting opens the service's own page; without one, the owner fills in connect_fields.
    has_page: bool
    connect_fields: list[FieldOut]
    connected: bool = False
    account_name: str = ""
    settings: dict[str, str] = {}
    # Everything required was chosen.
    ready: bool = False
    last_error: str = ""


class IntegrationDetail(IntegrationOut):
    settings_fields: list[FieldOut]
    save_label: str
    # Why the choices couldn't be loaded from the service.
    options_error: str = ""


class ValuesIn(Schema):
    values: dict[str, str] = {}


class ConnectOut(Schema):
    # Where to send the browser. Empty when it is connected already.
    url: str = ""


class CallbackIn(Schema):
    code: str
    state: str


class CallbackOut(Schema):
    workspace: str
    plugin: str


def get_plugin(plugin_id: str) -> Plugin:
    plugin = registry.get(plugin_id)
    if plugin is None:
        raise HttpError(404, "There is no such integration.")
    return plugin


def get_integration(workspace: Workspace, plugin: Plugin) -> Integration:
    return get_object_or_404(Integration, workspace=workspace, plugin=plugin.id)


def field_out(field: Field, options=None) -> dict:
    return {
        "name": field.name,
        "label": field.label,
        "kind": field.kind,
        "help": field.help,
        "placeholder": field.placeholder,
        "options": [{"value": o.value, "label": o.label} for o in (field.options if options is None else options)],
        "default": field.default,
        "required": field.required,
    }


def chosen(plugin: Plugin, integration: Integration) -> dict:
    return {f.name: str(integration.config.get(f.name, f.default)) for f in plugin.settings_fields}


def integration_out(plugin: Plugin, integration: Integration | None) -> dict:
    out = {
        "plugin": plugin.id,
        "name": plugin.name,
        "description": plugin.description,
        "notice": plugin.notice,
        "icon": plugin.icon,
        "available": plugin.available,
        "missing_options": plugin.missing_options,
        "has_page": has_page(plugin),
        "connect_fields": [field_out(f) for f in plugin.connect_fields],
    }
    if integration is None:
        return out
    values = chosen(plugin, integration)
    return out | {
        "connected": True,
        "account_name": integration.account_name,
        "settings": values,
        "ready": all(values[f.name] for f in plugin.settings_fields if f.required),
        "last_error": integration.last_error,
    }


def detail_out(plugin: Plugin, integration: Integration | None) -> dict:
    out = integration_out(plugin, integration) | {"settings_fields": [], "save_label": plugin.save_label}
    if integration is None:
        return out
    for field in plugin.settings_fields:
        options = None
        if field.kind == "select":
            try:
                options = plugin.options(integration, field.name)
            except PluginError as error:
                options, out["options_error"] = [], str(error)
        out["settings_fields"].append(field_out(field, options))
    return out


def has_page(plugin: Plugin) -> bool:
    return type(plugin).authorize_url is not Plugin.authorize_url


def clean(fields: tuple[Field, ...], values: dict[str, str], options=None) -> dict[str, str]:
    """The values of these fields, checked. `options` finds what a "select" offers."""
    result = {}
    for field in fields:
        value = str(values.get(field.name, field.default)).strip()[:MAX_VALUE_CHARS]
        if not value and field.required:
            raise HttpError(400, f"{field.label}: this is needed.")
        if value and field.kind in ("choice", "select"):
            allowed = field.options if field.kind == "choice" else options(field.name)
            if value not in {o.value for o in allowed}:
                raise HttpError(400, f"{field.label}: pick one from the list.")
        result[field.name] = value
    return result


def save_connection(workspace: Workspace, plugin: Plugin, connection: Connection, user) -> Integration:
    with transaction.atomic():
        current = Integration.objects.select_for_update().filter(workspace=workspace, plugin=plugin.id).first()
        if current and current.account_id != connection.account_id:
            # Another account: nothing chosen or linked in the old one means anything there.
            current.delete()
        integration, _ = Integration.objects.update_or_create(
            workspace=workspace,
            plugin=plugin.id,
            defaults={
                "account_id": connection.account_id,
                "account_name": connection.account_name,
                "credentials": connection.credentials,
                "connected_by": user,
                "last_error": "",
            },
        )
    return integration


def redirect_uri() -> str:
    """The dashboard's page the service sends the owner back to (frontend/src/app/integrations)."""
    return f"{settings.SITE_URL}/integrations/callback"


# --- The dashboard ---


@router.get("/workspaces/{workspace_id}/integrations", response=list[IntegrationOut], auth=token_auth)
def list_integrations(request, workspace_id: int):
    workspace = member_workspace(request.auth, workspace_id)
    connected = {i.plugin: i for i in workspace.integrations.all()}
    return [integration_out(plugin, connected.get(plugin.id)) for plugin in registry.plugins().values()]


@router.get("/workspaces/{workspace_id}/integrations/{plugin_id}", response=IntegrationDetail, auth=token_auth)
def get(request, workspace_id: int, plugin_id: str):
    workspace = owner_workspace(request.auth, workspace_id)
    plugin = get_plugin(plugin_id)
    return detail_out(plugin, workspace.integrations.filter(plugin=plugin.id).first())


@router.post("/workspaces/{workspace_id}/integrations/{plugin_id}/connect", response=ConnectOut, auth=token_auth)
def connect(request, workspace_id: int, plugin_id: str, payload: ValuesIn):
    workspace = owner_workspace(request.auth, workspace_id)
    plugin = get_plugin(plugin_id)
    if not plugin.available:
        raise HttpError(409, f"{plugin.name} isn't set up on this server yet.")
    if has_page(plugin):
        state = {"workspace": workspace.pk, "user": request.auth.pk, "plugin": plugin.id}
        return {"url": plugin.authorize_url(signing.dumps(state, salt=STATE_SALT), redirect_uri())}
    try:
        connection = plugin.connect(clean(plugin.connect_fields, payload.values))
    except PluginError as error:
        raise HttpError(400, str(error)) from error
    save_connection(workspace, plugin, connection, request.auth)
    return {"url": ""}


@router.post("/integrations/callback", response=CallbackOut, auth=token_auth)
def callback(request, payload: CallbackIn):
    """Back from the service. Only the person who started may finish: otherwise a link could make
    someone else's account serve the workspace of whoever sent it."""
    try:
        state = signing.loads(payload.state, salt=STATE_SALT, max_age=STATE_SECONDS)
    except signing.BadSignature:
        raise HttpError(400, "That took too long, or the link isn't valid. Connect again.") from None
    if state["user"] != request.auth.pk:
        raise HttpError(403, "Someone else started this. Connect again from your own dashboard.")
    workspace = owner_workspace(request.auth, state["workspace"])
    plugin = get_plugin(state["plugin"])
    try:
        connection = plugin.finish_authorization(payload.code, redirect_uri())
    except PluginError as error:
        raise HttpError(400, str(error)) from error
    save_connection(workspace, plugin, connection, request.auth)
    return {"workspace": workspace.slug, "plugin": plugin.id}


@router.put("/workspaces/{workspace_id}/integrations/{plugin_id}", response=IntegrationDetail, auth=token_auth)
def save(request, workspace_id: int, plugin_id: str, payload: ValuesIn):
    workspace = owner_workspace(request.auth, workspace_id)
    plugin = get_plugin(plugin_id)
    integration = get_integration(workspace, plugin)
    try:
        values = clean(plugin.settings_fields, payload.values, lambda name: plugin.options(integration, name))
        plugin.check_settings(integration, values)
    except PluginError as error:
        raise HttpError(400, str(error)) from error
    integration.config = values
    integration.last_error = ""
    integration.save(update_fields=["config", "last_error"])
    return detail_out(plugin, integration)


@router.delete("/workspaces/{workspace_id}/integrations/{plugin_id}", auth=token_auth)
def disconnect(request, workspace_id: int, plugin_id: str):
    workspace = owner_workspace(request.auth, workspace_id)
    plugin = get_plugin(plugin_id)
    integration = get_integration(workspace, plugin)
    try:
        plugin.disconnect(integration)
    except Exception as error:
        # Whatever the other end says, it is disconnected here.
        log.warning("Disconnecting %s: %s", integration, error)
    integration.delete()
    return {"ok": True}


# --- What services send ---


@router.post("/integrations/{plugin_id}/webhook", auth=None, include_in_schema=False)
def webhook(request, plugin_id: str):
    plugin = get_plugin(plugin_id)
    if not plugin.available:
        raise HttpError(404, "Not found.")
    try:
        received = plugin.receive(WebhookRequest(headers=request.headers, body=request.body))
    except BadRequest as error:
        raise HttpError(error.status, str(error)) from error
    for job in received.jobs:
        key = f"integration-job:{plugin.id}:{job.id}"
        if not cache.add(key, 1, SEEN_SECONDS):
            continue
        try:
            tasks.handle.delay(plugin.id, job.payload)
        except Exception:
            # Not queued: let the service send it again.
            cache.delete(key)
            raise
    return JsonResponse(received.body)
