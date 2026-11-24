"""What an organization may do, and how its subscription gets here.

The AI answers while the trial runs or a subscription gives access. Everything else (the
inbox, the widget, rules, the data) never depends on paying. With billing off
(settings.BILLING_ENABLED), as on your own server, nothing here limits anything.

Dodo is the only authority on subscriptions. A webhook, the customer coming back from
checkout and the hourly refresh all do the same thing: ask Dodo for the subscription and copy
it (`sync`). So webhooks may arrive twice, late or out of order.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.workspaces.models import Organization

from . import dodo
from .models import BillingAccount, Subscription

# Where a checkout says which account it is for.
REFERENCE_KEY = "whileisleep_account"
# In US cents, before tax. Also on the pricing page (frontend/src/lib/pricing.ts).
PRICES = {Subscription.Interval.MONTHLY: 200, Subscription.Interval.YEARLY: 1200}


def products() -> dict[str, str]:
    """Dodo product id -> interval."""
    return {
        settings.DODO_PRODUCT_MONTHLY: Subscription.Interval.MONTHLY.value,
        settings.DODO_PRODUCT_YEARLY: Subscription.Interval.YEARLY.value,
    }


def account_for(organization: Organization) -> BillingAccount:
    try:
        # Already loaded when the caller used select_related.
        return organization.billing_account
    except BillingAccount.DoesNotExist:
        account, _ = BillingAccount.objects.get_or_create(organization=organization)
        return account


@dataclass
class Standing:
    """Where an organization stands."""

    # "off" (billing isn't used here), "trial", "active" or "paused".
    state: str
    # Whole days, the last one counting as 1. Only during a trial.
    trial_days_left: int | None = None
    trial_ends_at: datetime | None = None
    subscription: Subscription | None = None

    @property
    def ai_allowed(self) -> bool:
        return self.state != "paused"


def standing(organization: Organization) -> Standing:
    if not settings.BILLING_ENABLED:
        return Standing("off")
    account = account_for(organization)
    subscriptions = list(account.subscriptions.order_by("-created_at"))
    giving = next((s for s in subscriptions if s.gives_access), None)
    if giving:
        return Standing("active", subscription=giving)
    # One that needs a new card, or the last one they had.
    latest = next((s for s in subscriptions if s.status in Subscription.OPEN), None)
    latest = latest or next((s for s in subscriptions if s.paid_until), None)
    left = account.trial_ends_at - timezone.now()
    if left > timedelta(0):
        return Standing("trial", math.ceil(left / timedelta(days=1)), account.trial_ends_at, latest)
    return Standing("paused", trial_ends_at=account.trial_ends_at, subscription=latest)


def ai_allowed(organization: Organization) -> bool:
    return standing(organization).ai_allowed


class AlreadySubscribed(Exception):
    pass


def checkout_url(organization: Organization, interval: str, return_url: str) -> str:
    account = account_for(organization)
    if account.subscriptions.filter(status__in=Subscription.OPEN).exists():
        raise AlreadySubscribed
    product_id = next(product for product, sold in products().items() if sold == interval)
    owner = organization.owner
    customer = (
        {"customer_id": account.customer_id}
        if account.customer_id
        else {"email": owner.email, "name": owner.first_name or owner.email}
    )
    return dodo.create_checkout(product_id, customer, return_url, {REFERENCE_KEY: account.reference})


def sync(subscription_id: str) -> Subscription | None:
    """Copies a subscription from Dodo. None if it isn't one of ours: the Dodo account may sell
    other products too, or serve another installation."""
    data = dodo.get_subscription(subscription_id)
    interval = products().get(data.get("product_id"))
    reference = (data.get("metadata") or {}).get(REFERENCE_KEY)
    if not interval or not reference:
        return None
    with transaction.atomic():
        account = BillingAccount.objects.select_for_update().filter(reference=reference).first()
        if account is None:
            return None
        subscription = Subscription.objects.filter(provider_id=subscription_id).first()
        subscription = subscription or Subscription(provider_id=subscription_id, account=account)
        subscription.status = data["status"]
        subscription.interval = interval
        subscription.cancels_at_period_end = bool(data.get("cancel_at_next_billing_date"))
        if subscription.status == Subscription.Status.ACTIVE:
            # Only then is the current period paid for; after a failed renewal it isn't.
            subscription.paid_until = parse_datetime(data["next_billing_date"])
        subscription.save()
        customer_id = (data.get("customer") or {}).get("customer_id")
        if customer_id and account.customer_id != customer_id and subscription.status in Subscription.OPEN:
            account.customer_id = customer_id
            account.save(update_fields=["customer_id"])
    return subscription
