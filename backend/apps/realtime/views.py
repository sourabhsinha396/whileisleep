"""Live streams: server-sent events for the widget and the inbox.

These are async views, served by the ASGI process (uvicorn), where one connection waiting
on Redis costs a coroutine rather than a thread. Everything else stays on the WSGI
process; Caddy sends only the two stream paths here.

    GET /api/v1/widget/{key}/stream          X-Visitor-Token: vt_...
    GET /api/v1/workspaces/{id}/stream       Authorization: Bearer ...

Tokens go in headers, never the URL (URLs end up in logs), so browsers read these with
fetch() rather than EventSource, which can't send headers.

A client that reconnects sends `Last-Event-ID: <the last message id it has>` and first
gets every message after that one, then live events. Message events carry their message
id as the SSE id. The stream subscribes before it reads the backlog, so nothing published
in between is lost; anything that arrives twice is dropped by id.

A comment line every STREAM_PING_SECONDS keeps proxies from closing a quiet connection and,
on the widget's stream, keeps the visitor online (apps.realtime.presence). After
STREAM_MAX_SECONDS the stream ends and the client reconnects, which checks its token again.

Without Redis these answer 503 and clients poll the REST endpoints instead.
"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable

from asgiref.sync import sync_to_async
from django.conf import settings
from django.core.handlers.asgi import ASGIRequest
from django.core.serializers.json import DjangoJSONEncoder
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone

from apps.accounts.models import AuthToken
from apps.conversations.models import Message, Visitor
from apps.conversations.serializers import message_out
from apps.conversations.services import current_conversation
from apps.workspaces.models import Workspace

from . import bus, presence

log = logging.getLogger(__name__)

# How much backlog a reconnecting inbox gets; beyond this it reloads the conversation list.
REPLAY_LIMIT = 200

Event = tuple[str, dict]
Hook = Callable[[], Awaitable[None]] | None


def error(status: int, detail: str) -> JsonResponse:
    return JsonResponse({"detail": detail}, status=status)


def refuse(request) -> JsonResponse | None:
    """Why this request can't get a stream here, if it can't."""
    if not isinstance(request, ASGIRequest):
        # Under WSGI Django would read the endless stream into a list and hold the worker
        # forever. The proxy should send streams to the ASGI process; clients poll instead.
        return error(503, "Live updates are served by the ASGI process; poll instead.")
    if request.method != "GET":
        return error(405, "Use GET.")
    return None


def last_event_id(request) -> int | None:
    value = request.headers.get("Last-Event-ID", "").strip()
    return int(value) if value.isdigit() else None


def frame(event: str, data: dict) -> str:
    lines = []
    if event == "message":
        lines.append(f"id: {data['message']['id']}")
    lines.append(f"event: {event}")
    # The same encoder as published events and the REST API: ISO 8601 dates.
    lines.append(f"data: {json.dumps(data, separators=(',', ':'), cls=DjangoJSONEncoder)}")
    return "\n".join(lines) + "\n\n"


async def event_stream(
    client,
    channels: list[str],
    backlog: Callable[[], Awaitable[list[Event]]],
    on_open: Hook = None,
    on_ping: Hook = None,
    on_close: Hook = None,
) -> AsyncIterator[str]:
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    await pubsub.subscribe(*channels)
    try:
        if on_open:
            await on_open()
        # Tells EventSource-style clients how soon to reconnect, and sends the headers now.
        yield "retry: 3000\n: connected\n\n"
        replayed = 0
        for event, data in await backlog():
            replayed = max(replayed, data["message"]["id"])
            yield frame(event, data)

        loop = asyncio.get_running_loop()
        ends = loop.time() + settings.STREAM_MAX_SECONDS
        next_ping = loop.time() + settings.STREAM_PING_SECONDS
        while (now := loop.time()) < ends:
            if now >= next_ping:
                yield ": ping\n\n"
                next_ping = now + settings.STREAM_PING_SECONDS
                if on_ping:
                    await on_ping()
            message = await pubsub.get_message(timeout=max(0.0, min(next_ping, ends) - loop.time()))
            if message is None or message["type"] != "message":
                continue
            payload = json.loads(message["data"])
            event, data = payload["event"], payload["data"]
            if event == "message" and data["message"]["id"] <= replayed:
                continue
            yield frame(event, data)
    finally:
        # Runs when the stream ends and when the browser goes away (the task is cancelled).
        try:
            await pubsub.aclose()
            if on_close:
                await on_close()
        except Exception:  # cleanup must not mask why the stream ended
            log.exception("Error closing a live stream")
        finally:
            await client.aclose()


def sse_response(stream: AsyncIterator[str]) -> StreamingHttpResponse:
    response = StreamingHttpResponse(stream, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache, no-transform"
    # nginx and similar proxies: don't buffer. (Caddy flushes event streams by itself.)
    response["X-Accel-Buffering"] = "no"
    return response


# --- The widget ---


def widget_backlog(visitor: Visitor, after: int | None) -> list[Event]:
    if after is None:
        return []
    conversation = current_conversation(visitor)
    if conversation is None:
        return []
    rows = (
        conversation.messages.filter(is_note=False, id__gt=after)
        .exclude(sender=Message.Sender.SYSTEM)
        .select_related("author__profile", "conversation")
        .prefetch_related("attachments")
    )
    return [("message", {"conversation_id": conversation.id, "message": message_out(m)}) for m in rows]


async def widget_stream(request, key: str):
    if refused := refuse(request):
        return refused
    workspace = await Workspace.objects.filter(public_key=key).afirst()
    if workspace is None:
        return error(404, "Not found.")
    token = request.headers.get("X-Visitor-Token", "")
    visitor = await Visitor.objects.filter(workspace=workspace, token=token).afirst() if token else None
    if visitor is None:
        return error(401, "Unknown visitor. Start a session first.")
    client = bus.async_client()
    if client is None:
        return error(503, "Live updates are off; poll /messages instead.")
    after = last_event_id(request)

    async def opened():
        await presence.stream_opened(client, workspace.id, visitor.id)

    async def alive():
        await presence.stream_alive(client, workspace.id, visitor.id)

    async def closed():
        if await presence.stream_closed(client, workspace.id, visitor.id):
            # Their last tab closed: when they were last here, for the Visitors page.
            await Visitor.objects.filter(pk=visitor.pk).aupdate(last_seen=timezone.now())

    stream = event_stream(
        client,
        [bus.visitor_channel(visitor.id)],
        lambda: sync_to_async(widget_backlog)(visitor, after),
        on_open=opened,
        on_ping=alive,
        on_close=closed,
    )
    return sse_response(stream)


# --- The inbox ---


def inbox_backlog(workspace_id: int, after: int | None) -> list[Event]:
    if after is None:
        return []
    rows = (
        Message.objects.filter(conversation__workspace_id=workspace_id, id__gt=after)
        .select_related("author__profile", "conversation")
        .prefetch_related("attachments")
        .order_by("id")[:REPLAY_LIMIT]
    )
    return [("message", {"conversation_id": m.conversation_id, "message": message_out(m)}) for m in rows]


async def inbox_stream(request, workspace_id: int):
    if refused := refuse(request):
        return refused
    scheme, _, key = request.headers.get("Authorization", "").partition(" ")
    token = (
        await AuthToken.objects.select_related("user").filter(key=key, user__is_active=True).afirst()
        if scheme.lower() == "bearer" and key
        else None
    )
    if token is None:
        return error(401, "Unauthorized")
    if not await Workspace.objects.filter(pk=workspace_id, memberships__user=token.user).aexists():
        return error(404, "Not found.")
    client = bus.async_client()
    if client is None:
        return error(503, "Live updates are off; poll the API instead.")
    after = last_event_id(request)
    stream = event_stream(
        client, [bus.workspace_channel(workspace_id)], lambda: sync_to_async(inbox_backlog)(workspace_id, after)
    )
    return sse_response(stream)
