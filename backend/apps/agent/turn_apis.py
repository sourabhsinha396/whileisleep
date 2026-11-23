"""Dashboard APIs for Turns: why the bot answered as it did, and what answering costs."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router, Schema

from apps.accounts.security import token_auth
from apps.conversations.models import Conversation
from apps.workspaces.services import member_workspace

from .models import Turn

router = Router(tags=["turns"], auth=token_auth)

# Stages that answered (or deliberately didn't) without calling the model.
WITHOUT_MODEL = (Turn.Stage.RULE, Turn.Stage.GUARD, Turn.Stage.FALLBACK)
# Stages that end without sending anything.
NO_REPLY = (Turn.Stage.NONE, Turn.Stage.SUPERSEDED)
MAX_SUMMARY_DAYS = 365


class TurnOut(Schema):
    id: int
    # rule, guard, ai, fallback, superseded or none: the pipeline stage that ended the turn.
    stage: str
    trigger_message_id: int | None
    reply_message_id: int | None
    rule_id: int | None
    rule_name: str = ""
    model: str
    llm_calls: int
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    cost: Decimal | None
    duration_ms: int
    steps: list[dict[str, Any]]
    error: str
    created_at: datetime


class TurnSummaryOut(Schema):
    days: int
    # Visitor messages handled in the period.
    turns: int
    by_stage: dict[str, int]
    # Turns that got a reply, and how many of those needed no model call.
    replied: int
    replied_without_model: int
    llm_calls: int
    input_tokens: int
    cached_tokens: int
    output_tokens: int
    cost: Decimal


def turn_out(turn: Turn) -> dict:
    return {
        "id": turn.id,
        "stage": turn.stage,
        "trigger_message_id": turn.trigger_id,
        "reply_message_id": turn.reply_id,
        "rule_id": turn.rule_id,
        "rule_name": turn.rule.name if turn.rule else "",
        "model": turn.model,
        "llm_calls": turn.llm_calls,
        "input_tokens": turn.input_tokens,
        "cached_tokens": turn.cached_tokens,
        "output_tokens": turn.output_tokens,
        "cost": turn.cost,
        "duration_ms": turn.duration_ms,
        "steps": turn.steps,
        "error": turn.error,
        "created_at": turn.created_at,
    }


@router.get("/workspaces/{workspace_id}/conversations/{conversation_id}/turns", response=list[TurnOut])
def conversation_turns(request, workspace_id: int, conversation_id: int):
    """Every pass of the pipeline in one conversation, oldest first."""
    workspace = member_workspace(request.auth, workspace_id)
    conversation = get_object_or_404(Conversation, pk=conversation_id, workspace=workspace)
    return [turn_out(turn) for turn in conversation.turns.select_related("rule")]


@router.get("/workspaces/{workspace_id}/turns/summary", response=TurnSummaryOut)
def summary(request, workspace_id: int, days: int = 30):
    """How the workspace's messages were answered over the last `days`, and at what cost."""
    workspace = member_workspace(request.auth, workspace_id)
    days = max(1, min(days, MAX_SUMMARY_DAYS))
    turns = Turn.objects.filter(workspace=workspace, created_at__gte=timezone.now() - timedelta(days=days))
    by_stage = dict(turns.values_list("stage").annotate(n=Count("id")))
    totals = turns.aggregate(
        llm_calls=Sum("llm_calls"),
        input_tokens=Sum("input_tokens"),
        cached_tokens=Sum("cached_tokens"),
        output_tokens=Sum("output_tokens"),
        cost=Sum("cost"),
    )
    return {
        "days": days,
        "turns": sum(by_stage.values()),
        "by_stage": {stage: by_stage.get(stage, 0) for stage in Turn.Stage.values},
        "replied": sum(count for stage, count in by_stage.items() if stage not in NO_REPLY),
        "replied_without_model": sum(by_stage.get(stage, 0) for stage in WITHOUT_MODEL),
        **{key: value or 0 for key, value in totals.items()},
    }
