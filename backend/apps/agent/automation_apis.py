"""Dashboard APIs for rules and playbooks. Members read; owners change them."""

from datetime import datetime
from typing import Any

from django.shortcuts import get_object_or_404
from ninja import Router, Schema
from ninja.errors import HttpError
from pydantic import Field

from apps.accounts.security import token_auth
from apps.workspaces.services import member_workspace, owner_workspace

from . import rules
from .models import Playbook, Rule

router = Router(tags=["automation"], auth=token_auth)


class RuleIn(Schema):
    name: str = Field(min_length=1, max_length=120)
    enabled: bool = True
    position: int = Field(0, ge=0)
    # A condition tree and a list of actions; apps.agent.rules documents both.
    conditions: dict[str, Any]
    actions: list[dict[str, Any]]
    also_when_human: bool = False


class RuleOut(RuleIn):
    id: int
    match_count: int
    last_matched_at: datetime | None


class BacktestIn(Schema):
    conditions: dict[str, Any]


class BacktestSample(Schema):
    message_id: int
    conversation_id: int
    text: str
    created_at: datetime


class BacktestOut(Schema):
    # Recent visitor messages looked at, and how many the conditions matched.
    checked: int
    matched: int
    samples: list[BacktestSample]


class PlaybookIn(Schema):
    title: str = Field(min_length=1, max_length=120)
    when_to_use: str = Field(min_length=1, max_length=300)
    instructions: str = Field(min_length=1, max_length=20000)
    enabled: bool = True


class PlaybookOut(PlaybookIn):
    id: int
    updated_at: datetime


def check_rule(payload: RuleIn) -> dict:
    try:
        rules.validate(payload.conditions, payload.actions)
    except rules.InvalidRule as error:
        raise HttpError(400, str(error)) from error
    return payload.dict()


# --- Rules ---


@router.get("/workspaces/{workspace_id}/rules", response=list[RuleOut])
def list_rules(request, workspace_id: int):
    return member_workspace(request.auth, workspace_id).rules.all()


@router.post("/workspaces/{workspace_id}/rules", response=RuleOut)
def create_rule(request, workspace_id: int, payload: RuleIn):
    return Rule.objects.create(workspace=owner_workspace(request.auth, workspace_id), **check_rule(payload))


@router.post("/workspaces/{workspace_id}/rules/backtest", response=BacktestOut)
def backtest_rule(request, workspace_id: int, payload: BacktestIn):
    """Tries conditions on the workspace's recent visitor messages, before saving a rule."""
    workspace = member_workspace(request.auth, workspace_id)
    try:
        rules.validate(payload.conditions, [{"type": "handoff"}])
    except rules.InvalidRule as error:
        raise HttpError(400, str(error)) from error
    return rules.backtest(workspace, payload.conditions)


@router.put("/workspaces/{workspace_id}/rules/{rule_id}", response=RuleOut)
def update_rule(request, workspace_id: int, rule_id: int, payload: RuleIn):
    rule = get_object_or_404(Rule, pk=rule_id, workspace=owner_workspace(request.auth, workspace_id))
    for field, value in check_rule(payload).items():
        setattr(rule, field, value)
    rule.save()
    return rule


@router.delete("/workspaces/{workspace_id}/rules/{rule_id}")
def delete_rule(request, workspace_id: int, rule_id: int):
    get_object_or_404(Rule, pk=rule_id, workspace=owner_workspace(request.auth, workspace_id)).delete()
    return {"ok": True}


# --- Playbooks ---


@router.get("/workspaces/{workspace_id}/playbooks", response=list[PlaybookOut])
def list_playbooks(request, workspace_id: int):
    return member_workspace(request.auth, workspace_id).playbooks.all()


def save_playbook(workspace, payload: PlaybookIn, playbook: Playbook | None = None) -> Playbook:
    others = Playbook.objects.filter(workspace=workspace, title__iexact=payload.title.strip())
    if playbook:
        others = others.exclude(pk=playbook.pk)
    if others.exists():
        raise HttpError(400, "A playbook with this title already exists.")
    playbook = playbook or Playbook(workspace=workspace)
    for field, value in payload.dict().items():
        setattr(playbook, field, value.strip() if isinstance(value, str) else value)
    playbook.save()
    return playbook


@router.post("/workspaces/{workspace_id}/playbooks", response=PlaybookOut)
def create_playbook(request, workspace_id: int, payload: PlaybookIn):
    return save_playbook(owner_workspace(request.auth, workspace_id), payload)


@router.put("/workspaces/{workspace_id}/playbooks/{playbook_id}", response=PlaybookOut)
def update_playbook(request, workspace_id: int, playbook_id: int, payload: PlaybookIn):
    workspace = owner_workspace(request.auth, workspace_id)
    return save_playbook(workspace, payload, get_object_or_404(Playbook, pk=playbook_id, workspace=workspace))


@router.delete("/workspaces/{workspace_id}/playbooks/{playbook_id}")
def delete_playbook(request, workspace_id: int, playbook_id: int):
    get_object_or_404(Playbook, pk=playbook_id, workspace=owner_workspace(request.auth, workspace_id)).delete()
    return {"ok": True}
