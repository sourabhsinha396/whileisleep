"""Trials, plans and Dodo Payments, against a fake Dodo (fake_dodo.py)."""

import json
import re
import time
from datetime import timedelta
from pathlib import Path

import pytest
from django.test import Client
from django.utils import timezone

from apps.billing import dodo, services, tasks
from apps.billing.models import BillingAccount, Subscription

from .conftest import Api
from .factories import (
    AuthTokenFactory,
    MembershipFactory,
    OrganizationFactory,
    WorkspaceFactory,
)
from .fake_dodo import SECRET, end_trial, state

pytestmark = pytest.mark.django_db

# --- Standing ---


def test_without_billing_nothing_is_limited_or_recorded(api, workspace):
    assert services.standing(workspace.organization).state == "off"
    assert services.ai_allowed(workspace.organization)
    assert api.get(f"/workspaces/{workspace.id}").json()["billing_state"] == "off"
    assert not BillingAccount.objects.exists()


def test_a_trial_lasts_fourteen_days(account, settings):
    standing = services.standing(account.organization)
    assert (standing.state, standing.trial_days_left) == ("trial", 14)
    account.trial_ends_at = timezone.now() + timedelta(hours=2)
    assert services.standing(account.organization).trial_days_left == 1
    end_trial(account)
    assert services.standing(account.organization).state == "paused"


def test_organizations_from_before_billing_get_a_full_trial(billing):
    organization = OrganizationFactory()
    type(organization).objects.filter(pk=organization.pk).update(created_at=timezone.now() - timedelta(days=400))
    assert services.standing(organization).trial_days_left == 14


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("active", "active"),
        ("past_due", "active"),  # Dodo is still trying the card
        ("on_hold", "paused"),
        ("paused", "paused"),
        ("pending", "paused"),
        ("failed", "paused"),
        ("expired", "paused"),
        ("cancelled", "paused"),  # never saw it paid
    ],
)
def test_which_statuses_give_access_after_the_trial(account, billing, status, expected):
    end_trial(account)
    billing.subscribe(account, status=status)
    services.sync("sub_1")
    assert state(account) == expected


def test_cancelling_keeps_the_time_already_paid_for(account, billing):
    end_trial(account)
    billing.subscribe(account)
    services.sync("sub_1")
    billing.subscribe(account, status="cancelled")
    services.sync("sub_1")
    assert state(account) == "active"
    Subscription.objects.update(paid_until=timezone.now() - timedelta(minutes=1))
    assert state(account) == "paused"


def test_a_failed_renewal_does_not_count_as_paid_time(account, billing):
    """Dodo may move next_billing_date on before it knows the renewal failed."""
    end_trial(account)
    billing.subscribe(account, next_billing_date=(timezone.now() - timedelta(minutes=1)).isoformat())
    services.sync("sub_1")
    for status in ("on_hold", "cancelled"):
        billing.subscribe(account, status=status)
        services.sync("sub_1")
        assert state(account) == "paused"


# --- Checkout and the portal ---


@pytest.mark.parametrize(("interval", "product"), [("monthly", "pdt_m"), ("yearly", "pdt_y")])
def test_checkout(api, account, billing, workspace, interval, product):
    response = api.post("/billing/checkout", {"interval": interval, "workspace": workspace.slug})
    assert response.json() == {"url": "https://checkout.example.com/cks_1"}
    sent = billing.sent("/checkouts")[0]
    assert sent["product_cart"] == [{"product_id": product, "quantity": 1}]
    assert sent["metadata"] == {"whileisleep_account": account.reference}
    assert sent["customer"]["email"] == account.organization.owner.email
    assert sent["return_url"] == f"https://chat.example.com/w/{workspace.slug}/billing"


def test_checkout_never_joins_an_existing_dodo_customer_by_email(api, account, billing, workspace):
    """Emails aren't verified here, and a customer's portal shows their cards and invoices."""
    api.post("/billing/checkout", {"interval": "monthly", "workspace": workspace.slug})
    assert billing.sent("/checkouts")[0]["feature_flags"]["always_create_new_customer"] is True


def test_coming_back_reuses_our_own_customer(api, account, billing, workspace):
    account.customer_id = "cus_1"
    account.save()
    api.post("/billing/checkout", {"interval": "monthly", "workspace": workspace.slug})
    assert billing.sent("/checkouts")[0]["customer"] == {"customer_id": "cus_1"}


@pytest.mark.parametrize("status", ["active", "past_due", "on_hold", "paused"])
def test_no_second_plan_next_to_an_open_one(api, account, billing, workspace, status):
    billing.subscribe(account, status=status)
    services.sync("sub_1")
    assert api.post("/billing/checkout", {"interval": "monthly", "workspace": workspace.slug}).status_code == 409
    assert billing.sent("/checkouts") == []


def test_a_new_plan_after_the_last_one_ended(api, account, billing, workspace):
    billing.subscribe(account, status="expired")
    services.sync("sub_1")
    assert api.post("/billing/checkout", {"interval": "yearly", "workspace": workspace.slug}).status_code == 200


def test_checkout_wants_a_known_interval_and_your_own_workspace(api, account, billing, workspace):
    assert api.post("/billing/checkout", {"interval": "weekly", "workspace": workspace.slug}).status_code == 422
    other = WorkspaceFactory()
    assert api.post("/billing/checkout", {"interval": "monthly", "workspace": other.slug}).status_code == 404


def test_a_teammate_cannot_buy_for_someone_elses_organization(account, billing, workspace):
    agent = MembershipFactory(workspace=workspace, role="agent")
    as_agent = Api(token=AuthTokenFactory(user=agent.user).key)
    response = as_agent.post("/billing/checkout", {"interval": "monthly", "workspace": workspace.slug})
    assert response.status_code == 404


def test_the_portal(api, account, billing, workspace):
    assert api.post("/billing/portal", {"workspace": workspace.slug}).status_code == 409
    billing.subscribe(account)
    services.sync("sub_1")
    assert api.post("/billing/portal", {"workspace": workspace.slug}).json() == {"url": "https://portal.example.com/p"}
    assert billing.requests[-1][1] == "/customers/cus_1/customer-portal/session"


def test_dodo_being_down_is_not_our_crash(api, account, billing, workspace):
    billing.down = True
    response = api.post("/billing/checkout", {"interval": "monthly", "workspace": workspace.slug})
    assert response.status_code == 502 and "Dodo" not in response.json()["detail"]


@pytest.mark.parametrize("path", ["checkout", "portal", "sync"])
def test_nothing_to_buy_when_billing_is_off(api, workspace, path):
    body = {"interval": "monthly", "workspace": workspace.slug, "subscription_id": "sub_1"}
    assert api.post(f"/billing/{path}", body).status_code == 404


def test_billing_needs_a_login(anon, billing):
    assert anon.get("/billing").status_code == 401


# --- Back from checkout ---


def test_coming_back_activates_the_plan_without_a_webhook(api, account, billing):
    billing.subscribe(account, product_id="pdt_y")
    result = api.post("/billing/sync", {"subscription_id": "sub_1"}).json()
    assert result["state"] == "active" and result["can_manage"] is True
    assert result["subscription"]["interval"] == "yearly"
    assert api.get("/billing").json() == result


def test_someone_elses_subscription_is_not_yours(api, account, billing):
    other = services.account_for(OrganizationFactory())
    billing.subscribe(other)
    assert api.post("/billing/sync", {"subscription_id": "sub_1"}).json()["state"] == "trial"
    assert state(other) == "active"


def test_a_subscription_never_changes_hands(account, billing):
    other = services.account_for(OrganizationFactory())
    billing.subscribe(account)
    services.sync("sub_1")
    billing.subscribe(other)
    services.sync("sub_1")
    assert Subscription.objects.get().account == account


@pytest.mark.parametrize(
    "fields", [{"product_id": "pdt_other"}, {"metadata": {}}, {"metadata": {"whileisleep_account": "acc_x"}}]
)
def test_other_products_in_the_same_dodo_account_are_ignored(account, billing, fields):
    billing.subscribe(account, **fields)
    assert services.sync("sub_1") is None
    assert not Subscription.objects.exists()


@pytest.mark.parametrize("bad", ["", "cus_1", "sub_1/../../customers", "sub_1?x=1"])
def test_only_an_id_reaches_dodos_address(api, account, billing, bad):
    assert api.post("/billing/sync", {"subscription_id": bad}).status_code == 422
    assert billing.requests == []


def test_an_unknown_subscription(api, account, billing):
    assert api.post("/billing/sync", {"subscription_id": "sub_nope"}).status_code == 502


# --- Webhooks ---


def deliver(event: dict | bytes, secret=SECRET, age=0, **headers):
    body = event if isinstance(event, bytes) else json.dumps(event).encode()
    stamp = str(int(time.time()) - age)
    signed = "v1," + dodo.signature(secret, "msg_1", stamp, body)
    headers = {"webhook-id": "msg_1", "webhook-timestamp": stamp, "webhook-signature": signed} | headers
    return Client().post("/api/v1/billing/webhooks/dodo", body, content_type="application/json", headers=headers)


def event(kind="subscription.active", **data):
    return {
        "type": kind,
        "data": {"payload_type": "Subscription", "subscription_id": "sub_1", "product_id": "pdt_m"} | data,
    }


def test_the_signature_matches_the_standard_webhooks_example():
    """The worked example from the Standard Webhooks reference libraries."""
    body = b'{"test": 2432232314}'
    secret = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
    signed = dodo.signature(secret, "msg_p5jXN8AQM9LWM0D4loKWxJek", "1614265330", body)
    assert signed == "g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE="


def test_a_webhook_activates_the_plan(account, billing):
    billing.subscribe(account)
    assert deliver(event()).status_code == 200
    assert Subscription.objects.get().status == "active"


def test_what_dodo_says_now_counts_not_what_the_webhook_said(account, billing):
    """So a late or repeated webhook can't bring a cancelled plan back."""
    billing.subscribe(account, status="cancelled")
    for _ in range(2):
        assert deliver(event("subscription.active", status="active")).status_code == 200
    assert Subscription.objects.get().status == "cancelled"


def test_unsigned_old_or_tampered_webhooks_are_refused(account, billing, settings):
    billing.subscribe(account)
    other = "whsec_b3RoZXItb3RoZXItb3RoZXI="
    good = json.dumps(event()).encode()
    stamp = str(int(time.time()))
    for response in (
        deliver(event(), secret=other),
        deliver(event(), age=600),
        deliver(event(), age=-600),
        deliver(event(), **{"webhook-signature": ""}),
        deliver(event(), **{"webhook-timestamp": "soon"}),
        deliver(event(), **{"webhook-signature": "v1,é"}),
        deliver(good + b" ", **{"webhook-signature": "v1," + dodo.signature(SECRET, "msg_1", stamp, good)}),
    ):
        assert response.status_code == 401
    assert billing.requests == []


def test_either_signature_works_while_the_key_is_rotated(account, billing):
    body, stamp = json.dumps(event("payment.succeeded")).encode(), str(int(time.time()))
    both = f"v1,AAAA v1,{dodo.signature(SECRET, 'msg_1', stamp, body)}"
    assert deliver(body, **{"webhook-signature": both, "webhook-timestamp": stamp}).status_code == 200


def test_events_that_are_not_about_our_plans_cost_no_call(account, billing):
    assert deliver(event("payment.succeeded")).status_code == 200
    assert deliver(event(product_id="pdt_other")).status_code == 200
    assert deliver(event(subscription_id=None)).status_code == 200
    assert billing.requests == []


def test_dodo_sends_it_again_when_we_could_not_look_it_up(account, billing):
    billing.down = True
    assert deliver(event()).status_code == 502


@pytest.mark.parametrize("body", [b"not json", b"[]", b"{}", b'{"type": "subscription.active", "data": null}'])
def test_odd_webhooks(account, billing, body):
    assert deliver(body).status_code == 400


def test_no_webhook_key_means_no_webhooks(account, billing, settings):
    settings.DODO_WEBHOOK_KEY = ""
    assert deliver(event()).status_code == 404


# --- The hourly refresh ---


def test_refresh_asks_about_what_should_have_changed(account, billing):
    over = (timezone.now() - timedelta(hours=1)).isoformat()
    billing.subscribe(account, "sub_over", next_billing_date=over)
    billing.subscribe(account, "sub_hold", status="on_hold")
    billing.subscribe(account, "sub_fine")
    billing.subscribe(account, "sub_done", status="expired")
    for id in billing.subscriptions:
        services.sync(id)
    billing.requests.clear()
    billing.subscriptions["sub_over"]["status"] = "expired"
    assert tasks.refresh_subscriptions() == 2
    assert sorted(path for _, path, _ in billing.requests) == ["/subscriptions/sub_hold", "/subscriptions/sub_over"]
    assert Subscription.objects.get(provider_id="sub_over").status == "expired"


def test_refresh_survives_dodo_being_down(account, billing):
    billing.subscribe(account, status="on_hold")
    services.sync("sub_1")
    billing.down = True
    assert tasks.refresh_subscriptions() == 0


def test_refresh_does_nothing_without_billing():
    assert tasks.refresh_subscriptions() == 0


# --- The dashboard ---


def test_the_billing_page(api, account):
    page = api.get("/billing").json()
    assert page["state"] == "trial" and page["subscription"] is None and page["can_manage"] is False
    assert page["prices"] == {"monthly": 200, "yearly": 1200}


def test_the_pricing_page_shows_what_we_charge():
    source = Path(__file__).resolve().parents[2] / "frontend/src/lib/pricing.ts"
    if not source.exists():
        pytest.skip("the backend is checked out alone")
    monthly, yearly = re.search(r"monthly: ([\d.]+), yearlyPerMonth: ([\d.]+)", source.read_text()).groups()
    assert services.PRICES == {"monthly": float(monthly) * 100, "yearly": float(yearly) * 1200}
