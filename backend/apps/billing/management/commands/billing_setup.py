from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.billing import dodo
from apps.billing.models import Subscription
from apps.billing.services import PRICES

# Marks our products, in a Dodo account that may sell others.
PLAN_KEY = "whileisleep_plan"
WEBHOOK_PATH = "/api/v1/billing/webhooks/dodo"
EVENTS = [
    f"subscription.{name}"
    for name in (
        "active",
        "renewed",
        "on_hold",
        "past_due",
        "paused",
        "unpaused",
        "cancelled",
        "failed",
        "expired",
        "plan_changed",
        "updated",
    )
]


def product_body(interval: str, brand: str = "") -> dict:
    body = {
        "name": f"whileisleep Cloud ({interval})",
        "description": "Hosted whileisleep: live chat with your own AI key.",
        "tax_category": "saas",
        "metadata": {PLAN_KEY: interval},
        "price": {
            "type": "recurring_price",
            "currency": "USD",
            "price": PRICES[interval],
            "payment_frequency_count": 1,
            "payment_frequency_interval": "Month" if interval == Subscription.Interval.MONTHLY else "Year",
            # How long it renews for in all, not the billing cycle.
            "subscription_period_count": 20,
            "subscription_period_interval": "Year",
            "tax_inclusive": False,
        },
    }
    return body | ({"brand_id": brand} if brand else {})


class Command(BaseCommand):
    help = (
        "Finds whileisleep's plans and webhook in the Dodo account and prints the settings for .env. "
        "Changes nothing unless --create is given, which makes the missing ones."
    )

    def add_arguments(self, parser):
        parser.add_argument("--create", action="store_true", help="Make the products and the webhook if missing.")
        parser.add_argument("--brand", default="", help="The Dodo brand id customers see (brnd_...).")

    def handle(self, *args, **options):
        if not (settings.DODO_BASE_URL and settings.DODO_API_KEY):
            raise CommandError("Set DODO_BASE_URL and DODO_API_KEY first.")
        mode = "test" if "//test." in settings.DODO_BASE_URL else "LIVE"
        self.stdout.write(f"Dodo account, {mode} mode.")
        try:
            lines = self.products(**options) + self.webhook(**options)
        except dodo.DodoError as error:
            raise CommandError(str(error)) from error
        if lines:
            self.stdout.write("\nPut these in .env:")
            for line in lines:
                self.stdout.write(line)

    def products(self, create: bool, brand: str, **options) -> list[str]:
        existing = {p["metadata"][PLAN_KEY]: p for p in dodo.list_products() if (p.get("metadata") or {}).get(PLAN_KEY)}
        lines = []
        for interval, price in PRICES.items():
            found = existing.get(interval.value)
            label = f"{interval.value.title()} plan, ${price / 100:g}"
            if found:
                product_id = found["product_id"]
                self.stdout.write(f"{label}: {product_id}")
                if found.get("price") != price:
                    # Never changed from here: people are already paying it.
                    self.stdout.write(self.style.WARNING(f"  Its price at Dodo is {found.get('price')} cents."))
            elif create:
                product_id = dodo.create_product(product_body(interval.value, brand))
                self.stdout.write(f"{label}: made {product_id}")
            else:
                self.stdout.write(f"{label}: missing (--create makes it)")
                continue
            lines.append(f"DODO_PRODUCT_{interval.name}={product_id}")
        return lines

    def webhook(self, create: bool, **options) -> list[str]:
        if not settings.SITE_URL.startswith("https://"):
            self.stdout.write("Webhook: skipped, Dodo can't reach this machine. Plans update when someone returns.")
            return []
        url = settings.SITE_URL + WEBHOOK_PATH
        webhook_id = next((w["id"] for w in dodo.list_webhooks() if w.get("url") == url), None)
        if webhook_id is None:
            if not create:
                self.stdout.write(f"Webhook to {url}: missing (--create makes it)")
                return []
            webhook_id = dodo.create_webhook(url, EVENTS)
        self.stdout.write(f"Webhook to {url}: {webhook_id}")
        return [f"DODO_WEBHOOK_KEY={dodo.webhook_secret(webhook_id)}"]
