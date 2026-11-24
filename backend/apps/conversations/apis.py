"""Dashboard APIs: the inbox and the visitors list."""

from datetime import timedelta

from django.conf import settings
from django.db.models import Max, OuterRef, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import File, Router, UploadedFile
from ninja.errors import HttpError

from apps.accounts.models import photo_url
from apps.accounts.security import token_auth
from apps.realtime import events, presence
from apps.workspaces.models import Membership
from apps.workspaces.services import member_workspace

from . import attachments, attributes
from .models import Attachment, Conversation, Message, Visitor
from .schemas import (
    AttachmentOut,
    AttributeIn,
    AttributeOut,
    ConversationDetail,
    ConversationPatch,
    ConversationRow,
    MessageOut,
    OpeningIn,
    ReplyIn,
    VisitorOut,
)
from .serializers import attachment_out, conversation_row, message_out, visitor_out
from .services import add_message, reply_as, set_human_requested, set_status, start_conversation

router = Router(tags=["inbox"], auth=token_auth)

STATUSES = {"open", "resolved", "all"}


def get_conversation(request, workspace_id: int, conversation_id: int) -> Conversation:
    workspace = member_workspace(request.auth, workspace_id)
    return get_object_or_404(
        Conversation.objects.select_related("visitor", "workspace"), pk=conversation_id, workspace=workspace
    )


@router.get("/workspaces/{workspace_id}/conversations", response=list[ConversationRow])
def list_conversations(request, workspace_id: int, status: str = "open", mine: bool = False):
    workspace = member_workspace(request.auth, workspace_id)
    if status not in STATUSES:
        raise HttpError(400, "status must be open, resolved or all.")
    last = Message.objects.filter(conversation=OuterRef("pk"), is_note=False).order_by("-id")
    rows = workspace.conversations.select_related("visitor").annotate(
        preview=Subquery(last.values("body")[:1]), last_id=Subquery(last.values("pk")[:1])
    )
    if status != "all":
        rows = rows.filter(status=status)
    if mine:
        rows = rows.filter(assignee=request.auth)
    rows = list(rows[:200])
    # A message that is only files is listed by their names.
    files: dict[int, list[str]] = {}
    for message_id, name in Attachment.objects.filter(
        message_id__in=[c.last_id for c in rows if not c.preview]
    ).values_list("message_id", "name"):
        files.setdefault(message_id, []).append(name)
    online = presence.online_ids({c.visitor_id for c in rows})
    result = []
    for conversation in rows:
        row = conversation_row(conversation, online=None if online is None else conversation.visitor_id in online)
        row["preview"] = (conversation.preview or "")[:140] or attachments.label(files.get(conversation.last_id, []))
        result.append(row)
    return result


@router.get("/workspaces/{workspace_id}/conversations/{conversation_id}", response=ConversationDetail)
def get(request, workspace_id: int, conversation_id: int):
    conversation = get_conversation(request, workspace_id, conversation_id)
    if conversation.unread:
        conversation.unread = False
        conversation.save(update_fields=["unread"])
        # Teammates' inbox lists drop the unread dot too.
        events.conversation_changed(conversation)
    messages = list(conversation.messages.select_related("author__profile").prefetch_related("attachments"))
    return {
        **conversation_row(conversation, next((m for m in reversed(messages) if not m.is_note), None)),
        "messages": [message_out(m) for m in messages],
    }


@router.post("/workspaces/{workspace_id}/conversations/{conversation_id}/messages", response=MessageOut)
def reply(request, workspace_id: int, conversation_id: int, payload: ReplyIn):
    conversation = get_conversation(request, workspace_id, conversation_id)
    files = attachments.unsent(conversation.workspace, payload.attachments, user=request.auth)
    body = payload.body.strip()
    return message_out(reply_as(request.auth, conversation, body, is_note=payload.is_note, attachments=files))


@router.post("/workspaces/{workspace_id}/attachments", response=AttachmentOut)
def upload(request, workspace_id: int, file: UploadedFile = File(...)):  # noqa: B008
    """Stores a file a teammate is about to send. Sending a reply with its id attaches it."""
    workspace = member_workspace(request.auth, workspace_id)
    return attachment_out(attachments.upload(workspace, file, user=request.auth))


@router.post("/workspaces/{workspace_id}/conversations/{conversation_id}/typing", response=dict)
def typing(request, workspace_id: int, conversation_id: int):
    """A teammate is typing a reply (not a note). The visitor's widget shows it."""
    conversation = get_conversation(request, workspace_id, conversation_id)
    user = request.auth
    events.typing(conversation, Message.Sender.AGENT, user.first_name or "", who=str(user.pk), photo=photo_url(user))
    return {"ok": True}


@router.patch("/workspaces/{workspace_id}/conversations/{conversation_id}", response=ConversationRow)
def update(request, workspace_id: int, conversation_id: int, payload: ConversationPatch):
    conversation = get_conversation(request, workspace_id, conversation_id)
    data = payload.dict(exclude_unset=True)
    if "status" in data and data["status"] not in Conversation.Status.values:
        raise HttpError(400, "status must be open or resolved.")
    if "assignee_id" in data:
        assignee_id = data["assignee_id"]
        if (
            assignee_id is not None
            and not Membership.objects.filter(workspace=conversation.workspace, user_id=assignee_id).exists()
        ):
            raise HttpError(400, "That person isn't in this workspace.")
        conversation.assignee_id = assignee_id
        conversation.save(update_fields=["assignee"])
        events.conversation_changed(conversation)
    if "human_requested" in data:
        set_human_requested(conversation, data["human_requested"], by=request.auth)
    if "status" in data:
        set_status(conversation, data["status"], by=request.auth)
    return conversation_row(conversation, conversation.messages.filter(is_note=False).last())


@router.get("/workspaces/{workspace_id}/visitors", response=list[VisitorOut])
def list_visitors(request, workspace_id: int, online: bool = False):
    workspace = member_workspace(request.auth, workspace_id)
    rows = workspace.visitors.annotate(conversation_id=Max("conversations__id")).order_by("-last_seen")
    online_now = presence.online_in(workspace.id)
    if online and online_now is not None:
        rows = rows.filter(pk__in=online_now)
    elif online:
        # No Redis: the last time the widget called us.
        rows = rows.filter(last_seen__gte=timezone.now() - timedelta(seconds=settings.PRESENCE_TTL_SECONDS))
    else:
        rows = rows.filter(last_seen__gte=timezone.now() - timedelta(days=7))
    rows = list(rows[:200])
    online_set = set(online_now) if online_now is not None else None
    return [visitor_out(v, v.conversation_id, None if online_set is None else v.id in online_set) for v in rows]


def save_attribute(target, key: str, payload: AttributeIn) -> list[dict]:
    if not attributes.KEY.match(key):
        raise HttpError(400, "Attribute names are lowercase letters, digits and underscores, starting with a letter.")
    if attributes.clean(key, payload.value) is None:
        raise HttpError(400, "That value can't be saved.")
    # A teammate's value replaces anything except one the host site signed.
    if attributes.is_verified(target, key):
        raise HttpError(400, "This value was verified by your website and can't be changed here.")
    attributes.set_attribute(target, key, payload.value, attributes.Source.AGENT)
    return attributes.listing(target)


@router.put("/workspaces/{workspace_id}/visitors/{visitor_id}/attributes/{key}", response=list[AttributeOut])
def set_visitor_attribute(request, workspace_id: int, visitor_id: int, key: str, payload: AttributeIn):
    """A teammate records or corrects something about a visitor."""
    workspace = member_workspace(request.auth, workspace_id)
    return save_attribute(get_object_or_404(Visitor, pk=visitor_id, workspace=workspace), key, payload)


@router.delete("/workspaces/{workspace_id}/visitors/{visitor_id}/attributes/{key}", response=list[AttributeOut])
def delete_visitor_attribute(request, workspace_id: int, visitor_id: int, key: str):
    visitor = get_object_or_404(Visitor, pk=visitor_id, workspace=member_workspace(request.auth, workspace_id))
    attributes.remove(visitor, key)
    return attributes.listing(visitor)


@router.put("/workspaces/{workspace_id}/conversations/{conversation_id}/attributes/{key}", response=list[AttributeOut])
def set_conversation_attribute(request, workspace_id: int, conversation_id: int, key: str, payload: AttributeIn):
    return save_attribute(get_conversation(request, workspace_id, conversation_id), key, payload)


@router.delete(
    "/workspaces/{workspace_id}/conversations/{conversation_id}/attributes/{key}", response=list[AttributeOut]
)
def delete_conversation_attribute(request, workspace_id: int, conversation_id: int, key: str):
    conversation = get_conversation(request, workspace_id, conversation_id)
    attributes.remove(conversation, key)
    return attributes.listing(conversation)


@router.post("/workspaces/{workspace_id}/visitors/{visitor_id}/conversations", response=ConversationRow)
def message_first(request, workspace_id: int, visitor_id: int, payload: OpeningIn):
    """A teammate messages a visitor first (from the Visitors page)."""
    workspace = member_workspace(request.auth, workspace_id)
    visitor = get_object_or_404(Visitor, pk=visitor_id, workspace=workspace)
    conversation = start_conversation(visitor, by=request.auth, assignee=request.auth, unread=False)
    message = add_message(conversation, Message.Sender.AGENT, payload.body.strip(), author=request.auth)
    return conversation_row(conversation, message)
