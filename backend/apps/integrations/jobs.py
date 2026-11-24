"""What the dashboard asks of a service: connecting, listing choices, saving.

A web request must not wait for a service, so it starts a job, answers with its id, and the browser
asks how it went (GET /integrations/jobs/<id>). What a job needs may be secret (a typed key, an OAuth
code), so it is encrypted on its way through the queue.
"""

import json
import logging
import secrets

from django.contrib.auth import get_user_model
from django.core.cache import cache

from apps.workspaces.models import Workspace
from whileisleep import encryption

from . import connections, registry
from .models import Integration
from .plugin import PluginError

log = logging.getLogger(__name__)

RESULT_SECONDS = 600


def key(job_id: str) -> str:
    return f"integration-request:{job_id}"


def start(user, kind: str, plugin_id: str, workspace: Workspace, **args) -> dict:
    from . import tasks

    job_id = secrets.token_urlsafe(16)
    cache.set(key(job_id), {"user": user.pk, "done": False}, RESULT_SECONDS)
    payload = {"kind": kind, "plugin": plugin_id, "workspace": workspace.pk, "user": user.pk, "args": args}
    tasks.run_job.delay(job_id, encryption.encrypt(json.dumps(payload)))
    return {"job": job_id}


def result(user, job_id: str) -> dict | None:
    """How a job of this user's went. None: there is no such job (anymore)."""
    found = cache.get(key(job_id))
    return found if found and found["user"] == user.pk else None


def run(job_id: str, sealed: str) -> None:
    payload = json.loads(encryption.decrypt(sealed) or "null")
    if payload is None:
        return
    outcome = {"user": payload["user"], "done": True}
    try:
        outcome["result"] = do(payload)
    except PluginError as error:
        outcome["error"] = str(error)
    except Exception:
        log.exception("Job %s of plugin %s failed", payload["kind"], payload["plugin"])
        outcome["error"] = "Something went wrong. Try again."
    cache.set(key(job_id), outcome, RESULT_SECONDS)


def do(payload: dict) -> dict:
    plugin = registry.get(payload["plugin"])
    workspace = Workspace.objects.filter(pk=payload["workspace"]).first()
    user = get_user_model().objects.filter(pk=payload["user"]).first()
    if plugin is None or workspace is None or user is None:
        raise PluginError("It is no longer there.")
    args, integration = payload["args"], None
    match payload["kind"]:
        case "connect":
            integration = connections.save(workspace, plugin, plugin.connect(args["values"]), user)
        case "authorize":
            connection = plugin.finish_authorization(args["code"], connections.redirect_uri())
            integration = connections.save(workspace, plugin, connection, user)
        case "options":
            integration = find(workspace, plugin, args["connection"])
            names = [field.name for field in plugin.settings_fields if field.kind == "select"]
            return {"options": {name: connections.options_of(plugin, integration, name) for name in names}}
        case "save":
            integration = find(workspace, plugin, args["connection"])
            connections.save_settings(plugin, integration, args["values"])
    return {"workspace": workspace.slug, "plugin": plugin.id, "connection": integration.pk}


def find(workspace: Workspace, plugin, connection_id: int) -> Integration:
    integration = Integration.objects.filter(workspace=workspace, plugin=plugin.id, pk=connection_id).first()
    if integration is None:
        raise PluginError("It was disconnected meanwhile.")
    return integration
