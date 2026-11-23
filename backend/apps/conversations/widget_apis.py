"""Public APIs the embeddable widget calls from customers' websites.

The workspace is named by its public key in the path. The visitor proves who they are
with the `X-Visitor-Token` header that POST /session hands out.
"""

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from apps.agent import actions, pipeline
from apps.knowledge.models import Article
from apps.knowledge.search import search
from apps.realtime import presence
from apps.workspaces.models import Workspace
from whileisleep.client_ip import client_ip

from . import identity, limits
from .models import Conversation, Message, Visitor
from .schemas import (
    ArticleOut,
    ArticleRef,
    WidgetActionIn,
    WidgetConfigOut,
    WidgetMessageIn,
    WidgetMessagesOut,
    WidgetSessionIn,
    WidgetSessionOut,
)
from .serializers import message_out
from .services import add_message, current_conversation, is_stale, touch_visitor

router = Router(tags=["widget"])


def get_workspace(key: str) -> Workspace:
    return get_object_or_404(Workspace, public_key=key)


def get_visitor(request, workspace: Workspace) -> Visitor:
    token = request.headers.get("X-Visitor-Token", "")
    visitor = Visitor.objects.filter(workspace=workspace, token=token).first() if token else None
    if visitor is None:
        raise HttpError(401, "Unknown visitor. Start a session first.")
    return visitor


@router.get("/{key}/config", response=WidgetConfigOut)
def config(request, key: str):
    return get_workspace(key)


@router.post("/{key}/session", response=WidgetSessionOut)
def session(request, key: str, payload: WidgetSessionIn):
    """Start or resume a visitor. The widget calls it on each page load; its live stream
    (or, without one, its polling) keeps the visitor online after that."""
    workspace = get_workspace(key)
    token = request.headers.get("X-Visitor-Token", "")
    visitor = Visitor.objects.filter(workspace=workspace, token=token).first() if token else None
    if payload.identity_token:
        try:
            claims = identity.verify(workspace, payload.identity_token)
        except identity.IdentityError as error:
            raise HttpError(401, str(error)) from error
        # The signed-in user's own visitor, which may not be the one this browser had.
        visitor = identity.sign_in(workspace, visitor, claims)
    if visitor is None:
        if not limits.allow_new_visitor(client_ip(request)):
            raise HttpError(429, "Too many new chats from your network. Please try again later.")
        visitor = Visitor(workspace=workspace, ip=client_ip(request))
    touch_visitor(
        visitor,
        current_url=payload.url,
        page_title=payload.title,
        referrer=payload.referrer or None,
        user_agent=request.headers.get("User-Agent", ""),
        details=payload.details(),
    )
    presence.touch(visitor)
    conversation = current_conversation(visitor)
    last = conversation.messages.filter(is_note=False).order_by("-id").first() if conversation else None
    return {
        "token": visitor.token,
        "visitor_id": visitor.id,
        "conversation_id": conversation.id if conversation else None,
        "last_message_id": last.id if last else None,
    }


@router.post("/{key}/restart", response=dict)
def restart(request, key: str):
    """Start a new chat. The old conversation stays in the inbox; the widget just stops showing it."""
    workspace = get_workspace(key)
    visitor = get_visitor(request, workspace)
    visitor.chat_cleared_at = timezone.now()
    visitor.save(update_fields=["chat_cleared_at"])
    return {"ok": True}


@router.get("/{key}/messages", response=WidgetMessagesOut)
def messages(request, key: str, after: int = 0):
    """New messages since `after`. The widget polls this when it has no live stream, so it
    also keeps the visitor online."""
    workspace = get_workspace(key)
    visitor = get_visitor(request, workspace)
    presence.touch(visitor)
    conversation = current_conversation(visitor)
    if conversation is None:
        return {"conversation_id": None, "messages": []}
    rows = conversation.messages.filter(is_note=False, id__gt=after).exclude(sender=Message.Sender.SYSTEM)
    return {
        "conversation_id": conversation.id,
        "human_requested": conversation.human_requested,
        "messages": [message_out(m) for m in rows.select_related("author")],
    }


@router.post("/{key}/messages", response=WidgetMessagesOut)
def send(request, key: str, payload: WidgetMessageIn):
    workspace = get_workspace(key)
    visitor = get_visitor(request, workspace)
    if not limits.allow_message(visitor.id, client_ip(request)):
        raise HttpError(429, "You're sending messages too quickly. Please wait a minute.")
    conversation = current_conversation(visitor)
    if conversation is None or is_stale(conversation):
        conversation = Conversation.objects.create(workspace=workspace, visitor=visitor)
    message = add_message(
        conversation, Message.Sender.VISITOR, payload.body.strip(), intent=payload.intent, intent_data=payload.data
    )
    pipeline.handle(conversation, message)
    conversation.refresh_from_db(fields=["human_requested"])
    rows = conversation.messages.filter(is_note=False, id__gte=message.id).exclude(sender=Message.Sender.SYSTEM)
    return {
        "conversation_id": conversation.id,
        "human_requested": conversation.human_requested,
        "messages": [message_out(m) for m in rows],
    }


@router.post("/{key}/actions", response=dict)
def action(request, key: str, payload: WidgetActionIn):
    """An A2UI action event: the visitor pressed a button in a bot message."""
    workspace = get_workspace(key)
    visitor = get_visitor(request, workspace)
    conversation = current_conversation(visitor)
    if conversation is None:
        raise HttpError(400, "No conversation yet.")
    try:
        return actions.handle(conversation, payload.name, payload.context, payload.surfaceId)
    except actions.ActionError as error:
        raise HttpError(400, str(error)) from error


@router.get("/{key}/articles", response=list[ArticleRef])
def articles(request, key: str, q: str = ""):
    workspace = get_workspace(key)
    rows = (
        search(workspace, q, limit=10, prefix=True)
        if q.strip()
        else Article.objects.filter(workspace=workspace, published=True)[:20]
    )
    return [{"id": a.id, "title": a.title, "excerpt": a.body[:160]} for a in rows]


@router.get("/{key}/articles/{article_id}", response=ArticleOut)
def article(request, key: str, article_id: int):
    workspace = get_workspace(key)
    return get_object_or_404(Article, pk=article_id, workspace=workspace, published=True)
