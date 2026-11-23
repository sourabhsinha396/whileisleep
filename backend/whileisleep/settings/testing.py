"""Tests run on Postgres, the database production uses: search, JSON lookups and locking
behave differently on anything else. `docker compose up -d db` provides it locally (base.py
defaults to its address); CI starts a Postgres service. No .env and no network are needed.
"""

from .base import *  # noqa: F403

SECRET_KEY = "test-secret-key-not-for-production"
ALLOWED_HOSTS = ["testserver"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
# Tests swap in a fake LLM; conftest.py fails any real HTTP request.
BOT_SYNC = True
