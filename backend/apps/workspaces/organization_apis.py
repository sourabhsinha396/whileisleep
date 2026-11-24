"""The signed-in user's organization: its name and the LLM settings (provider keys, the model
that answers, and the one that takes over when it fails).

Only the owner reaches these. Keys are write-only: responses say whether one is set and show
its last characters, never the key.
"""

import re

from django.core.cache import cache
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.security import token_auth
from apps.agent import providers

from .models import Organization, Provider
from .schemas import KeyCheckOut, ModelOut, OrganizationOut, OrganizationPatch, ProviderKeyIn
from .services import organization_for

router = Router(tags=["organization"], auth=token_auth)
MODELS_CACHE_SECONDS = 3600


def organization_out(organization: Organization) -> dict:
    return {
        "id": organization.id,
        "name": organization.name,
        "providers": [
            {
                "id": provider.value,
                "name": provider.label,
                "keys_url": providers.PROVIDERS[provider].KEYS_URL,
                "has_key": bool(organization.provider_keys.get(provider)),
                "key_hint": organization.key_hint(provider),
            }
            for provider in Provider
        ],
        "llm_provider": organization.llm_provider,
        "llm_model": organization.llm_model,
        "fallback_provider": organization.fallback_provider,
        "fallback_model": organization.fallback_model,
        "ai_replies_per_day": organization.ai_replies_per_day,
        "llm_ready": organization.llm_ready,
        "workspace_count": organization.workspaces.count(),
    }


def models_cache_key(organization: Organization, provider: Provider) -> str:
    # What a key can use differs between accounts, except on OpenRouter.
    owner = "all" if provider == Provider.OPENROUTER else organization.id
    return f"llm-models:{provider.value}:{owner}"


@router.get("/organization", response=OrganizationOut)
def get(request):
    return organization_out(organization_for(request.auth))


@router.patch("/organization", response=OrganizationOut)
def update(request, payload: OrganizationPatch):
    organization = organization_for(request.auth)
    sent = payload.dict(exclude_unset=True)
    changes = {k: v.strip() for k, v in sent.items() if isinstance(v, str)}
    if "ai_replies_per_day" in sent:
        changes["ai_replies_per_day"] = sent["ai_replies_per_day"]
    for field, value in changes.items():
        setattr(organization, field, value)
    if not organization.fallback_provider:
        organization.fallback_model = ""
    main = (organization.llm_provider, organization.llm_model)
    if organization.fallback_model and (organization.fallback_provider, organization.fallback_model) == main:
        raise HttpError(400, "Pick a different model for the fallback: this one is already the main model.")
    # Not the keys: they are saved on their own, perhaps at this very moment.
    organization.save(update_fields=[*changes, "fallback_model"])
    return organization_out(organization)


@router.put("/organization/keys/{provider}", response=OrganizationOut)
def save_key(request, provider: Provider, payload: ProviderKeyIn):
    key = payload.api_key.strip()
    if not re.fullmatch(r"[!-~]+", key):
        # Every call sends it in an HTTP header, where a space or an accent can't go.
        raise HttpError(400, "That doesn't look like an API key.")
    organization = organization_for(request.auth)
    organization.provider_keys[provider.value] = key
    return keys_changed(organization, provider)


@router.delete("/organization/keys/{provider}", response=OrganizationOut)
def remove_key(request, provider: Provider):
    organization = organization_for(request.auth)
    organization.provider_keys.pop(provider.value, None)
    return keys_changed(organization, provider)


def keys_changed(organization: Organization, provider: Provider) -> dict:
    organization.save(update_fields=["provider_keys"])
    cache.delete(models_cache_key(organization, provider))
    return organization_out(organization)


@router.post("/organization/keys/{provider}/check", response=KeyCheckOut)
def check_key(request, provider: Provider):
    """Asks the provider whether the saved key works."""
    key = organization_for(request.auth).provider_keys.get(provider)
    if not key:
        return {"ok": False, "message": "No key saved yet."}
    try:
        info = providers.PROVIDERS[provider].check_key(key)
    except providers.ProviderError as error:
        return {"ok": False, "message": str(error)}
    return {"ok": True, "message": "The key works.", **info}


@router.get("/organization/models/{provider}", response=list[ModelOut])
def models(request, provider: Provider):
    """A provider's models for the picker, cached for an hour."""
    organization = organization_for(request.auth)
    key = organization.provider_keys.get(provider, "")
    if not key and provider != Provider.OPENROUTER:
        raise HttpError(400, f"Add your {provider.label} key to see its models.")
    cache_key = models_cache_key(organization, provider)
    rows = cache.get(cache_key)
    if rows is None:
        try:
            rows = providers.PROVIDERS[provider].list_models(key)
        except providers.ProviderError as error:
            raise HttpError(502, str(error)) from error
        cache.set(cache_key, rows, MODELS_CACHE_SECONDS)
    return rows
