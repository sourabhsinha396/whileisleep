"""A workspace's logo: owners upload it, the widget shows it."""

import re

import pytest
from django.core.files.storage import default_storage

from apps.workspaces.models import Membership

from .conftest import Api
from .factories import AuthTokenFactory, MembershipFactory, WorkspaceFactory
from .test_images import picture

pytestmark = pytest.mark.django_db


def logos(workspace) -> list[str]:
    try:
        return default_storage.listdir(f"workspaces/{workspace.id}/logo")[1]
    except FileNotFoundError:
        return []


def test_owner_uploads_a_logo_and_the_widget_gets_it(api, anon, workspace):
    response = api.upload(f"/workspaces/{workspace.id}/logo", picture(size=(400, 300)))
    assert response.status_code == 200
    url = response.json()["logo_url"]
    assert re.fullmatch(rf"https://cdn\.example\.com/workspaces/{workspace.id}/logo/[0-9a-f]{{32}}\.png", url)
    assert api.get(f"/workspaces/{workspace.id}").json()["logo_url"] == url
    assert api.get("/workspaces").json()[0]["logo_url"] == url
    assert anon.get(f"/widget/{workspace.public_key}/config").json()["logo_url"] == url


def test_no_logo_is_an_empty_address(api, anon, workspace):
    assert api.get(f"/workspaces/{workspace.id}").json()["logo_url"] == ""
    assert anon.get(f"/widget/{workspace.public_key}/config").json()["logo_url"] == ""


def test_a_new_logo_replaces_the_old_file(api, workspace):
    first = api.upload(f"/workspaces/{workspace.id}/logo", picture()).json()["logo_url"]
    second = api.upload(f"/workspaces/{workspace.id}/logo", picture("JPEG")).json()["logo_url"]
    assert first != second
    assert logos(workspace) == [second.rsplit("/", 1)[1]]


def test_a_refused_image_keeps_the_old_logo(api, workspace):
    url = api.upload(f"/workspaces/{workspace.id}/logo", picture()).json()["logo_url"]
    response = api.upload(f"/workspaces/{workspace.id}/logo", picture("GIF"))
    assert response.status_code == 400 and "PNG, JPEG or WebP" in response.json()["detail"]
    assert api.get(f"/workspaces/{workspace.id}").json()["logo_url"] == url
    assert len(logos(workspace)) == 1


def test_removing_the_logo_deletes_the_file(api, workspace):
    api.upload(f"/workspaces/{workspace.id}/logo", picture())
    assert api.delete(f"/workspaces/{workspace.id}/logo").json()["logo_url"] == ""
    assert logos(workspace) == []
    assert api.delete(f"/workspaces/{workspace.id}/logo").status_code == 200


def test_saving_other_settings_keeps_the_logo(api, workspace):
    url = api.upload(f"/workspaces/{workspace.id}/logo", picture()).json()["logo_url"]
    assert api.patch(f"/workspaces/{workspace.id}", {"greeting": "Hey"}).json()["logo_url"] == url


def test_only_owners_of_this_workspace_may_change_it(workspace):
    agent = MembershipFactory(workspace=workspace, role=Membership.Role.AGENT).user
    stranger = MembershipFactory(workspace=WorkspaceFactory()).user
    path = f"/workspaces/{workspace.id}/logo"
    for user in (agent, stranger):
        api = Api(token=AuthTokenFactory(user=user).key)
        assert api.upload(path, picture()).status_code == 404
        assert api.delete(path).status_code == 404
    assert Api().upload(path, picture()).status_code == 401
    assert logos(workspace) == []


def test_each_workspace_has_its_own_folder(api, workspace, membership):
    other = MembershipFactory(user=membership.user).workspace
    for each in (workspace, other):
        assert f"/workspaces/{each.id}/logo/" in api.upload(f"/workspaces/{each.id}/logo", picture()).json()["logo_url"]


def test_without_a_bucket_uploads_are_off(api, workspace, settings):
    assert api.get(f"/workspaces/{workspace.id}").json()["uploads_enabled"] is True
    settings.UPLOADS_ENABLED = False
    assert api.get(f"/workspaces/{workspace.id}").json()["uploads_enabled"] is False
    response = api.upload(f"/workspaces/{workspace.id}/logo", picture())
    assert response.status_code == 503 and "storage" in response.json()["detail"]
