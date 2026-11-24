"""manage.py billing_setup."""

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from apps.billing.apps import half_configured

from .fake_dodo import SECRET


def run_setup(*args) -> str:
    out = StringIO()
    call_command("billing_setup", *args, stdout=out)
    return out.getvalue()


def test_setup_changes_nothing_unless_told_to(billing):
    assert "missing" in run_setup()
    assert {method for method, *_ in billing.requests} == {"GET"}


def test_setup_creates_what_is_missing(billing):
    out = run_setup("--create")
    assert "DODO_PRODUCT_MONTHLY=pdt_monthly" in out and "DODO_PRODUCT_YEARLY=pdt_yearly" in out
    assert f"DODO_WEBHOOK_KEY={SECRET}" in out
    made = [body for method, path, body in billing.requests if (method, path) == ("POST", "/products")]
    assert [(p["price"]["price"], p["price"]["payment_frequency_interval"]) for p in made] == [
        (200, "Month"),
        (1200, "Year"),
    ]
    hook = next(body for method, path, body in billing.requests if (method, path) == ("POST", "/webhooks"))
    assert hook["url"] == "https://chat.example.com/api/v1/billing/webhooks/dodo"


def test_setup_run_again_finds_its_own_and_leaves_others_alone(billing):
    billing.products = [
        {"product_id": "pdt_exam", "price": 500, "metadata": {}},
        {"product_id": "pdt_a", "price": 200, "metadata": {"whileisleep_plan": "monthly"}},
        {"product_id": "pdt_b", "price": 900, "metadata": {"whileisleep_plan": "yearly"}},
    ]
    billing.webhooks = [{"id": "ep_9", "url": "https://chat.example.com/api/v1/billing/webhooks/dodo"}]
    out = run_setup("--create")
    assert "DODO_PRODUCT_MONTHLY=pdt_a" in out and "price at Dodo is 900" in out
    assert {method for method, *_ in billing.requests} == {"GET"}


def test_setup_without_a_public_address_makes_no_webhook(billing, settings):
    settings.SITE_URL = "http://localhost:3004"
    assert "skipped" in run_setup("--create")
    assert billing.sent("/webhooks") == []


def test_setup_needs_a_key(settings):
    with pytest.raises(CommandError, match="DODO_API_KEY"):
        run_setup()


def test_a_half_configured_server_says_so(settings):
    assert half_configured(None) == []
    settings.PAYMENT_PROVIDER, settings.BILLING_MISSING = "dodo", ["DODO_PRODUCT_YEARLY"]
    assert "DODO_PRODUCT_YEARLY" in half_configured(None)[0].msg
