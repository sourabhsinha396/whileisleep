"""Dashboard APIs for a workspace's AI tools (data connectors)."""

from datetime import datetime
from typing import Any

from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from apps.accounts.security import token_auth
from apps.conversations import attributes
from apps.conversations.models import Visitor
from apps.workspaces.services import member_workspace, owner_workspace

from . import http_tools, mcp_tools
from .bot import BUILTIN_TOOLS, PLAYBOOK_TOOL
from .models import Tool, tool_name

router = Router(tags=["tools"], auth=token_auth)
TOOL_FIELDS = (
    "id",
    "name",
    "description",
    "method",
    "url",
    "input_schema",
    "allow_unverified_identity",
    "enabled",
)
RESERVED = {t["name"] for t in BUILTIN_TOOLS} | {PLAYBOOK_TOOL}


class ToolIn(Schema):
    name: str = Field(max_length=64)
    description: str = Field(min_length=10)
    method: str = "GET"
    url: str = Field(min_length=8, max_length=1000)
    input_schema: dict[str, Any] = {"type": "object", "properties": {}}
    headers: dict[str, str] = {}
    allow_unverified_identity: bool = False
    enabled: bool = True


class ToolOut(Schema):
    id: int
    name: str
    description: str
    method: str
    url: str
    input_schema: dict[str, Any]
    # Names only: header values are secrets.
    header_names: list[str]
    allow_unverified_identity: bool
    enabled: bool
    created_at: datetime
    # Set for tools that come from an MCP server; those are switched on with /approve.
    mcp_server_id: int | None = None
    read_only: bool = False
    # The server changed this tool since it was approved (or it never was): not offered to
    # the AI until an owner approves it again.
    needs_review: bool = False


class ToolApproveIn(Schema):
    enabled: bool


class ToolTestIn(Schema):
    inputs: dict[str, Any] = {}


class ToolTestOut(Schema):
    result: str
    is_error: bool


def tool_out(tool: Tool) -> dict:
    return {
        **{field: getattr(tool, field) for field in TOOL_FIELDS},
        "header_names": sorted(tool.headers or {}),
        "created_at": tool.created_at,
        "mcp_server_id": tool.mcp_server_id,
        "read_only": tool.read_only,
        "needs_review": tool.needs_review,
    }


def check(payload: ToolIn) -> None:
    try:
        tool_name(payload.name)
    except ValidationError as error:
        raise HttpError(400, f"Tool name: {error.messages[0]}") from error
    if payload.name in RESERVED:
        raise HttpError(400, f"{payload.name} is a built-in tool name.")
    if payload.method not in Tool.Method.values:
        raise HttpError(400, "Method must be GET or POST.")
    if not payload.url.startswith(("http://", "https://")):
        raise HttpError(400, "URL must start with http:// or https://.")
    if "__" in payload.name:
        # Reserved for tools imported from MCP servers ("stripe__refund").
        raise HttpError(400, "Tool names can't contain a double underscore.")
    if payload.input_schema.get("type", "object") != "object":
        raise HttpError(400, 'Input schema must be a JSON Schema with "type": "object".')


@router.get("/workspaces/{workspace_id}/tools", response=list[ToolOut])
def list_tools(request, workspace_id: int):
    return [tool_out(t) for t in member_workspace(request.auth, workspace_id).tools.all()]


@router.post("/workspaces/{workspace_id}/tools", response=ToolOut)
def create(request, workspace_id: int, payload: ToolIn):
    workspace = owner_workspace(request.auth, workspace_id)
    check(payload)
    if workspace.tools.filter(name=payload.name).exists():
        raise HttpError(400, "A tool with this name already exists.")
    return tool_out(Tool.objects.create(workspace=workspace, **payload.dict()))


@router.put("/workspaces/{workspace_id}/tools/{tool_id}", response=ToolOut)
def update(request, workspace_id: int, tool_id: int, payload: ToolIn):
    """Replaces the tool. An empty `headers` keeps the saved ones, since the dashboard never sees them."""
    tool = get_object_or_404(Tool, pk=tool_id, workspace=owner_workspace(request.auth, workspace_id))
    if tool.mcp_server_id:
        raise HttpError(400, "This tool comes from an MCP server, which defines it. Switch it on or off instead.")
    check(payload)
    if Tool.objects.filter(workspace=tool.workspace, name=payload.name).exclude(pk=tool.pk).exists():
        raise HttpError(400, "A tool with this name already exists.")
    data = payload.dict()
    if not data["headers"]:
        data.pop("headers")
    for field, value in data.items():
        setattr(tool, field, value)
    tool.save()
    return tool_out(tool)


@router.delete("/workspaces/{workspace_id}/tools/{tool_id}")
def delete(request, workspace_id: int, tool_id: int):
    get_object_or_404(Tool, pk=tool_id, workspace=owner_workspace(request.auth, workspace_id)).delete()
    return {"ok": True}


@router.post("/workspaces/{workspace_id}/tools/{tool_id}/approve", response=ToolOut)
def approve(request, workspace_id: int, tool_id: int, payload: ToolApproveIn):
    """Switches an MCP tool on or off. Switching it on approves its definition as it is now."""
    tool = get_object_or_404(Tool, pk=tool_id, workspace=owner_workspace(request.auth, workspace_id))
    if not tool.mcp_server_id:
        raise HttpError(400, "Only tools from an MCP server are approved this way.")
    return tool_out(mcp_tools.approve(tool, payload.enabled))


@router.post("/workspaces/{workspace_id}/tools/{tool_id}/test", response=ToolTestOut)
def test(request, workspace_id: int, tool_id: int, payload: ToolTestIn):
    """Calls the tool as the bot would, with a stand-in visitor, so owners can check it."""
    tool = get_object_or_404(Tool, pk=tool_id, workspace=owner_workspace(request.auth, workspace_id))
    if tool.mcp_server_id:
        result, is_error = mcp_tools.run(tool, payload.inputs)
        return {"result": result, "is_error": is_error}
    stand_in = Visitor(
        pk=0,
        workspace=tool.workspace,
        external_id="test-user",
        # Verified, so tools that need a proven identity can be tried.
        attributes={
            "name": {"value": "Test visitor", "source": attributes.Source.VERIFIED},
            "email": {"value": request.auth.email, "source": attributes.Source.VERIFIED},
        },
    )
    result, is_error = http_tools.run(tool, payload.inputs, stand_in)
    return {"result": result, "is_error": is_error}
