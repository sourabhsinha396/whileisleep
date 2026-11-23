"""Dashboard APIs for a workspace's MCP servers. Members read; owners change them.

The tools a server provides appear in the ordinary tools list (apps.agent.apis), where
owners switch each one on.
"""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from apps.accounts.security import token_auth
from apps.workspaces.services import member_workspace, owner_workspace

from . import mcp, mcp_tools
from .models import McpServer, server_name

router = Router(tags=["mcp"], auth=token_auth)


class McpServerIn(Schema):
    name: str = Field(max_length=24)
    url: str = Field(min_length=8, max_length=1000)
    # Sent with every request, e.g. {"Authorization": "Bearer ..."}. Write-only.
    headers: dict[str, str] = {}
    enabled: bool = True


class McpServerOut(Schema):
    id: int
    name: str
    url: str
    # Names only: header values are secrets.
    header_names: list[str]
    enabled: bool
    tool_count: int
    # Tools switched on and approved as the server defines them now.
    active_tool_count: int
    last_synced_at: datetime | None
    # Why the last sync failed; empty when it worked.
    last_error: str


class SyncOut(Schema):
    server: McpServerOut
    added: int = 0
    changed: int = 0
    removed: int = 0


def server_out(server: McpServer) -> dict:
    tools = list(server.tools.all())
    return {
        "id": server.id,
        "name": server.name,
        "url": server.url,
        "header_names": sorted(server.headers or {}),
        "enabled": server.enabled,
        "tool_count": len(tools),
        "active_tool_count": sum(1 for tool in tools if tool.enabled and not tool.needs_review),
        "last_synced_at": server.last_synced_at,
        "last_error": server.last_error,
    }


def check(payload: McpServerIn) -> None:
    try:
        server_name(payload.name)
    except ValidationError as error:
        raise HttpError(400, f"Name: {error.messages[0]}") from error
    if not payload.url.startswith(("http://", "https://")):
        raise HttpError(400, "URL must start with http:// or https://.")


def sync_out(server: McpServer) -> dict:
    """Syncs and reports. A server that can't be reached is still saved, with the reason,
    so the owner can fix the URL or token and try again."""
    try:
        counts = mcp_tools.sync(server)
    except mcp.McpError:
        counts = {}
    server.refresh_from_db()
    return {"server": server_out(server), **counts}


@router.get("/workspaces/{workspace_id}/mcp-servers", response=list[McpServerOut])
def list_servers(request, workspace_id: int):
    workspace = member_workspace(request.auth, workspace_id)
    return [server_out(server) for server in workspace.mcp_servers.prefetch_related("tools")]


@router.post("/workspaces/{workspace_id}/mcp-servers", response=SyncOut)
def create(request, workspace_id: int, payload: McpServerIn):
    """Connects a server and imports its tools, all switched off."""
    workspace = owner_workspace(request.auth, workspace_id)
    check(payload)
    if workspace.mcp_servers.filter(name=payload.name).exists():
        raise HttpError(400, "A server with this name already exists.")
    return sync_out(McpServer.objects.create(workspace=workspace, **payload.dict()))


@router.put("/workspaces/{workspace_id}/mcp-servers/{server_id}", response=SyncOut)
def update(request, workspace_id: int, server_id: int, payload: McpServerIn):
    """Replaces the server's settings and syncs. An empty `headers` keeps the saved ones."""
    server = get_object_or_404(McpServer, pk=server_id, workspace=owner_workspace(request.auth, workspace_id))
    check(payload)
    if payload.name != server.name:
        # Tool names start with the server's name; renaming would silently rename them all.
        raise HttpError(400, "A server can't be renamed. Remove it and add it again.")
    data = payload.dict()
    if not data["headers"]:
        data.pop("headers")
    if data["url"] != server.url:
        # A different address may be a different kind of server.
        server.era = ""
    for field, value in data.items():
        setattr(server, field, value)
    server.save()
    return sync_out(server)


@router.post("/workspaces/{workspace_id}/mcp-servers/{server_id}/sync", response=SyncOut)
def sync(request, workspace_id: int, server_id: int):
    """Fetches the server's tool list again."""
    server = get_object_or_404(McpServer, pk=server_id, workspace=owner_workspace(request.auth, workspace_id))
    return sync_out(server)


@router.delete("/workspaces/{workspace_id}/mcp-servers/{server_id}")
def delete(request, workspace_id: int, server_id: int):
    """Removes the server and the tools it provided."""
    get_object_or_404(McpServer, pk=server_id, workspace=owner_workspace(request.auth, workspace_id)).delete()
    return {"ok": True}
