"""Tests run on Postgres, the database production uses: search, JSON lookups and locking
behave differently on anything else. `docker compose up -d db` provides it locally (base.py
defaults to its address); CI starts a Postgres service. No .env and no network are needed.
"""

from .base import *  # noqa: F403

SECRET_KEY = "test-secret-key-not-for-production"
ALLOWED_HOSTS = ["testserver"]
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
# Tests swap in a fake LLM; conftest.py fails any real HTTP request.

# Whatever a developer's .env says, tests use no Redis: jobs run inside the call that
# queues them (and raise there), and the cache is this process's memory.
REDIS_URL = ""
CELERY_BROKER_URL = ""
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# Nor a real bucket: files stay in memory.
STORAGES["default"] = {"BACKEND": "django.core.files.storage.InMemoryStorage"}  # noqa: F405
