import pytest

from apps.agent import providers
from apps.workspaces.models import Membership, Organization, Provider

from .conftest import Api
from .factories import AuthTokenFactory, MembershipFactory, OrganizationFactory

pytestmark = pytest.mark.django_db

KEY = "sk-or-v1-abcdefgh1234"


def provider_row(organization: dict, provider: str) -> dict:
    return next(row for row in organization["providers"] if row["id"] == provider)


def test_signup_creates_an_organization(anon):
    anon.post("/auth/signup", {"name": "Ana", "email": "ana@example.com", "password": "longpassword"})
    assert Organization.objects.get().owner.email == "ana@example.com"


def test_new_workspaces_join_your_organization(api, membership):
    created = api.post("/workspaces", {"name": "Second site"}).json()
    assert Organization.objects.get(owner=membership.user).workspaces.filter(pk=created["id"]).exists()


# --- Keys ---


def test_every_provider_is_offered(api):
    rows = api.get("/organization").json()["providers"]
    assert [row["name"] for row in rows] == ["OpenAI", "Anthropic", "Google Gemini", "OpenRouter"]
    assert all(row["keys_url"].startswith("https://") and not row["has_key"] for row in rows)


def test_there_is_a_client_for_every_provider():
    assert set(providers.PROVIDERS) == set(Provider.values)
    assert all(providers.PROVIDERS[p.value].NAME == p.label for p in Provider)


def test_keys_are_write_only(api):
    saved = api.put("/organization/keys/openrouter", {"api_key": f" {KEY} "}).json()
    assert provider_row(saved, "openrouter")["has_key"] is True
    assert provider_row(saved, "openrouter")["key_hint"] == "…1234"
    assert "abcdefgh" not in str(api.get("/organization").json())


def test_each_provider_has_its_own_key(api, membership):
    api.put("/organization/keys/openrouter", {"api_key": KEY})
    saved = api.put("/organization/keys/anthropic", {"api_key": "sk-ant-abcdefgh5678"}).json()
    assert provider_row(saved, "openrouter")["key_hint"] == "…1234"
    assert provider_row(saved, "anthropic")["key_hint"] == "…5678"

    removed = api.delete("/organization/keys/openrouter").json()
    assert provider_row(removed, "openrouter")["has_key"] is False
    assert Organization.objects.get(owner=membership.user).provider_keys == {"anthropic": "sk-ant-abcdefgh5678"}


def test_saving_other_settings_keeps_the_keys(api, membership):
    api.put("/organization/keys/openrouter", {"api_key": KEY})
    api.patch("/organization", {"llm_model": "x/y", "name": "Renamed"})
    organization = Organization.objects.get(owner=membership.user)
    assert organization.provider_keys == {"openrouter": KEY} and organization.name == "Renamed"


@pytest.mark.parametrize("key", ["", "   ", "two words", "línea", "a\nb"])
def test_text_that_is_not_a_key_is_refused(api, membership, key):
    assert api.put("/organization/keys/openai", {"api_key": key}).status_code in (400, 422)
    assert Organization.objects.get(owner=membership.user).provider_keys == {}


@pytest.mark.parametrize("method", ["put", "post", "delete"])
def test_unknown_providers_are_refused(api, method):
    path = "/organization/keys/skynet" + ("/check" if method == "post" else "")
    arguments = () if method == "delete" else ({"api_key": KEY},)
    assert getattr(api, method)(path, *arguments).status_code == 422


def test_agents_edit_only_their_own_organization(workspace):
    """A teammate added to someone else's workspace can't touch that organization's keys."""
    agent = MembershipFactory(workspace=workspace, role=Membership.Role.AGENT)
    as_agent = Api(token=AuthTokenFactory(user=agent.user).key)
    as_agent.put("/organization/keys/openrouter", {"api_key": "sk-or-v1-hijacked0000"})
    workspace.organization.refresh_from_db()
    assert workspace.organization.provider_keys == {}
    assert as_agent.get(f"/workspaces/{workspace.id}").json()["is_organization_owner"] is False


def test_check_key(api, monkeypatch):
    nothing = {"ok": False, "message": "No key saved yet.", "label": "", "usage": None, "limit_remaining": None}
    assert api.post("/organization/keys/openrouter/check").json() == nothing
    api.put("/organization/keys/openrouter", {"api_key": KEY})
    info = {"label": "main", "usage": 1.5, "limit_remaining": 8.5}
    monkeypatch.setattr(providers.PROVIDERS["openrouter"], "check_key", lambda key: info if key == KEY else None)
    checked = api.post("/organization/keys/openrouter/check").json()
    assert checked["ok"] is True and checked["limit_remaining"] == 8.5


def test_check_key_reports_rejection(api, monkeypatch):
    api.put("/organization/keys/openai", {"api_key": KEY})

    def reject(key):
        raise providers.ProviderError("The OpenAI API key was rejected (no).", 401)

    monkeypatch.setattr(providers.PROVIDERS["openai"], "check_key", reject)
    checked = api.post("/organization/keys/openai/check").json()
    assert checked["ok"] is False and checked["message"] == "The OpenAI API key was rejected (no)."


# --- The model and its fallback ---


def test_ready_needs_a_model_and_that_providers_key(api, workspace):
    api.put("/organization/keys/anthropic", {"api_key": "sk-ant-abcdefgh5678"})
    assert api.patch("/organization", {"llm_provider": "openai", "llm_model": "gpt-x"}).json()["llm_ready"] is False
    assert api.patch("/organization", {"llm_provider": "anthropic"}).json()["llm_ready"] is True
    assert api.get(f"/workspaces/{workspace.id}").json()["llm_ready"] is True


def test_choose_a_fallback_and_remove_it(api):
    saved = api.patch(
        "/organization",
        {
            "llm_provider": "openai",
            "llm_model": "gpt-x",
            "fallback_provider": "anthropic",
            "fallback_model": "claude-y",
        },
    ).json()
    assert (saved["fallback_provider"], saved["fallback_model"]) == ("anthropic", "claude-y")
    removed = api.patch("/organization", {"fallback_provider": ""}).json()
    assert (removed["fallback_provider"], removed["fallback_model"]) == ("", "")
    assert removed["llm_model"] == "gpt-x"


def test_the_fallback_must_be_another_model(api, membership):
    api.patch("/organization", {"llm_provider": "openai", "llm_model": "gpt-x"})
    same = api.patch("/organization", {"fallback_provider": "openai", "fallback_model": "gpt-x"})
    assert same.status_code == 400 and "different model" in same.json()["detail"]
    assert Organization.objects.get(owner=membership.user).fallback_model == ""
    # Another model of the same provider is fine.
    assert api.patch("/organization", {"fallback_provider": "openai", "fallback_model": "gpt-y"}).status_code == 200


def test_unknown_provider_for_the_model_is_refused(api):
    assert api.patch("/organization", {"llm_provider": "skynet"}).status_code == 422
    assert api.patch("/organization", {"llm_provider": ""}).status_code == 422
    assert api.patch("/organization", {"fallback_provider": "skynet"}).status_code == 422


def test_choices_come_in_order_and_skip_what_is_incomplete():
    both = OrganizationFactory.build(with_fallback=True)
    assert [c.label for c in both.llm_choices] == ["OpenRouter test/model", "Anthropic claude-test"]
    assert [c.slug for c in both.llm_choices] == ["test/model", "anthropic/claude-test"]
    assert "sk-ant" not in repr(both.llm_choices)

    keyless = OrganizationFactory.build(with_fallback=True, provider_keys={"anthropic": "k"})
    assert [c.provider for c in keyless.llm_choices] == ["anthropic"] and keyless.llm_ready
    assert not OrganizationFactory.build(provider_keys={"openrouter": "k"}).llm_ready


# --- The model picker ---


def test_models_are_cached_until_the_key_changes(api, monkeypatch):
    keys = []
    rows = [{"id": "gpt-x", "name": "GPT X"}]
    monkeypatch.setattr(providers.PROVIDERS["openai"], "list_models", lambda key: keys.append(key) or rows)
    api.put("/organization/keys/openai", {"api_key": "sk-first"})
    assert api.get("/organization/models/openai").json() == rows
    api.get("/organization/models/openai")
    api.put("/organization/keys/openai", {"api_key": "sk-second"})
    api.get("/organization/models/openai")
    assert keys == ["sk-first", "sk-second"]


def test_models_of_one_account_are_not_shown_to_another(api, monkeypatch):
    monkeypatch.setattr(providers.PROVIDERS["openai"], "list_models", lambda key: [{"id": key, "name": key}])
    api.put("/organization/keys/openai", {"api_key": "sk-mine"})
    api.get("/organization/models/openai")
    other = Api(token=AuthTokenFactory().key)
    other.put("/organization/keys/openai", {"api_key": "sk-theirs"})
    assert other.get("/organization/models/openai").json() == [{"id": "sk-theirs", "name": "sk-theirs"}]


def test_only_openrouter_lists_models_without_a_key(api, monkeypatch):
    monkeypatch.setattr(providers.PROVIDERS["openrouter"], "list_models", lambda key: [{"id": "x/y", "name": "Y"}])
    assert api.get("/organization/models/openrouter").status_code == 200
    refused = api.get("/organization/models/anthropic")
    assert refused.status_code == 400 and "Anthropic key" in refused.json()["detail"]


def test_a_provider_that_cannot_list_models_is_reported(api, monkeypatch):
    def down(key):
        raise providers.ProviderError("Could not reach OpenRouter: ConnectError")

    monkeypatch.setattr(providers.PROVIDERS["openrouter"], "list_models", down)
    failed = api.get("/organization/models/openrouter")
    assert failed.status_code == 502 and "Could not reach" in failed.json()["detail"]
