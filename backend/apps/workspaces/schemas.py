from typing import Literal

from ninja import Schema
from pydantic import EmailStr, Field

from .models import Provider


class WorkspaceIn(Schema):
    name: str = Field(min_length=1, max_length=120)
    website: str = ""


class WorkspacePatch(Schema):
    name: str | None = Field(None, min_length=1, max_length=120)
    # The name in dashboard URLs (/w/<slug>/inbox). Changing it breaks bookmarks of the old one.
    slug: str | None = Field(None, min_length=2, max_length=60, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    website: str | None = None
    color: str | None = Field(None, max_length=16)
    greeting: str | None = Field(None, max_length=300)
    timezone: str | None = Field(None, max_length=64)
    ai_enabled: bool | None = None
    ai_instructions: str | None = None


class WorkspaceOut(Schema):
    id: int
    name: str
    slug: str
    public_key: str
    website: str
    color: str
    logo_url: str
    greeting: str
    timezone: str
    ai_enabled: bool
    ai_instructions: str
    role: str = ""
    open_count: int = 0
    # The organization has a model and its provider's key, so the AI agent can use an LLM.
    llm_ready: bool = False
    is_organization_owner: bool = False
    # Whether this server can store images at all.
    uploads_enabled: bool = False
    # Where the organization stands: "off" (no billing here), "trial", "active" or "paused".
    billing_state: str = "off"
    trial_days_left: int | None = None
    # Whether articles can have images: the organization connected its own bucket for them.
    article_uploads_enabled: bool = False


class SetupStepOut(Schema):
    key: str
    done: bool


class IdentitySecretOut(Schema):
    secret: str


class MemberIn(Schema):
    email: EmailStr
    role: str = "agent"


class MemberOut(Schema):
    user_id: int
    name: str
    email: str
    role: str
    photo_url: str


class ProviderOut(Schema):
    id: str
    name: str
    # Where its keys are made.
    keys_url: str
    has_key: bool
    key_hint: str


class OrganizationOut(Schema):
    id: int
    name: str
    providers: list[ProviderOut]
    llm_provider: str
    llm_model: str
    # "" when there is no fallback.
    fallback_provider: str
    fallback_model: str
    llm_ready: bool
    workspace_count: int


class OrganizationPatch(Schema):
    name: str | None = Field(None, min_length=1, max_length=120)
    llm_provider: Provider | None = None
    llm_model: str | None = Field(None, max_length=200)
    # "" removes the fallback.
    fallback_provider: Provider | Literal[""] | None = None
    fallback_model: str | None = Field(None, max_length=200)


class ProviderKeyIn(Schema):
    # Write-only.
    api_key: str = Field(min_length=1, max_length=400)


class ModelOut(Schema):
    id: str
    name: str


class StorageIn(Schema):
    endpoint_url: str = Field(max_length=300)
    region: str = Field("", max_length=40)
    bucket: str = Field(max_length=63)
    # Write-only. Both empty keeps the saved key.
    access_key_id: str = Field("", max_length=300)
    secret_access_key: str = Field("", max_length=300)
    public_base_url: str = Field(max_length=300)


class StorageOut(Schema):
    connected: bool
    endpoint_url: str = ""
    region: str = ""
    bucket: str = ""
    key_hint: str = ""
    public_base_url: str = ""
    image_count: int = 0


class KeyCheckOut(Schema):
    ok: bool
    message: str
    label: str = ""
    usage: float | None = None
    limit_remaining: float | None = None
