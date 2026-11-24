from zoneinfo import available_timezones

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from ninja import File, Router, UploadedFile
from ninja.errors import HttpError

from apps.accounts.models import photo_url
from apps.accounts.security import token_auth
from whileisleep import images

from . import setup
from .colors import WIDGET_COLORS
from .models import Membership, Workspace, new_identity_secret
from .schemas import IdentitySecretOut, MemberIn, MemberOut, SetupStepOut, WorkspaceIn, WorkspaceOut, WorkspacePatch
from .services import create_workspace, member_workspace, owner_workspace

router = Router(tags=["workspaces"], auth=token_auth)


def workspace_out(workspace: Workspace, viewer, role: str, open_count: int = 0) -> dict:
    return {
        **{f: getattr(workspace, f) for f in WorkspaceOut.model_fields if hasattr(workspace, f)},
        "role": role,
        "open_count": open_count,
        "llm_ready": workspace.organization.llm_ready,
        "is_organization_owner": workspace.organization.owner_id == viewer.id,
        "uploads_enabled": settings.UPLOADS_ENABLED,
        "article_uploads_enabled": workspace.organization.storage_bucket is not None,
    }


@router.get("/workspaces", response=list[WorkspaceOut])
def list_workspaces(request):
    memberships = (
        Membership.objects.filter(user=request.auth)
        .select_related("workspace__organization__bucket")
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
    data = payload.dict(exclude_unset=True)
    if data.get("timezone") is not None and data["timezone"] not in available_timezones():
        raise HttpError(400, "Unknown timezone. Use a name like Europe/Berlin or Asia/Kolkata.")
    if data.get("color") is None or data["color"] == workspace.color:
        # Unchanged. Also how a workspace keeps a color from before there was a list.
        data.pop("color", None)
    else:
        data["color"] = data["color"].lower()
        if data["color"] not in WIDGET_COLORS:
            raise HttpError(400, "Pick one of the listed widget colors.")
    if data.get("slug") is None:
        data.pop("slug", None)
    elif Workspace.objects.filter(slug=data["slug"]).exclude(pk=workspace.pk).exists():
        raise HttpError(400, "That address is taken. Try another.")
    for field, value in data.items():
        setattr(workspace, field, value)
    workspace.save()
    return workspace_out(workspace, request.auth, Membership.Role.OWNER)


@router.post("/workspaces/{workspace_id}/logo", response=WorkspaceOut)
def upload_logo(request, workspace_id: int, file: UploadedFile = File(...)):  # noqa: B008
    workspace = owner_workspace(request.auth, workspace_id)
    images.require_storage()
    images.replace(workspace, "logo", images.clean_image(file, images.AVATAR_SIDE, square=True))
    return workspace_out(workspace, request.auth, Membership.Role.OWNER)


@router.delete("/workspaces/{workspace_id}/logo", response=WorkspaceOut)
def remove_logo(request, workspace_id: int):
    workspace = owner_workspace(request.auth, workspace_id)
    images.replace(workspace, "logo", None)
    return workspace_out(workspace, request.auth, Membership.Role.OWNER)


@router.get("/workspaces/{workspace_id}/setup", response=list[SetupStepOut])
def setup_steps(request, workspace_id: int):
    """The steps of the "Get started" guide, in order, and which are done."""
    return setup.steps(member_workspace(request.auth, workspace_id))


@router.get("/workspaces/{workspace_id}/identity-secret", response=IdentitySecretOut)
def identity_secret(request, workspace_id: int):
    """The secret the site's server signs identity tokens with. Owners only."""
    return {"secret": owner_workspace(request.auth, workspace_id).identity_secret}


@router.post("/workspaces/{workspace_id}/identity-secret/rotate", response=IdentitySecretOut)
def rotate_identity_secret(request, workspace_id: int):
    """Replaces the secret, e.g. after a leak. Tokens signed with the old one stop working."""
    workspace = owner_workspace(request.auth, workspace_id)
    workspace.identity_secret = new_identity_secret()
    workspace.save(update_fields=["identity_secret"])
    return {"secret": workspace.identity_secret}


def member_out(membership: Membership) -> dict:
    user = membership.user
    return {
        "user_id": user.id,
        "name": user.first_name or user.email,
        "email": user.email,
        "role": membership.role,
        "photo_url": photo_url(user),
    }


@router.get("/workspaces/{workspace_id}/members", response=list[MemberOut])
def members(request, workspace_id: int):
    workspace = member_workspace(request.auth, workspace_id)
    return [member_out(m) for m in workspace.memberships.select_related("user__profile").order_by("user__email")]


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
    return member_out(membership)
