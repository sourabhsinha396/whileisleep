"""The organization's plan. Only its owner reaches these, except the webhook, which Dodo signs."""

import json
import logging

from django.conf import settings
from django.shortcuts import get_object_or_404
from ninja import Router
from ninja.errors import HttpError

from apps.accounts.security import token_auth
from apps.workspaces.models import Organization, Workspace
from apps.workspaces.services import organization_for

from . import dodo, services
from .schemas import BillingOut, CheckoutIn, LinkOut, PortalIn, SyncIn

log = logging.getLogger(__name__)
router = Router(tags=["billing"])


def billing_out(organization: Organization) -> dict:
    standing = services.standing(organization)
    subscription = standing.subscription
    return {
        "state": standing.state,
        "trial_days_left": standing.trial_days_left,
        "trial_ends_at": standing.trial_ends_at,
        "can_manage": standing.state != "off" and bool(services.account_for(organization).customer_id),
        "subscription": subscription,
        "prices": services.PRICES,
    }


def require_billing() -> None:
    if not settings.BILLING_ENABLED:
        raise HttpError(404, "Billing isn't set up on this installation.")


def unavailable(error: dodo.DodoError) -> HttpError:
    # What Dodo said is for whoever runs the server, not for the customer.
    log.warning("Dodo Payments: %s", error)
    return HttpError(502, "The payment service didn't answer as expected. Try again in a minute.")


def billing_page(organization: Organization, slug: str) -> str:
    """Where Dodo sends the customer back to: the billing page they came from."""
    workspace = get_object_or_404(Workspace, organization=organization, slug=slug)
    return f"{settings.SITE_URL}/w/{workspace.slug}/billing"


@router.get("/billing", response=BillingOut, auth=token_auth)
def get(request):
    return billing_out(organization_for(request.auth))


@router.post("/billing/checkout", response=LinkOut, auth=token_auth)
def checkout(request, payload: CheckoutIn):
    """Starts a subscription: the address of the payment page."""
    require_billing()
    organization = organization_for(request.auth)
    back = billing_page(organization, payload.workspace)
    try:
        return {"url": services.checkout_url(organization, payload.interval, back)}
    except services.AlreadySubscribed:
        raise HttpError(409, "You already have a plan. Use Manage plan to change it.") from None
    except dodo.DodoError as error:
        raise unavailable(error) from error


@router.post("/billing/portal", response=LinkOut, auth=token_auth)
def portal(request, payload: PortalIn):
    """Change the card, read invoices, cancel: a page at Dodo."""
    require_billing()
    organization = organization_for(request.auth)
    back = billing_page(organization, payload.workspace)
    customer_id = services.account_for(organization).customer_id
    if not customer_id:
        raise HttpError(409, "There is no plan to manage yet.")
    try:
        return {"url": dodo.portal_link(customer_id, back)}
    except dodo.DodoError as error:
        raise unavailable(error) from error


@router.post("/billing/sync", response=BillingOut, auth=token_auth)
def sync(request, payload: SyncIn):
    """Back from checkout: look the new subscription up now instead of waiting for the webhook.
    It counts only for the account it was bought for, whoever sends its id."""
    require_billing()
    try:
        services.sync(payload.subscription_id)
    except dodo.DodoError as error:
        raise unavailable(error) from error
    # Read it again: the account may have been made by this very request.
    return billing_out(Organization.objects.get(pk=organization_for(request.auth).pk))


@router.post("/billing/webhooks/dodo", auth=None, include_in_schema=False)
def webhook(request):
    if not settings.BILLING_ENABLED or not settings.DODO_WEBHOOK_KEY:
        raise HttpError(404, "Not found.")
    if not dodo.webhook_is_genuine(request.headers, request.body):
        raise HttpError(401, "Bad signature.")
    try:
        event = json.loads(request.body)
        kind, data = str(event["type"]), event["data"]
        subscription_id, product_id = data.get("subscription_id"), data.get("product_id")
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HttpError(400, "Not an event.") from None
    ours = product_id is None or product_id in services.products()
    if kind.startswith("subscription.") and subscription_id and ours:
        try:
            services.sync(subscription_id)
        except dodo.DodoError as error:
            # Not a 2xx, so Dodo sends it again later.
            raise unavailable(error) from error
    return {"ok": True}
