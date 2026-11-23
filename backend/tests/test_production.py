"""Production settings refuse to start half-configured, and the operational endpoints work."""

import importlib
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured

from whileisleep import encryption

from .conftest import Api

GOOD = {
    "DJANGO_SECRET_KEY": "s" * 50,
    "ENCRYPTION_KEYS": encryption.new_key(),
    "POSTGRES_PASSWORD": "a-real-password",
    "SITE_URL": "https://chat.example.com",
    "REDIS_URL": "redis://redis:6379/0",
}


def load_production(monkeypatch, **overrides):
    """Imports the production settings module fresh, with this environment."""
    for name, value in (GOOD | overrides).items():
        # "Missing" is set-but-empty: a developer's backend/.env can't fill an empty variable
        # back in, and production treats empty as unset.
        monkeypatch.setenv(name, value or "")
    for module in ("whileisleep.settings.production", "whileisleep.settings.base"):
        sys.modules.pop(module, None)
    try:
        return importlib.import_module("whileisleep.settings.production")
    finally:
        # Leave no half-imported settings behind for other tests.
        for module in ("whileisleep.settings.production", "whileisleep.settings.base"):
            sys.modules.pop(module, None)


def test_a_complete_environment_loads(monkeypatch):
    production = load_production(monkeypatch)
    assert production.DEBUG is False
    assert production.ALLOWED_HOSTS == ["chat.example.com"]
    assert production.CSRF_TRUSTED_ORIGINS == ["https://chat.example.com"]
    assert production.SESSION_COOKIE_SECURE and production.SECURE_HSTS_SECONDS > 0
    assert production.TRUSTED_PROXY_COUNT == 1
    assert production.OUTBOUND_ALLOW_PRIVATE_NETWORKS is False
    assert production.CACHES["default"]["LOCATION"] == "redis://redis:6379/0"
    assert "whitenoise.middleware.WhiteNoiseMiddleware" in production.MIDDLEWARE
    # CORS must stay first so even error responses carry its headers.
    assert production.MIDDLEWARE[0] == "corsheaders.middleware.CorsMiddleware"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"DJANGO_SECRET_KEY": None}, "DJANGO_SECRET_KEY"),
        ({"DJANGO_SECRET_KEY": "short"}, "DJANGO_SECRET_KEY"),
        ({"ENCRYPTION_KEYS": None}, "ENCRYPTION_KEYS"),
        ({"POSTGRES_PASSWORD": None}, "POSTGRES_PASSWORD"),
        ({"SITE_URL": None}, "SITE_URL"),
        ({"SITE_URL": "http://chat.example.com"}, "https://"),
        ({"REDIS_URL": None}, "REDIS_URL"),
    ],
)
def test_missing_or_weak_settings_stop_startup(monkeypatch, overrides, message):
    with pytest.raises(ImproperlyConfigured, match=message):
        load_production(monkeypatch, **overrides)


def test_trailing_slash_in_site_url_is_fine(monkeypatch):
    assert load_production(monkeypatch, SITE_URL="https://chat.example.com/").ALLOWED_HOSTS == ["chat.example.com"]


# --- Operational endpoints ---


def test_health_needs_nothing():
    assert Api().get("/health").json() == {"ok": True}


@pytest.mark.django_db
def test_ready_checks_the_database_and_cache():
    assert Api().get("/ready").json() == {"ok": True}


@pytest.mark.django_db
def test_ready_reports_a_broken_cache(monkeypatch):
    from whileisleep import api as api_module

    def broken(*args, **kwargs):
        raise ConnectionError("redis is down")

    monkeypatch.setattr(api_module.cache, "set", broken)
    response = Api().get("/ready")
    assert response.status_code == 503 and "ConnectionError" in response.json()["detail"]


# --- Closing sign-up ---


@pytest.mark.django_db
def test_signup_can_be_closed(settings):
    body = {"name": "Sofia", "email": "sofia@example.com", "password": "password123"}
    settings.SIGNUP_ENABLED = False
    closed = Api().post("/auth/signup", body)
    assert closed.status_code == 403 and "closed" in closed.json()["detail"]
    settings.SIGNUP_ENABLED = True
    assert Api().post("/auth/signup", body).status_code == 200
