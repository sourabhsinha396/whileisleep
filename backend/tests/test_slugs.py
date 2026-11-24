"""Workspace slugs: the name a workspace has in dashboard URLs."""

import pytest

from apps.workspaces.models import Workspace, unique_slug

from .factories import WorkspaceFactory

pytestmark = pytest.mark.django_db


def test_a_new_workspace_gets_a_slug_from_its_name():
    assert WorkspaceFactory(name="BrightDesk").slug == "brightdesk"
    assert WorkspaceFactory(name="Little Fern Coffee!").slug == "little-fern-coffee"


def test_the_same_name_twice_gets_a_number():
    slugs = [WorkspaceFactory(name="Acme").slug for _ in range(3)]
    assert slugs == ["acme", "acme-2", "acme-3"]


@pytest.mark.parametrize("name", ["!!!", "日本語", "   "])
def test_names_with_nothing_usable_still_get_a_slug(name):
    assert WorkspaceFactory(name=name).slug.startswith("workspace")


def test_long_names_are_cut_to_fit():
    slug = WorkspaceFactory(name="word " * 23).slug
    assert len(slug) <= 60 and not slug.endswith("-")


def test_renaming_a_workspace_keeps_its_address():
    workspace = WorkspaceFactory(name="Acme")
    workspace.name = "Acme Corporation"
    workspace.save()
    assert Workspace.objects.get(pk=workspace.pk).slug == "acme"


def test_unique_slug_ignores_the_workspace_itself():
    workspace = WorkspaceFactory(name="Acme")
    assert unique_slug("Acme", exclude_pk=workspace.pk) == "acme"
    assert unique_slug("Acme") == "acme-2"


def test_the_api_returns_the_slug(api, workspace):
    assert api.get(f"/workspaces/{workspace.id}").json()["slug"] == workspace.slug
    assert api.get("/workspaces").json()[0]["slug"] == workspace.slug


def test_creating_through_the_api_makes_a_slug(api):
    created = api.post("/workspaces", {"name": "Second Shop", "website": ""}).json()
    assert created["slug"] == "second-shop"


def test_an_owner_can_change_the_slug(api, workspace):
    changed = api.patch(f"/workspaces/{workspace.id}", {"slug": "my-shop"})
    assert changed.status_code == 200 and changed.json()["slug"] == "my-shop"


def test_a_taken_slug_is_refused(api, workspace):
    WorkspaceFactory(name="Taken")
    response = api.patch(f"/workspaces/{workspace.id}", {"slug": "taken"})
    assert response.status_code == 400 and "taken" in response.json()["detail"]
    # Its own slug is not "taken".
    assert api.patch(f"/workspaces/{workspace.id}", {"slug": workspace.slug}).status_code == 200


@pytest.mark.parametrize("slug", ["My Shop", "shop_1", "-shop", "shop-", "a", "shop--one", "x" * 61, "../admin"])
def test_malformed_slugs_are_refused(api, workspace, slug):
    assert api.patch(f"/workspaces/{workspace.id}", {"slug": slug}).status_code == 422


def test_other_changes_leave_the_slug_alone(api, workspace):
    before = workspace.slug
    api.patch(f"/workspaces/{workspace.id}", {"name": "Renamed"})
    assert api.get(f"/workspaces/{workspace.id}").json()["slug"] == before
