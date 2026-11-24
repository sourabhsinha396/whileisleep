"""A stand-in for Dodo Payments, and helpers for billing tests."""

import json
from datetime import timedelta

import httpx
from django.utils import timezone

from apps.billing import services
from apps.billing.models import BillingAccount

SECRET = "whsec_c2VjcmV0LXNlY3JldC1zZWNyZXQ="


class FakeDodo:
    """Dodo's API: what it holds, and every request made to it."""

    def __init__(self):
        self.subscriptions = {}
        self.products = []
        self.webhooks = []
        self.requests = []
        self.down = False

    def sent(self, path: str) -> list[dict]:
        return [body for _, called, body in self.requests if called == path]

    def handle(self, transport, request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://test.dodopayments.com/")
        assert request.headers["Authorization"] == "Bearer dodo-key"
        path = request.url.path
        body = json.loads(request.content) if request.content else dict(request.url.params)
        self.requests.append((request.method, path, body))
        if self.down:
            raise httpx.ConnectError("no route")
        status, data = self.answer(request.method, path, body)
        return httpx.Response(status, json=data, request=request)

    def answer(self, method, path, body):
        if path == "/checkouts":
            return 200, {"session_id": "cks_1", "checkout_url": "https://checkout.example.com/cks_1"}
        if path.endswith("/customer-portal/session"):
            return 200, {"link": "https://portal.example.com/p"}
        if path.startswith("/subscriptions/"):
            found = self.subscriptions.get(path.rsplit("/", 1)[1])
            return (200, found) if found else (404, {"code": "NOT_FOUND", "message": "No such thing"})
        if path == "/products" and method == "GET":
            return 200, {"items": self.products if body["page_number"] == "0" else []}
        if path == "/products":
            return 200, {"product_id": f"pdt_{body['metadata']['whileisleep_plan']}"}
        if path == "/webhooks" and method == "GET":
            return 200, {"data": self.webhooks, "done": True}
        if path == "/webhooks":
            return 200, {"id": "ep_1", "url": body["url"]}
        if path.endswith("/secret"):
            return 200, {"secret": SECRET}
        raise AssertionError(f"Unexpected call: {method} {path}")

    def subscribe(self, account: BillingAccount, id="sub_1", **fields) -> dict:
        """What Dodo holds after someone pays."""
        self.subscriptions[id] = {
            "subscription_id": id,
            "status": "active",
            "product_id": "pdt_m",
            "metadata": {"whileisleep_account": account.reference},
            "customer": {"customer_id": "cus_1", "email": "a@example.com", "name": "A"},
            "cancel_at_next_billing_date": False,
            "next_billing_date": (timezone.now() + timedelta(days=30)).isoformat(),
        } | fields
        return self.subscriptions[id]


def end_trial(account):
    account.trial_ends_at = timezone.now() - timedelta(minutes=1)
    account.save()


def state(account) -> str:
    fresh = BillingAccount.objects.select_related("organization").get(pk=account.pk)
    return services.standing(fresh.organization).state
