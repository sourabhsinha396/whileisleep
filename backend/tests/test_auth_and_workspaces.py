import pytest

from apps.workspaces.models import Membership

from .conftest import Api
from .factories import AuthTokenFactory, MembershipFactory, UserFactory, WorkspaceFactory

pytestmark = pytest.mark.django_db


def test_signup_then_login(anon):
    created = anon.post("/auth/signup", {"name": "Ana", "email": "Ana@Example.com", "password": "longpassword"})
    assert created.status_code == 200
    assert created.json()["user"]["email"] == "ana@example.com"

    logged_in = anon.post("/auth/login", {"email": "ana@example.com", "password": "longpassword"})
    assert logged_in.status_code == 200
    me = Api(token=logged_in.json()["token"]).get("/auth/me")
    assert me.json()["name"] == "Ana"


def test_login_with_wrong_password(anon):
    UserFactory(email="bo@example.com")
    assert anon.post("/auth/login", {"email": "bo@example.com", "password": "nope"}).status_code == 401


def test_logout_revokes_the_token(api):
    api.post("/auth/logout")
    assert api.get("/auth/me").status_code == 401


def test_create_workspace_makes_you_owner(api):
    created = api.post("/workspaces", {"name": "Second site", "website": "https://two.example.com"})
    assert created.status_code == 200
    body = created.json()
    assert body["role"] == "owner"
    assert body["public_key"].startswith("ws_")
    assert {w["name"] for w in api.get("/workspaces").json()} >= {"Second site"}


def test_workspaces_are_private(api):
    other = WorkspaceFactory()
    assert api.get(f"/workspaces/{other.id}").status_code == 404
    assert api.get(f"/workspaces/{other.id}/conversations").status_code == 404


def test_agents_cannot_change_settings(workspace):
    agent = MembershipFactory(workspace=workspace, role=Membership.Role.AGENT)
    as_agent = Api(token=AuthTokenFactory(user=agent.user).key)
    assert as_agent.get(f"/workspaces/{workspace.id}").status_code == 200
    assert as_agent.patch(f"/workspaces/{workspace.id}", {"name": "Hijacked"}).status_code == 404


def test_owner_updates_settings(api, workspace):
    updated = api.patch(f"/workspaces/{workspace.id}", {"greeting": "Hey there", "ai_enabled": False})
    assert updated.json()["greeting"] == "Hey there"
    assert updated.json()["ai_enabled"] is False


def test_add_member_by_email(api, workspace):
    UserFactory(email="teammate@example.com")
    added = api.post(f"/workspaces/{workspace.id}/members", {"email": "teammate@example.com", "role": "agent"})
    assert added.status_code == 200
    assert len(api.get(f"/workspaces/{workspace.id}/members").json()) == 2
