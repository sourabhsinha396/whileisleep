from decimal import Decimal

import httpx
import pytest

from apps.agent import openrouter
from apps.workspaces.models import Membership, Organization

from .conftest import Api
from .factories import AuthTokenFactory, MembershipFactory, OrganizationFactory

pytestmark = pytest.mark.django_db


def test_signup_creates_an_organization(anon):
    anon.post("/auth/signup", {"name": "Ana", "email": "ana@example.com", "password": "longpassword"})
    assert Organization.objects.get().owner.email == "ana@example.com"


def test_new_workspaces_join_your_organization(api, membership):
    created = api.post("/workspaces", {"name": "Second site"}).json()
    assert Organization.objects.get(owner=membership.user).workspaces.filter(pk=created["id"]).exists()


def test_key_is_write_only(api, workspace):
    saved = api.patch("/organization", {"openrouter_api_key": "sk-or-v1-abcdefgh1234", "llm_model": "x/y"}).json()
    assert saved["has_openrouter_key"] is True
    assert saved["key_hint"] == "…1234"
    assert "abcdefgh" not in str(api.get("/organization").json())
    assert saved["llm_ready"] is True
    assert api.get(f"/workspaces/{workspace.id}").json()["llm_ready"] is True


def test_leaving_key_out_keeps_it_and_empty_clears_it(api, membership):
    api.patch("/organization", {"openrouter_api_key": "sk-or-v1-abcdefgh1234"})
    api.patch("/organization", {"llm_model": "x/y"})
    assert Organization.objects.get(owner=membership.user).openrouter_api_key == "sk-or-v1-abcdefgh1234"
    api.patch("/organization", {"openrouter_api_key": ""})
    assert Organization.objects.get(owner=membership.user).openrouter_api_key == ""


def test_agents_edit_only_their_own_organization(workspace):
    """A teammate added to someone else's workspace can't touch that organization's key."""
    agent = MembershipFactory(workspace=workspace, role=Membership.Role.AGENT)
    as_agent = Api(token=AuthTokenFactory(user=agent.user).key)
    as_agent.patch("/organization", {"openrouter_api_key": "sk-or-v1-hijacked0000"})
    assert workspace.organization.openrouter_api_key == ""
    assert as_agent.get(f"/workspaces/{workspace.id}").json()["is_organization_owner"] is False


def test_check_key(api, membership, monkeypatch):
    assert api.post("/organization/check-key").json() == {
        "ok": False,
        "message": "No key saved yet.",
        "label": "",
        "usage": None,
        "limit_remaining": None,
    }
    api.patch("/organization", {"openrouter_api_key": "sk-or-v1-abcdefgh1234"})
    monkeypatch.setattr(
        openrouter,
        "key_info",
        lambda key: {"label": "main", "usage": 1.5, "limit_remaining": 8.5, "is_free_tier": False},
    )
    checked = api.post("/organization/check-key").json()
    assert checked["ok"] is True and checked["limit_remaining"] == 8.5


def test_check_key_reports_rejection(api, monkeypatch):
    api.patch("/organization", {"openrouter_api_key": "sk-or-v1-abcdefgh1234"})

    def reject(key):
        raise openrouter.OpenRouterError("The OpenRouter API key was rejected (User not found).", 401)

    monkeypatch.setattr(openrouter, "key_info", reject)
    checked = api.post("/organization/check-key").json()
    assert checked == {**checked, "ok": False, "message": "The OpenRouter API key was rejected (User not found)."}


# --- OpenRouter client ---


class FakeHttp:
    def __init__(self, status=200, json=None):
        self.status, self.json, self.calls = status, json, []

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        return httpx.Response(self.status, json=self.json, request=httpx.Request(method, url))


def test_complete_sends_tools_and_returns_the_message(monkeypatch):
    http = FakeHttp(json={"choices": [{"message": {"role": "assistant", "content": "hi"}}]})
    monkeypatch.setattr(openrouter.httpx, "request", http)
    completion = openrouter.complete("sk-or-x", "m/1", [{"role": "user", "content": "hi"}], [{"type": "function"}])
    call = http.calls[0]
    assert call["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert call["headers"]["Authorization"] == "Bearer sk-or-x"
    assert call["json"]["model"] == "m/1" and call["json"]["tools"] == [{"type": "function"}]
    assert completion.message == {"role": "assistant", "content": "hi"}
    # No usage in the response: counted as nothing rather than failing.
    assert (completion.input_tokens, completion.cached_tokens, completion.output_tokens) == (0, 0, 0)
    assert completion.cost is None


def test_complete_reports_tokens_and_cost(monkeypatch):
    usage = {
        "prompt_tokens": 1200,
        "completion_tokens": 80,
        "prompt_tokens_details": {"cached_tokens": 1000},
        "cost": 0.00042,
    }
    http = FakeHttp(json={"choices": [{"message": {"role": "assistant", "content": "hi"}}], "usage": usage})
    monkeypatch.setattr(openrouter.httpx, "request", http)
    completion = openrouter.complete("k", "m", [], [])
    assert (completion.input_tokens, completion.cached_tokens, completion.output_tokens) == (1200, 1000, 80)
    assert completion.cost == Decimal("0.00042")


@pytest.mark.parametrize(
    "usage",
    [None, "lots", {"prompt_tokens": "many"}, {"prompt_tokens": -5}, {"prompt_tokens_details": 7}, {"cost": "free"}],
)
def test_odd_usage_shapes_do_not_break_a_reply(monkeypatch, usage):
    http = FakeHttp(json={"choices": [{"message": {"role": "assistant", "content": "hi"}}], "usage": usage})
    monkeypatch.setattr(openrouter.httpx, "request", http)
    completion = openrouter.complete("k", "m", [], [])
    assert completion.input_tokens == 0 and completion.cost is None


@pytest.mark.parametrize(
    ("status", "expected"),
    [(401, "API key was rejected"), (402, "credits or key limit"), (500, "boom")],
)
def test_complete_errors_are_readable(monkeypatch, status, expected):
    monkeypatch.setattr(openrouter.httpx, "request", FakeHttp(status, {"error": {"code": status, "message": "boom"}}))
    with pytest.raises(openrouter.OpenRouterError, match=expected):
        openrouter.complete("k", "m", [], [])


def test_list_models_skips_models_without_tools(monkeypatch):
    rows = [
        {"id": "b/with-tools", "name": "B", "supported_parameters": ["tools", "temperature"]},
        {"id": "a/no-tools", "name": "A", "supported_parameters": ["temperature"]},
        {"id": "c/unknown", "display_name": "C"},
    ]
    monkeypatch.setattr(openrouter.httpx, "request", FakeHttp(json={"data": rows}))
    assert openrouter.list_models() == [{"id": "b/with-tools", "name": "B"}, {"id": "c/unknown", "name": "C"}]


def test_models_endpoint_is_cached(api, monkeypatch):
    calls = []
    monkeypatch.setattr(openrouter, "list_models", lambda key="": calls.append(1) or [{"id": "x/y", "name": "Y"}])
    assert api.get("/organization/models").json() == [{"id": "x/y", "name": "Y"}]
    api.get("/organization/models")
    assert calls == [1]


def test_ready_needs_key_and_model():
    assert not OrganizationFactory.build(openrouter_api_key="k").llm_ready
    assert OrganizationFactory.build(ready=True).llm_ready
