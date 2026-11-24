"""Dashboard APIs for a workspace's integrations, and the address services send webhooks to.

Members see what is connected; owners connect and change it. Nothing here waits for a service: what
needs one is a job (apps.integrations.jobs).
"""

import json
from datetime import datetime

from django.core import signing
from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts.security import token_auth
from apps.workspaces.services import member_workspace, owner_workspace
from whileisleep import encryption

from . import connections, deliveries, jobs, registry, tasks
from .models import Delivery, Integration
from .plugin import BadRequest, Field, Plugin, PluginError, WebhookRequest

router = Router(tags=["integrations"])

# How long an owner has to allow the connection at the service.
STATE_SECONDS = 900
STATE_SALT = "integrations.authorize"
# How long a webhook's job is remembered, so a repeat does nothing. Services give up sooner.
SEEN_SECONDS = 6 * 3600
LOG_ROWS = 30


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


class ShownOut(Schema):
    label: str
    value: str
    secret: bool
    help: str


class ConnectionOut(Schema):
    id: int
    account_name: str
    settings: dict[str, str]
    # Which secrets are saved. Their values never come back.
    secrets: list[str]
    # Everything required was chosen.
    ready: bool
    last_error: str


class ConnectionDetail(ConnectionOut):
    shown: list[ShownOut]


class IntegrationBase(Schema):
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
    # A workspace may have several.
    many: bool


class IntegrationOut(IntegrationBase):
    connections: list[ConnectionOut]


class IntegrationDetail(IntegrationBase):
    connect_fields: list[FieldOut]
    settings_fields: list[FieldOut]
    save_label: str
    keeps_log: bool
    connections: list[ConnectionDetail]


class ValuesIn(Schema):
    values: dict[str, str] = {}


class JobOut(Schema):
    job: str = ""


class ConnectOut(JobOut):
    # Where to send the browser, instead of a job.
    url: str = ""


class CallbackIn(Schema):
    code: str
    state: str


class JobResult(Schema):
    done: bool
    error: str = ""
    result: dict = {}


class DeliveryOut(Schema):
    id: int
    event: str
    status: str
    attempts: int
    detail: str
    created_at: datetime
    conversation_id: int


def get_plugin(plugin_id: str) -> Plugin:
    plugin = registry.get(plugin_id)
    if plugin is None:
        raise HttpError(404, "There is no such integration.")
    return plugin


def get_connection(request, workspace_id: int, plugin: Plugin, connection_id: int) -> Integration:
    workspace = owner_workspace(request.auth, workspace_id)
    return get_object_or_404(Integration, pk=connection_id, workspace=workspace, plugin=plugin.id)


def has_page(plugin: Plugin) -> bool:
    return type(plugin).authorize_url is not Plugin.authorize_url


def field_out(field: Field) -> dict:
    return {
        "name": field.name,
        "label": field.label,
        "kind": field.kind,
        "help": field.help,
        "placeholder": field.placeholder,
        "options": [{"value": o.value, "label": o.label} for o in field.options],
        "default": field.default,
        "required": field.required,
    }


def connection_out(plugin: Plugin, integration: Integration) -> dict:
    fields = plugin.settings_fields
    secrets = [f.name for f in fields if f.kind == "secret" and integration.credentials.get(f.name)]
    values = {f.name: str(integration.config.get(f.name, f.default)) for f in fields if f.kind != "secret"}
    chosen = all(integration.config.get(f.name) or f.name in secrets for f in fields if f.required)
    return {
        "id": integration.pk,
        "account_name": integration.account_name,
        "settings": values,
        "secrets": secrets,
        "ready": chosen,
        "last_error": integration.last_error,
    }


def integration_out(plugin: Plugin, rows: list[Integration]) -> dict:
    return {
        "plugin": plugin.id,
        "name": plugin.name,
        "description": plugin.description,
        "notice": plugin.notice,
        "icon": plugin.icon,
        "available": plugin.available,
        "missing_options": plugin.missing_options,
        "has_page": has_page(plugin),
        "many": plugin.many,
        "connections": [connection_out(plugin, row) for row in rows],
    }


def detail_out(plugin: Plugin, rows: list[Integration]) -> dict:
    out = integration_out(plugin, rows)
    for row, connection in zip(rows, out["connections"], strict=True):
        connection["shown"] = [
            {"label": s.label, "value": s.value, "secret": s.secret, "help": s.help} for s in plugin.shown(row)
        ]
    return out | {
        "connect_fields": [field_out(f) for f in plugin.connect_fields],
        "settings_fields": [field_out(f) for f in plugin.settings_fields],
        "save_label": plugin.save_label,
        "keeps_log": plugin.keeps_log,
    }


# --- The dashboard ---


@router.get("/workspaces/{workspace_id}/integrations", response=list[IntegrationOut], auth=token_auth)
def list_integrations(request, workspace_id: int):
    workspace = member_workspace(request.auth, workspace_id)
    rows: dict[str, list[Integration]] = {}
    for row in workspace.integrations.order_by("pk"):
        rows.setdefault(row.plugin, []).append(row)
    return [integration_out(plugin, rows.get(plugin.id, [])) for plugin in registry.plugins().values()]


@router.get("/workspaces/{workspace_id}/integrations/{plugin_id}", response=IntegrationDetail, auth=token_auth)
def get(request, workspace_id: int, plugin_id: str):
    workspace = owner_workspace(request.auth, workspace_id)
    plugin = get_plugin(plugin_id)
    return detail_out(plugin, list(workspace.integrations.filter(plugin=plugin.id).order_by("pk")))


@router.post("/workspaces/{workspace_id}/integrations/{plugin_id}/connect", response=ConnectOut, auth=token_auth)
def connect(request, workspace_id: int, plugin_id: str, payload: ValuesIn):
    workspace = owner_workspace(request.auth, workspace_id)
    plugin = get_plugin(plugin_id)
    if not plugin.available:
        raise HttpError(409, f"{plugin.name} isn't set up on this server yet.")
    try:
        connections.check_room(workspace, plugin)
        values = connections.clean(plugin.connect_fields, payload.values)
    except PluginError as error:
        raise HttpError(400, str(error)) from error
    if has_page(plugin):
        state = {"workspace": workspace.pk, "user": request.auth.pk, "plugin": plugin.id}
        sealed = signing.dumps(state, salt=STATE_SALT)
        return {"url": plugin.authorize_url(sealed, connections.redirect_uri())}
    return jobs.start(request.auth, "connect", plugin.id, workspace, values=values)


@router.post("/integrations/callback", response=JobOut, auth=token_auth)
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
    return jobs.start(request.auth, "authorize", plugin.id, workspace, code=payload.code)


@router.get("/integrations/jobs/{job_id}", response=JobResult, auth=token_auth)
def job(request, job_id: str):
    """How a job went, for the person who started it."""
    found = jobs.result(request.auth, job_id)
    if found is None:
        raise HttpError(404, "That took too long. Try again.")
    return found


ONE = "/workspaces/{workspace_id}/integrations/{plugin_id}/{connection_id}"


@router.post(f"{ONE}/options", response=JobOut, auth=token_auth)
def options(request, workspace_id: int, plugin_id: str, connection_id: int):
    """What every "select" offers, as the job's result: {"options": {name: [...]}}."""
    plugin = get_plugin(plugin_id)
    integration = get_connection(request, workspace_id, plugin, connection_id)
    return jobs.start(request.auth, "options", plugin.id, integration.workspace, connection=integration.pk)


@router.put(ONE, response=JobOut, auth=token_auth)
def save(request, workspace_id: int, plugin_id: str, connection_id: int, payload: ValuesIn):
    plugin = get_plugin(plugin_id)
    integration = get_connection(request, workspace_id, plugin, connection_id)
    return jobs.start(
        request.auth, "save", plugin.id, integration.workspace, connection=integration.pk, values=payload.values
    )


@router.delete(ONE, auth=token_auth)
def disconnect(request, workspace_id: int, plugin_id: str, connection_id: int):
    """Disconnected here at once; a worker tells the service."""
    plugin = get_plugin(plugin_id)
    integration = get_connection(request, workspace_id, plugin, connection_id)
    row = {"account_id": integration.account_id, "credentials": integration.credentials}
    integration.delete()
    tasks.say_goodbye.delay(plugin.id, encryption.encrypt(json.dumps(row)))
    return {"ok": True}


@router.get(f"{ONE}/deliveries", response=list[DeliveryOut], auth=token_auth)
def list_deliveries(request, workspace_id: int, plugin_id: str, connection_id: int):
    """The newest first: what was sent, is waiting, or was given up on."""
    integration = get_connection(request, workspace_id, get_plugin(plugin_id), connection_id)
    return integration.deliveries.order_by("-id")[:LOG_ROWS]


@router.post(f"{ONE}/deliveries/{{delivery_id}}/again", response=DeliveryOut, auth=token_auth)
def send_again(request, workspace_id: int, plugin_id: str, connection_id: int, delivery_id: int):
    integration = get_connection(request, workspace_id, get_plugin(plugin_id), connection_id)
    delivery = get_object_or_404(Delivery, pk=delivery_id, integration=integration)
    if delivery.status == Delivery.Status.PENDING:
        raise HttpError(409, "It is on its way already.")
    delivery.status, delivery.attempts, delivery.due_at = Delivery.Status.PENDING, 0, timezone.now()
    delivery.save(update_fields=["status", "attempts", "due_at"])
    deliveries.send_later(integration.pk, delivery.conversation_id)
    # It may have been sent already, and not kept.
    return Delivery.objects.filter(pk=delivery.pk).first() or delivery


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
    for work in received.jobs:
        key = f"integration-job:{plugin.id}:{work.id}"
        if not cache.add(key, 1, SEEN_SECONDS):
            continue
        try:
            tasks.handle.delay(plugin.id, work.payload)
        except Exception:
            # Not queued: let the service send it again.
            cache.delete(key)
            raise
    return JsonResponse(received.body)
