from django.shortcuts import get_object_or_404

from .models import Membership, Organization, Workspace


def member_workspace(user, workspace_id: int) -> Workspace:
    """The workspace, if the user belongs to it. 404 otherwise, so ids don't leak."""
    return get_object_or_404(Workspace.objects.select_related("organization"), pk=workspace_id, memberships__user=user)


def owner_workspace(user, workspace_id: int) -> Workspace:
    return get_object_or_404(
        Workspace, pk=workspace_id, memberships__user=user, memberships__role=Membership.Role.OWNER
    )


def organization_for(user) -> Organization:
    """The organization the user owns, made on first use."""
    organization, _ = Organization.objects.get_or_create(
        owner=user, defaults={"name": f"{user.first_name or user.email}'s organization"}
    )
    return organization


def create_workspace(user, **fields) -> Workspace:
    workspace = Workspace.objects.create(organization=organization_for(user), **fields)
    Membership.objects.create(user=user, workspace=workspace, role=Membership.Role.OWNER)
    return workspace
