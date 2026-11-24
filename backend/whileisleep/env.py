"""Validates backend/.env with pydantic before Django starts.

Every key must be declared here: a typo or a leftover key (an old ANTHROPIC_API_KEY, say)
stops startup instead of being silently ignored, and required keys must be present and
non-empty. Empty optional values count as unset.
"""

from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class EnvFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    # Required
    DJANGO_SETTINGS_MODULE: str = Field(min_length=1)
    POSTGRES_DB: str = Field(min_length=1)
    POSTGRES_USER: str = Field(min_length=1)
    POSTGRES_PASSWORD: str = Field(min_length=1)
    POSTGRES_HOST: str = Field(min_length=1)
    POSTGRES_PORT: int = Field(gt=0, lt=65536)

    # Optional
    WEB_PORT: int = Field(8004, gt=0, lt=65536)
    DJANGO_SECRET_KEY: str | None = None
    DJANGO_DEBUG: bool | None = None
    ALLOWED_HOSTS: str | None = None
    # Comma-separated Fernet keys for stored secrets; see whileisleep/encryption.py.
    ENCRYPTION_KEYS: str | None = None
    # Redis for the cache and the job queue (redis://...). Unset: counters stay in this
    # process's memory and AI replies run inside the web request, fine for one process.
    REDIS_URL: str | None = None
    # Only to put the job queue on a different server than the cache.
    CELERY_BROKER_URL: str | None = None
    # Where uploaded files go (whileisleep/storage.py): set all five, or none.
    S3_ENDPOINT_URL: str | None = Field(None, pattern=r"^https?://")
    S3_ACCESS_KEY_ID: str | None = None
    S3_SECRET_ACCESS_KEY: str | None = None
    STORAGE_BUCKET: str | None = None
    STORAGE_PUBLIC_BASE_URL: str | None = Field(None, pattern=r"^https?://")
    # The provider's region; "auto" (Cloudflare R2) when unset.
    S3_REGION: str | None = None
    # Selling the hosted plan (apps.billing). Leave all of it out on your own server: billing
    # is off and everything is free. The last three come from `manage.py billing_setup`.
    PAYMENT_PROVIDER: Literal["dodo"] | None = None
    DODO_BASE_URL: str | None = Field(None, pattern=r"^https://")
    DODO_API_KEY: str | None = None
    DODO_PRODUCT_MONTHLY: str | None = Field(None, pattern=r"^pdt_")
    DODO_PRODUCT_YEARLY: str | None = Field(None, pattern=r"^pdt_")
    DODO_WEBHOOK_KEY: str | None = Field(None, pattern=r"^whsec_")
    # Plugins besides ours (apps.integrations): importable modules, comma-separated. What a plugin
    # needs is in PLUGIN_<ID>_<NAME> keys, which only the plugin knows; `manage.py check` names
    # the ones that no plugin here has.
    EXTRA_PLUGINS: str | None = None
    # "false" closes account creation.
    SIGNUP_ENABLED: bool | None = None
    # Only `manage.py seed_demo` reads these. The running app takes each organization's
    # AI provider keys from its settings page, never from here.
    # Plain pattern: reserved test domains (demo@whileisleep.test) are fine here.
    DEMO_EMAIL: str | None = Field(None, pattern=r"^[^@\s]+@[^@\s]+$")
    DEMO_PASSWORD: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def empty_is_unset(cls, value):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value


class EnvError(Exception):
    pass


def validate_env_file(path: Path) -> EnvFile:
    """Parse and check a .env file. Raises EnvError listing every problem."""
    raw = {key: value for key, value in dotenv_values(path).items() if key and not key.startswith("PLUGIN_")}
    try:
        return EnvFile(**raw)
    except ValidationError as error:
        lines = []
        for problem in error.errors():
            key = ".".join(str(part) for part in problem["loc"]) or "(file)"
            if problem["type"] == "extra_forbidden":
                lines.append(f"  {key}: not a known setting (remove it, or declare it in whileisleep/env.py)")
            elif problem["type"] == "missing" or not (raw.get(key) or "").strip():
                # Absent, or present but empty.
                lines.append(f"  {key}: required")
            else:
                lines.append(f"  {key}: {problem['msg']}")
        raise EnvError(f"{path} is invalid:\n" + "\n".join(lines)) from None
