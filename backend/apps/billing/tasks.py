"""Background jobs for billing, run by the Celery worker."""

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from . import dodo, services
from .models import Subscription

log = logging.getLogger(__name__)


@shared_task
def find_payments() -> int:
    """Finds the plans of people who paid but never came back from the payment page."""
    if not settings.BILLING_ENABLED:
        return 0
    try:
        return services.find_payments(services.waiting())
    except dodo.DodoError as error:
        log.warning("Could not look for payments: %s", error)
        return 0


@shared_task
def refresh_subscriptions() -> int:
    """Asks Dodo about every subscription that should have changed by now (its paid period is
    over), that is waiting on a payment, or that wasn't looked at for a day (it may have been
    cancelled or refunded). Returns how many were refreshed."""
    if not settings.BILLING_ENABLED:
        return 0
    now = timezone.now()
    due = Subscription.objects.exclude(status__in=Subscription.ENDED).filter(
        ~Q(status=Subscription.Status.ACTIVE) | Q(paid_until__lt=now) | Q(updated_at__lt=now - timedelta(days=1))
    )
    count = 0
    for provider_id in due.order_by("updated_at").values_list("provider_id", flat=True)[:100]:
        try:
            services.sync(provider_id)
            count += 1
        except dodo.DodoError as error:
            log.warning("Could not refresh subscription %s: %s", provider_id, error)
    return count
