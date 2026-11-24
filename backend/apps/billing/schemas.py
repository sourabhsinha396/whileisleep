from datetime import datetime
from typing import Literal

from ninja import Schema
from pydantic import Field

Interval = Literal["monthly", "yearly"]


class SubscriptionOut(Schema):
    status: str
    interval: Interval
    paid_until: datetime | None
    cancels_at_period_end: bool


class BillingOut(Schema):
    state: Literal["off", "trial", "active", "paused"]
    trial_days_left: int | None
    trial_ends_at: datetime | None
    # Has paid before, so there is a portal to open.
    can_manage: bool
    subscription: SubscriptionOut | None
    # In US cents, before tax.
    prices: dict[Interval, int]


class CheckoutIn(Schema):
    interval: Interval
    # The slug of the workspace they are in, to come back to.
    workspace: str


class PortalIn(Schema):
    workspace: str


class SyncIn(Schema):
    # What checkout came back with; without it, whatever this organization has at Dodo. Goes into
    # an address at Dodo, so nothing but an id.
    subscription_id: str | None = Field(None, pattern=r"^sub_[A-Za-z0-9]+$", max_length=64)


class LinkOut(Schema):
    url: str
