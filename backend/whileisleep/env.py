"""Validates backend/.env with pydantic before Django starts.

Every key must be declared here: a typo or a leftover key (an old ANTHROPIC_API_KEY, say)
stops startup instead of being silently ignored, and required keys must be present and
non-empty. Empty optional values count as unset.
"""

from pathlib import Path

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
    # Only `manage.py seed_demo` reads these. The running app takes each organization's
    # OpenRouter key from its settings page, never from here.
    # Plain pattern: reserved test domains (demo@whileisleep.test) are fine here.
    DEMO_EMAIL: str | None = Field(None, pattern=r"^[^@\s]+@[^@\s]+$")
    DEMO_PASSWORD: str | None = None
    OPENROUTER_API_KEY: str | None = None
    EXAMGRILL_API_URL: str | None = None

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
    raw = {key: value for key, value in dotenv_values(path).items() if key}
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
