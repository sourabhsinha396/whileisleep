from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.security import token_auth

from .models import Membership, Workspace
from .schemas import MemberIn, MemberOut, WorkspaceIn, WorkspaceOut, WorkspacePatch
from .services import create_workspace, member_workspace, owner_workspace

router = Router(tags=["workspaces"], auth=token_auth)


def workspace_out(workspace: Workspace, viewer, role: str, open_count: int = 0) -> dict:
    return {
        **{f: getattr(workspace, f) for f in WorkspaceOut.model_fields if hasattr(workspace, f)},
        "role": role,
        "open_count": open_count,
        "llm_ready": workspace.organization.llm_ready,
        "is_organization_owner": workspace.organization.owner_id == viewer.id,
    }


@router.get("/workspaces", response=list[WorkspaceOut])
def list_workspaces(request):
    memberships = (
        Membership.objects.filter(user=request.auth)
        .select_related("workspace__organization")
        .order_by("workspace__name")
    )
    counts = dict(
        Workspace.objects.filter(memberships__user=request.auth)
        .annotate(n=Count("conversations", filter=Q(conversations__status="open")))
        .values_list("id", "n")
    )
    return [workspace_out(m.workspace, request.auth, m.role, counts.get(m.workspace_id, 0)) for m in memberships]


@router.post("/workspaces", response=WorkspaceOut)
def create(request, payload: WorkspaceIn):
    return workspace_out(create_workspace(request.auth, **payload.dict()), request.auth, Membership.Role.OWNER)


@router.get("/workspaces/{workspace_id}", response=WorkspaceOut)
def get(request, workspace_id: int):
    workspace = member_workspace(request.auth, workspace_id)
    role = Membership.objects.get(user=request.auth, workspace=workspace).role
    return workspace_out(workspace, request.auth, role)


@router.patch("/workspaces/{workspace_id}", response=WorkspaceOut)
def update(request, workspace_id: int, payload: WorkspacePatch):
    workspace = owner_workspace(request.auth, workspace_id)
    for field, value in payload.dict(exclude_unset=True).items():
        setattr(workspace, field, value)
    workspace.save()
    return workspace_out(workspace, request.auth, Membership.Role.OWNER)


@router.get("/workspaces/{workspace_id}/members", response=list[MemberOut])
def members(request, workspace_id: int):
    workspace = member_workspace(request.auth, workspace_id)
    return [
        {"user_id": m.user_id, "name": m.user.first_name or m.user.email, "email": m.user.email, "role": m.role}
        for m in workspace.memberships.select_related("user").order_by("user__email")
    ]


@router.post("/workspaces/{workspace_id}/members", response=MemberOut)
def add_member(request, workspace_id: int, payload: MemberIn):
    """Adds someone who already has an account. Email invites come later."""
    workspace = owner_workspace(request.auth, workspace_id)
    if payload.role not in Membership.Role.values:
        raise HttpError(400, "Role must be owner or agent.")
    user = get_user_model().objects.filter(username=payload.email.lower()).first()
    if user is None:
        raise HttpError(404, "No account with that email. Ask them to sign up first.")
    membership, _ = Membership.objects.update_or_create(user=user, workspace=workspace, defaults={"role": payload.role})
    return {"user_id": user.id, "name": user.first_name or user.email, "email": user.email, "role": membership.role}
