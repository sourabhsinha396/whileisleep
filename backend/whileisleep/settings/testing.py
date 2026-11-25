"""Tests run on Postgres, the database production uses: search, JSON lookups and locking
behave differently on anything else. `docker compose up -d db` provides it locally (base.py
defaults to its address); CI starts a Postgres service. No .env and no network are needed.
"""

import re

from .base import *  # noqa: F403

SECRET_KEY = "test-secret-key-not-for-production"
# Named after the folder, so tests in two checkouts don't delete each other's database.
checkout = re.sub(r"\W+", "_", BASE_DIR.resolve().parent.name.lower())[:40]  # noqa: F405
DATABASES["default"]["TEST"] = {"NAME": f"test_{checkout}"}  # noqa: F405
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

# Nor real payments; the `billing` fixture turns them on, against a fake Dodo.
BILLING_ENABLED = False
PAYMENT_PROVIDER = DODO_BASE_URL = DODO_API_KEY = ""
DODO_PRODUCT_MONTHLY = DODO_PRODUCT_YEARLY = DODO_WEBHOOK_KEY = ""

# Nor reCAPTCHA; test_captcha.py turns it on, against a fake Google.
RECAPTCHA_ENABLED = False
RECAPTCHA_SITE_KEY = RECAPTCHA_SECRET_KEY = ""

# Nor Google; test_google.py turns it on, against a fake one.
GOOGLE_ENABLED = False
GOOGLE_CLIENT_ID = GOOGLE_CLIENT_SECRET = ""

# Nor emails; test_passwords.py turns them on, against a fake Brevo.
MAIL_ENABLED = False
BREVO_API_KEY = MAIL_FROM = ""

# Nor other plugins than ours, which are not set up; tests do that.
PLUGINS = ["plugins.slack", "plugins.webhooks"]
PLUGIN_OPTIONS = {}

# Nor a real bucket: files stay in memory.
STORAGES["default"] = {  # noqa: F405
    "BACKEND": "django.core.files.storage.InMemoryStorage",
    "OPTIONS": {"base_url": "https://cdn.example.com/"},
}
UPLOADS_ENABLED = True
