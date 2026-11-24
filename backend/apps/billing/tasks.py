"""Background jobs for billing, run by the Celery worker."""

import logging

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from . import dodo, services
from .models import Subscription

log = logging.getLogger(__name__)


@shared_task
def refresh_subscriptions() -> int:
    """The safety net under the webhooks: asks Dodo about every subscription that should have
    changed by now (its paid period is over) or that is waiting on a payment. Returns how many
    were refreshed."""
    if not settings.BILLING_ENABLED:
        return 0
    due = Subscription.objects.exclude(status__in=Subscription.ENDED).filter(
        ~Q(status=Subscription.Status.ACTIVE) | Q(paid_until__lt=timezone.now())
    )
    count = 0
    for provider_id in due.order_by("updated_at").values_list("provider_id", flat=True)[:100]:
        try:
            services.sync(provider_id)
            count += 1
        except dodo.DodoError as error:
            log.warning("Could not refresh subscription %s: %s", provider_id, error)
    return count
