"""The signed-in user's organization: its name and the LLM (OpenRouter) settings.

Only the owner reaches these. The OpenRouter key is write-only: responses say whether
it is set and show its last characters, never the key.
"""

from django.core.cache import cache
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.security import token_auth
from apps.agent import openrouter

from .models import Organization
from .schemas import KeyCheckOut, ModelOut, OrganizationOut, OrganizationPatch
from .services import organization_for

router = Router(tags=["organization"], auth=token_auth)
MODELS_CACHE_SECONDS = 3600


def organization_out(organization: Organization) -> dict:
    return {
        "id": organization.id,
        "name": organization.name,
        "has_openrouter_key": bool(organization.openrouter_api_key),
        "key_hint": organization.key_hint,
        "llm_model": organization.llm_model,
        "llm_ready": organization.llm_ready,
        "workspace_count": organization.workspaces.count(),
    }


@router.get("/organization", response=OrganizationOut)
def get(request):
    return organization_out(organization_for(request.auth))


@router.patch("/organization", response=OrganizationOut)
def update(request, payload: OrganizationPatch):
    organization = organization_for(request.auth)
    data = payload.dict(exclude_unset=True)
    for field in ("name", "openrouter_api_key", "llm_model"):
        if field in data and data[field] is not None:
            setattr(organization, field, data[field].strip())
    organization.save()
    return organization_out(organization)


@router.post("/organization/check-key", response=KeyCheckOut)
def check_key(request):
    """Asks OpenRouter whether the saved key works."""
    organization = organization_for(request.auth)
    if not organization.openrouter_api_key:
        return {"ok": False, "message": "No key saved yet."}
    try:
        info = openrouter.key_info(organization.openrouter_api_key)
    except openrouter.OpenRouterError as error:
        return {"ok": False, "message": str(error)}
    return {"ok": True, "message": "The key works.", **{k: info[k] for k in ("label", "usage", "limit_remaining")}}


@router.get("/organization/models", response=list[ModelOut])
def models(request):
    """OpenRouter models for the picker, cached for an hour."""
    rows = cache.get("openrouter:models")
    if rows is None:
        try:
            rows = openrouter.list_models(organization_for(request.auth).openrouter_api_key)
        except openrouter.OpenRouterError as error:
            raise HttpError(502, str(error)) from error
        cache.set("openrouter:models", rows, MODELS_CACHE_SECONDS)
    return rows
