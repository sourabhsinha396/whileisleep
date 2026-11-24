"""Production. Everything comes from environment variables (see backend/.env.example); a
missing or weak one stops the server at startup with a message saying which.

Assumes a tunnel or reverse proxy in front that terminates TLS and forwards the original scheme and client address.
"""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import BILLING_ENABLED, ENCRYPTION_KEYS, MIDDLEWARE, PAYMENT_PROVIDER, SECRET_KEY


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ImproperlyConfigured(f"{name} must be set in production.")
    return value


DEBUG = False

if len(SECRET_KEY) < 40:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set to a random string of at least 40 characters.")
if not ENCRYPTION_KEYS:
    # Without it, stored secrets would be tied to SECRET_KEY and couldn't be rotated.
    raise ImproperlyConfigured("ENCRYPTION_KEYS must be set. Make a key with: manage.py generate_encryption_key")
required("POSTGRES_PASSWORD")

# The public address, e.g. https://chat.example.com. The dashboard and the widget's API both
# live here.
SITE_URL = required("SITE_URL").rstrip("/")
if not SITE_URL.startswith("https://"):
    raise ImproperlyConfigured("SITE_URL must start with https://.")
# "web" is what the dashboard's server calls this one inside the Compose network, to render the docs.
ALLOWED_HOSTS = [SITE_URL.removeprefix("https://"), "web"]
CSRF_TRUSTED_ORIGINS = [SITE_URL]

# The proxy tells us the visitor's scheme and address.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "1"))

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
# Only this host: whileisleep can't know whether your other subdomains are HTTPS-only.
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
# `manage.py check --deploy` findings that are decisions, not oversights: HSTS stays on this
# host only (W005, W021), and the proxy redirects HTTP to HTTPS (W008).
SILENCED_SYSTEM_CHECKS = ["security.W005", "security.W008", "security.W021"]
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# Rate limits are counted in the cache, and every worker must see the same counts.
required("REDIS_URL")

# Half-configured payments would either take no money or lose track of who paid.
if PAYMENT_PROVIDER:
    for name in ("DODO_BASE_URL", "DODO_API_KEY", "DODO_PRODUCT_MONTHLY", "DODO_PRODUCT_YEARLY"):
        required(name)
    if not BILLING_ENABLED:
        raise ImproperlyConfigured("PAYMENT_PROVIDER must be 'dodo', or empty.")

# Keep database connections open between requests, and check them before use.
DATABASES["default"]["CONN_MAX_AGE"] = 60  # noqa: F405
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405

# Django's own static files (the admin), served by the app itself. Outside the code, which is
# mounted into the container.
STATIC_ROOT = "/opt/static"
MIDDLEWARE = [
    MIDDLEWARE[0],
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    *[m for m in MIDDLEWARE[1:] if m != "django.middleware.security.SecurityMiddleware"],
]
STORAGES["staticfiles"] = {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"}  # noqa: F405

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"line": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "line"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
