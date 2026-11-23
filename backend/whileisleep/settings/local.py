"""Local development, in Docker or on the host. Requires a valid backend/.env."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from whileisleep.env import EnvError, validate_env_file

ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"
if not ENV_FILE.exists():
    raise ImproperlyConfigured(f"{ENV_FILE} is missing. Copy .env.example to .env and fill it in.")
try:
    validate_env_file(ENV_FILE)
except EnvError as error:
    raise ImproperlyConfigured(str(error)) from None

from .base import *  # noqa: E402, F403

DEBUG = True
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or "dev-secret-key-not-for-production"
ALLOWED_HOSTS = ["*"]
# In development the tools you try are usually on this machine (host.docker.internal).
OUTBOUND_ALLOW_PRIVATE_NETWORKS = True
# The Next.js dev server proxies /api to Django.
TRUSTED_PROXY_COUNT = 1
