"""Shared settings. `local` (Docker dev) and `testing` build on this."""

import os
from pathlib import Path

from corsheaders.defaults import default_headers
from dotenv import load_dotenv

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
    "corsheaders",
    "apps.accounts",
    "apps.workspaces",
    "apps.conversations",
    "apps.knowledge",
    "apps.agent",
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
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# The dashboard and the widget both send bearer tokens, never cookies, so the
# API can answer any origin. The widget runs on customers' own websites.
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_HEADERS = (*default_headers, "x-visitor-token")

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

# A visitor writing after this long a silence starts a new conversation (old ones stay in
# the inbox but stop feeding the AI).
CONVERSATION_IDLE_HOURS = 24

# A visitor counts as online if the widget pinged within this many seconds.
ONLINE_WINDOW_SECONDS = 60

# Reverse proxies between the internet and Django (Caddy, a load balancer...). Rate limits
# read the visitor's address from X-Forwarded-For only as far as these can vouch for it
# (whileisleep.client_ip). 0 ignores the header.
TRUSTED_PROXY_COUNT = 0

# Tools call URLs that workspace owners typed in. Unless this is on, whileisleep.outbound
# refuses any that resolve to a private address (this server's own network).
OUTBOUND_ALLOW_PRIVATE_NETWORKS = False

# The AI agent's OpenRouter key and model are per organization, set in the dashboard.
# Tests set this so the bot replies inside the request instead of a thread.
BOT_SYNC = False
