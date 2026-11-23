"""MCP servers as a source of tools for the AI.

A workspace connects a server (its URL and a token); `sync` copies the server's tool list
into Tool rows, next to the workspace's HTTP tools. Three rules keep that safe:

- **Nothing is on by default.** Imported tools start disabled. The owner switches on the
  ones the AI may call; a server with fifty tools doesn't put fifty in the prompt.
- **Approval is for a definition, not a name.** A tool's description is text the model
  reads, written by someone else. Switching a tool on records a hash of its definition;
  if the server later changes the description or schema, the tool stops being offered
  until the owner looks again. (A tool that turns hostile after approval is the known
  attack on MCP clients.)
- **The server is told nothing about the visitor.** Only the arguments the model chose
  are sent.
"""

import hashlib
import json
import re

from django.db import transaction
from django.utils import timezone

from . import http_tools, mcp
from .models import McpServer, Tool

MAX_NAME = 64


def definition_hash(tool: mcp.RemoteTool) -> str:
    """Identifies everything about a remote tool that the model would read."""
    definition = {"name": tool.name, "description": tool.description, "input_schema": tool.input_schema}
    return hashlib.sha256(json.dumps(definition, sort_keys=True).encode()).hexdigest()


def local_name(server: McpServer, remote_name: str) -> str:
    """The tool's name in this workspace: the server's name in front, so two servers (or a
    server and an HTTP tool) can both have a "search"."""
    cleaned = re.sub(r"[^a-z0-9_]+", "_", remote_name.lower()).strip("_") or "tool"
    return f"{server.name}__{cleaned}"[:MAX_NAME]


def client_for(server: McpServer) -> mcp.Client:
    return mcp.Client(server.url, dict(server.headers or {}), era=server.era or None)


def remember_era(server: McpServer, client: mcp.Client) -> None:
    if client.era and client.era != server.era:
        server.era = client.era
        server.save(update_fields=["era"])


def sync(server: McpServer) -> dict:
    """Brings the server's Tool rows in line with what it offers now.

    Returns counts: {"added", "changed", "removed"}. A failure leaves the rows as they
    were and is recorded on the server (`last_error`), then raised as McpError.
    """
    client = client_for(server)
    try:
        # Outside the transaction below: the network call can be slow, and the error must
        # be saved even though nothing else is.
        remote = client.list_tools()
    except mcp.McpError as error:
        server.last_error = str(error)
        server.save(update_fields=["last_error"])
        raise
    remember_era(server, client)
    return store(server, remote)


@transaction.atomic
def store(server: McpServer, remote: list[mcp.RemoteTool]) -> dict:
    """Saves a fetched tool list: all of it or none of it."""
    existing = {tool.remote_name: tool for tool in server.tools.all()}
    counts = {"added": 0, "changed": 0, "removed": 0}
    seen: set[str] = set()
    taken = set(
        Tool.objects.filter(workspace=server.workspace).exclude(mcp_server=server).values_list("name", flat=True)
    )
    for remote_tool in remote:
        name = local_name(server, remote_tool.name)
        if remote_tool.name in seen or name in taken:
            # Two remote names that clean to the same local one: the first wins.
            continue
        seen.add(remote_tool.name)
        taken.add(name)
        current = definition_hash(remote_tool)
        fields = {
            "name": name,
            "description": remote_tool.description or f"The {remote_tool.name} tool of {server.name}.",
            "input_schema": remote_tool.input_schema,
            "read_only": remote_tool.read_only,
            "definition_hash": current,
        }
        tool = existing.get(remote_tool.name)
        if tool is None:
            Tool.objects.create(
                workspace=server.workspace, mcp_server=server, remote_name=remote_tool.name, enabled=False, **fields
            )
            counts["added"] += 1
        elif tool.definition_hash != current or tool.name != name:
            # approved_hash stays as it was, so a changed definition is no longer approved.
            for field, value in fields.items():
                setattr(tool, field, value)
            tool.save(update_fields=list(fields))
            counts["changed"] += 1
    for remote_name, tool in existing.items():
        if remote_name not in seen:
            tool.delete()
            counts["removed"] += 1

    server.last_synced_at = timezone.now()
    server.last_error = ""
    server.save(update_fields=["last_synced_at", "last_error"])
    return counts


def approve(tool: Tool, enabled: bool) -> Tool:
    """The owner switches an MCP tool on (approving its definition as it is now) or off."""
    tool.enabled = enabled
    if enabled:
        tool.approved_hash = tool.definition_hash
    tool.save(update_fields=["enabled", "approved_hash"])
    return tool


def usable(workspace) -> list[Tool]:
    """The workspace tools the AI may be offered right now: HTTP tools that are on, and MCP
    tools that are on, approved as they are now, and on a server that is on."""
    return [
        tool
        for tool in Tool.objects.filter(workspace=workspace, enabled=True).select_related("mcp_server")
        if tool.mcp_server is None or (tool.mcp_server.enabled and not tool.needs_review)
    ]


def run(tool: Tool, inputs: dict) -> tuple[str, bool]:
    """Calls an MCP tool. Returns (result text for the model, is_error)."""
    server = tool.mcp_server
    client = client_for(server)
    try:
        text, is_error = client.call_tool(tool.remote_name, inputs or {})
    except mcp.McpError as error:
        return str(error), True
    remember_era(server, client)
    if len(text) > http_tools.MAX_RESULT_CHARS:
        text = text[: http_tools.MAX_RESULT_CHARS] + " ...[truncated]"
    return text, is_error
