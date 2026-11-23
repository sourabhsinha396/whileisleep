"""Tests run on in-memory SQLite: no Docker, no .env, no network."""

from .base import *  # noqa: F403

SECRET_KEY = "test-secret-key-not-for-production"
ALLOWED_HOSTS = ["testserver"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
# Tests swap in a fake LLM; conftest.py fails any real HTTP request.
BOT_SYNC = True
