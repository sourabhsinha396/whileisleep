"""Dashboard APIs: the inbox and the visitors list."""

from datetime import timedelta

from django.conf import settings
from django.db.models import Max, OuterRef, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.security import token_auth
from apps.workspaces.models import Membership
from apps.workspaces.services import member_workspace

from .models import Conversation, Message, Visitor
from .schemas import ConversationDetail, ConversationPatch, ConversationRow, MessageOut, ReplyIn, VisitorOut
from .serializers import conversation_row, message_out, visitor_out
from .services import add_message

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
    last_body = Message.objects.filter(conversation=OuterRef("pk"), is_note=False).order_by("-id").values("body")[:1]
    rows = workspace.conversations.select_related("visitor").annotate(preview=Subquery(last_body))
    if status != "all":
        rows = rows.filter(status=status)
    if mine:
        rows = rows.filter(assignee=request.auth)
    result = []
    for conversation in rows[:200]:
        row = conversation_row(conversation)
        row["preview"] = (conversation.preview or "")[:140]
        result.append(row)
    return result


@router.get("/workspaces/{workspace_id}/conversations/{conversation_id}", response=ConversationDetail)
def get(request, workspace_id: int, conversation_id: int):
    conversation = get_conversation(request, workspace_id, conversation_id)
    if conversation.unread:
        conversation.unread = False
        conversation.save(update_fields=["unread"])
    messages = list(conversation.messages.select_related("author"))
    return {
        **conversation_row(conversation, next((m for m in reversed(messages) if not m.is_note), None)),
        "messages": [message_out(m) for m in messages],
    }


@router.post("/workspaces/{workspace_id}/conversations/{conversation_id}/messages", response=MessageOut)
def reply(request, workspace_id: int, conversation_id: int, payload: ReplyIn):
    conversation = get_conversation(request, workspace_id, conversation_id)
    message = add_message(
        conversation, Message.Sender.AGENT, payload.body.strip(), author=request.auth, is_note=payload.is_note
    )
    if not payload.is_note and conversation.assignee_id is None:
        conversation.assignee = request.auth
        conversation.save(update_fields=["assignee"])
    return message_out(message)


@router.patch("/workspaces/{workspace_id}/conversations/{conversation_id}", response=ConversationRow)
def update(request, workspace_id: int, conversation_id: int, payload: ConversationPatch):
    conversation = get_conversation(request, workspace_id, conversation_id)
    data = payload.dict(exclude_unset=True)
    if "status" in data:
        if data["status"] not in Conversation.Status.values:
            raise HttpError(400, "status must be open or resolved.")
        conversation.status = data["status"]
    if "assignee_id" in data:
        assignee_id = data["assignee_id"]
        if (
            assignee_id is not None
            and not Membership.objects.filter(workspace=conversation.workspace, user_id=assignee_id).exists()
        ):
            raise HttpError(400, "That person isn't in this workspace.")
        conversation.assignee_id = assignee_id
    if "human_requested" in data:
        conversation.human_requested = data["human_requested"]
    conversation.save()
    return conversation_row(conversation, conversation.messages.filter(is_note=False).last())


@router.get("/workspaces/{workspace_id}/visitors", response=list[VisitorOut])
def list_visitors(request, workspace_id: int, online: bool = False):
    workspace = member_workspace(request.auth, workspace_id)
    rows = workspace.visitors.annotate(conversation_id=Max("conversations__id")).order_by("-last_seen")
    if online:
        rows = rows.filter(last_seen__gte=timezone.now() - timedelta(seconds=settings.ONLINE_WINDOW_SECONDS))
    else:
        rows = rows.filter(last_seen__gte=timezone.now() - timedelta(days=7))
    return [visitor_out(v, v.conversation_id) for v in rows[:200]]


@router.post("/workspaces/{workspace_id}/visitors/{visitor_id}/conversations", response=ConversationRow)
def start_conversation(request, workspace_id: int, visitor_id: int, payload: ReplyIn):
    """A teammate messages a visitor first (from the Visitors page)."""
    workspace = member_workspace(request.auth, workspace_id)
    visitor = get_object_or_404(Visitor, pk=visitor_id, workspace=workspace)
    conversation = Conversation.objects.create(
        workspace=workspace, visitor=visitor, assignee=request.auth, unread=False
    )
    message = add_message(conversation, Message.Sender.AGENT, payload.body.strip(), author=request.auth)
    return conversation_row(conversation, message)
