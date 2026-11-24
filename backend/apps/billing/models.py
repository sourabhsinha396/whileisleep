import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.workspaces.models import Organization


def new_reference() -> str:
    return "acc_" + secrets.token_urlsafe(24)


def trial_end():
    return timezone.now() + timedelta(days=settings.TRIAL_DAYS)


class BillingAccount(models.Model):
    """An organization as a paying customer. Made the first time billing looks at it, which
    starts its trial: organizations that exist when billing is switched on get a full one."""

    organization = models.OneToOneField(Organization, on_delete=models.CASCADE, related_name="billing_account")
    # Travels with a checkout and comes back on the subscription it creates, saying whose it
    # is. Random: several installations (test, staging) can share one Dodo account, and their
    # organizations have the same ids.
    reference = models.CharField(max_length=64, unique=True, default=new_reference)
    trial_ends_at = models.DateTimeField(default=trial_end)
    # The customer at Dodo, once someone has paid.
    customer_id = models.CharField(max_length=64, blank=True)
    # When they last opened a payment page, so we know to look for a payment they didn't come back from.
    last_checkout_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"billing of {self.organization}"


class Subscription(models.Model):
    """Our copy of a subscription at Dodo. Only `services.sync` writes it, from what Dodo says."""

    class Status(models.TextChoices):
        PENDING = "pending"
        ACTIVE = "active"
        # A renewal failed and Dodo is trying again; the customer keeps access meanwhile.
        PAST_DUE = "past_due"
        # A renewal failed. A new card (in the portal) brings it back.
        ON_HOLD = "on_hold"
        PAUSED = "paused"
        CANCELLED = "cancelled"
        FAILED = "failed"
        EXPIRED = "expired"

    class Interval(models.TextChoices):
        MONTHLY = "monthly"
        YEARLY = "yearly"

    account = models.ForeignKey(BillingAccount, on_delete=models.CASCADE, related_name="subscriptions")
    provider_id = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices)
    interval = models.CharField(max_length=10, choices=Interval.choices)
    # The end of the last period that was paid for.
    paid_until = models.DateTimeField(null=True, blank=True)
    # They cancelled; it runs until paid_until.
    cancels_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # What a new checkout would duplicate: running, or waiting for a new card.
    OPEN = (Status.ACTIVE, Status.PAST_DUE, Status.ON_HOLD, Status.PAUSED)
    ENDED = (Status.CANCELLED, Status.FAILED, Status.EXPIRED)

    def __str__(self):
        return f"{self.provider_id} ({self.status})"

    @property
    def gives_access(self) -> bool:
        if self.status in (self.Status.ACTIVE, self.Status.PAST_DUE):
            return True
        # Cancelled early: they keep the time they paid for.
        paid = self.paid_until is not None and self.paid_until > timezone.now()
        return self.status == self.Status.CANCELLED and paid
