"""Shared settings. `local` (Docker dev) and `testing` build on this."""

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from corsheaders.defaults import default_headers
from dotenv import load_dotenv

from whileisleep.storage import default_storage_config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Host runs read .env; in Docker, compose already set these (and they win).
load_dotenv(BASE_DIR / ".env", override=False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = os.environ.get("DJANGO_DEBUG", "").lower() == "true"
ALLOWED_HOSTS = [h for h in os.environ.get("ALLOWED_HOSTS", "").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "corsheaders",
    "apps.accounts",
    "apps.workspaces",
    "apps.conversations",
    "apps.knowledge",
    "apps.agent",
    "apps.realtime",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "whileisleep.urls"
WSGI_APPLICATION = "whileisleep.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "whileisleep"),
        "USER": os.environ.get("POSTGRES_USER", "whileisleep"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "whileisleep"),
        "HOST": os.environ.get("POSTGRES_HOST", "127.0.0.1"),
        "PORT": os.environ.get("POSTGRES_PORT", "5448"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STORAGES = {
    # Uploaded files: the S3 bucket, if one is configured.
    "default": default_storage_config(os.environ),
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
# Logos and photos need a bucket: nothing serves files from the local disk.
UPLOADS_ENABLED = "OPTIONS" in STORAGES["default"]
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The dashboard and the widget both send bearer tokens, never cookies, so the
# API can answer any origin. The widget runs on customers' own websites.
CORS_ALLOW_ALL_ORIGINS = True
# last-event-id: a live stream resuming after a disconnect (apps.realtime.views).
CORS_ALLOW_HEADERS = (*default_headers, "x-visitor-token", "last-event-id")

# Longest message a visitor can send, and longest free-text form answer. Keeps each AI call
# small; the widget reads it from /widget/{key}/config and stops typing at it.
VISITOR_MESSAGE_MAX_CHARS = 500

# Abuse and cost limits (apps.conversations.limits). Past an AI cap, the conversation goes
# to a person instead of the LLM.
RATE_LIMITS = {
    "messages_per_visitor_per_minute": 10,
    "messages_per_ip_per_minute": 30,
    "new_visitors_per_ip_per_hour": 30,
    "ai_replies_per_visitor_per_day": 50,
    "ai_replies_per_workspace_per_day": 2000,
}

# What the AI sees of a conversation: recent turns up to this many characters (each message
# cut at HISTORY_MESSAGE_CHARS), always at least the last HISTORY_MIN_MESSAGES. Who the
# visitor is and what they came for are pinned in the system prompt instead.
HISTORY_BUDGET_CHARS = 6000
HISTORY_MESSAGE_CHARS = 1500
HISTORY_MIN_MESSAGES = 4

# Knowledge base search (apps.knowledge.search). SEARCH_LANGUAGE is a Postgres text search
# configuration: it decides word stemming ("refunds" finds "refund"). Use "simple" for a
# help center in a language Postgres has no configuration for, then run
# `manage.py reindex_knowledge`.
SEARCH_LANGUAGE = "english"
# How much article text one search hands the AI, in characters (about 4 per token).
KNOWLEDGE_BUDGET_CHARS = 5000

# A visitor writing after this long a silence starts a new conversation (old ones stay in
# the inbox but stop feeding the AI).
CONVERSATION_IDLE_HOURS = 24

# Live updates (apps.realtime). A visitor is online while their presence key lives; an
# open stream refreshes it on every keep-alive ping, so the TTL must be a few pings long.
PRESENCE_TTL_SECONDS = 45
STREAM_PING_SECONDS = 15
# A stream ends after this long and the browser reconnects at once. Checks the visitor or
# dashboard token again, and spreads connections over restarted stream processes.
STREAM_MAX_SECONDS = 600

# Redis does two jobs: the cache (rate-limit counters and reply locks, which every process
# must share) and the Celery broker (the queue of AI replies waiting for a worker). They
# use different database numbers of the same server, so clearing the cache can't empty
# the queue.
REDIS_URL = os.environ.get("REDIS_URL", "")
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}


def redis_database(url: str, number: int) -> str:
    """The same Redis server, another of its numbered databases."""
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{number}"))


# --- Celery (whileisleep/celery.py) ---
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL") or (redis_database(REDIS_URL, 1) if REDIS_URL else "")
# Without a broker there is nobody to hand jobs to, so they run inside the request that
# queued them. Fine for trying things on one machine; the visitor's request then waits for
# the AI.
CELERY_TASK_ALWAYS_EAGER = not CELERY_BROKER_URL
# Jobs report by writing to the database (a Turn, a message); nobody waits on a result.
CELERY_TASK_IGNORE_RESULT = True
# A job leaves the queue when it finishes, not when a worker picks it up, so a worker that
# dies mid-reply doesn't take the reply with it.
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
# Take one job at a time per worker thread instead of reserving a batch that then waits
# behind a slow LLM call.
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
# With Redis, a job a dead worker was holding comes back after this many seconds. Longer
# than any reply can take (REPLY_DEADLINE_SECONDS), or a slow reply would run twice.
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 900}
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TIMEZONE = "UTC"
# Run by `celery beat` (one per installation).
CELERY_BEAT_SCHEDULE = {
    # Picks up visitor messages whose reply job was lost; see apps/agent/tasks.py.
    "sweep-unanswered": {"task": "apps.agent.tasks.sweep_unanswered", "schedule": 60.0},
}

# Whether anyone can create an account (and with it an organization). Turn it off on a
# private installation once your own accounts exist.
SIGNUP_ENABLED = os.environ.get("SIGNUP_ENABLED", "true").lower() != "false"

# Fernet keys for secrets stored in the database (whileisleep.encryption): the first encrypts,
# all decrypt. Empty derives one from SECRET_KEY, which is fine for development only.
# Make one with: python manage.py generate_encryption_key
ENCRYPTION_KEYS = [k.strip() for k in os.environ.get("ENCRYPTION_KEYS", "").split(",") if k.strip()]

# Reverse proxies between the internet and Django (Caddy, a load balancer...). Rate limits
# read the visitor's address from X-Forwarded-For only as far as these can vouch for it
# (whileisleep.client_ip). 0 ignores the header.
TRUSTED_PROXY_COUNT = 0

# Tools call URLs that workspace owners typed in. Unless this is on, whileisleep.outbound
# refuses any that resolve to a private address (this server's own network).
OUTBOUND_ALLOW_PRIVATE_NETWORKS = False

# How long the AI waits before answering, in case the visitor is sending several short
# messages in a row; the last one's turn answers them all (apps.agent.pipeline).
REPLY_DEBOUNCE_SECONDS = 1.5
# The most time one reply may spend calling the model and tools before giving up and
# falling back to a help center search. Worker threads can't be interrupted from outside,
# so the loop checks this itself.
REPLY_DEADLINE_SECONDS = 120
# How long a reply job may hold its conversation's lock. Longer than the deadline plus one
# last model call, so a lock never expires under a reply that is still being written.
REPLY_LOCK_SECONDS = 300

# The AI agent's provider keys and models are per organization, set in the dashboard.
