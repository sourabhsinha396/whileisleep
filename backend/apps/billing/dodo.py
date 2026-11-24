"""Minimal Dodo Payments client: checkout, subscriptions, the customer portal, and webhooks.

Docs: https://docs.dodopayments.com/api-reference/introduction

Dodo is the merchant of record: it takes the card, works out tax and sends invoices. No card
detail ever reaches this server.
"""

import base64
import binascii
import hashlib
import hmac
import time

import httpx
from django.conf import settings

TIMEOUT_SECONDS = 20
# A webhook older (or newer) than this is refused, so a captured one can't be replayed later.
WEBHOOK_TOLERANCE_SECONDS = 300


class DodoError(Exception):
    """A failed call. `status` is None when Dodo couldn't be reached."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def call(method: str, path: str, **kwargs) -> dict:
    try:
        response = httpx.request(
            method,
            settings.DODO_BASE_URL.rstrip("/") + path,
            headers={"Authorization": f"Bearer {settings.DODO_API_KEY}"},
            timeout=TIMEOUT_SECONDS,
            **kwargs,
        )
    except httpx.HTTPError as error:
        raise DodoError(f"Could not reach Dodo Payments: {type(error).__name__}") from error
    if response.status_code >= 400:
        try:
            message = response.json()["message"]
        except (ValueError, KeyError, TypeError):
            message = response.reason_phrase
        raise DodoError(f"Dodo Payments refused: {message}", response.status_code)
    try:
        return response.json()
    except ValueError as error:
        raise DodoError("Dodo Payments sent a response that isn't JSON.") from error


# --- Selling ---


def create_checkout(product_id: str, customer: dict, return_url: str, metadata: dict) -> str:
    """The address of a hosted checkout page for one subscription."""
    data = call(
        "POST",
        "/checkouts",
        json={
            "product_cart": [{"product_id": product_id, "quantity": 1}],
            "customer": customer,
            "return_url": return_url,
            "cancel_url": return_url,
            "metadata": metadata,
            "feature_flags": {
                # Without this Dodo attaches the checkout to whoever already has that email. We
                # don't verify emails, so paying with someone else's would open their customer
                # portal (their invoices and cards, in every product of this Dodo account).
                "always_create_new_customer": "customer_id" not in customer,
            },
        },
    )
    url = data.get("checkout_url")
    if not url:
        raise DodoError("Dodo Payments made a checkout without an address.")
    return url


def get_subscription(subscription_id: str) -> dict:
    return call("GET", f"/subscriptions/{subscription_id}")


def portal_link(customer_id: str, return_url: str) -> str:
    """A short-lived link where the customer changes their card, reads invoices and cancels."""
    data = call("POST", f"/customers/{customer_id}/customer-portal/session", params={"return_url": return_url})
    if not data.get("link"):
        raise DodoError("Dodo Payments made a portal session without a link.")
    return data["link"]


# --- Setting up (manage.py billing_setup) ---


def list_products() -> list[dict]:
    products, page = [], 0
    while True:
        items = call("GET", "/products", params={"page_size": 100, "page_number": page}).get("items") or []
        products += items
        if len(items) < 100:
            return products
        page += 1


def create_product(body: dict) -> str:
    return call("POST", "/products", json=body)["product_id"]


def list_webhooks() -> list[dict]:
    return call("GET", "/webhooks", params={"limit": 100}).get("data") or []


def create_webhook(url: str, events: list[str]) -> str:
    return call("POST", "/webhooks", json={"url": url, "description": "whileisleep", "filter_types": events})["id"]


def webhook_secret(webhook_id: str) -> str:
    return call("GET", f"/webhooks/{webhook_id}/secret")["secret"]


# --- Webhooks (the Standard Webhooks scheme) ---


def signature(secret: str, webhook_id: str, timestamp: str, body: bytes) -> str:
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{webhook_id}.{timestamp}.".encode() + body
    return base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()


def webhook_is_genuine(headers, body: bytes) -> bool:
    """Whether Dodo sent this: signed with our webhook key, and recently."""
    webhook_id = headers.get("webhook-id", "")
    timestamp = headers.get("webhook-timestamp", "")
    try:
        if abs(time.time() - int(timestamp)) > WEBHOOK_TOLERANCE_SECONDS:
            return False
        expected = signature(settings.DODO_WEBHOOK_KEY, webhook_id, timestamp, body)
    except (ValueError, binascii.Error):
        return False
    # Several signatures while a key is being rotated: "v1,aaa v1,bbb".
    sent = [part.removeprefix("v1,") for part in headers.get("webhook-signature", "").split() if part.startswith("v1,")]
    return any(hmac.compare_digest(expected.encode(), one.encode()) for one in sent)
