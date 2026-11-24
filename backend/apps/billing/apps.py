from django.apps import AppConfig
from django.conf import settings
from django.core import checks


class BillingConfig(AppConfig):
    name = "apps.billing"
    default_auto_field = "django.db.models.BigAutoField"


@checks.register
def half_configured(app_configs, **kwargs):
    """Says so instead of leaving billing silently off (production refuses to start instead)."""
    if not settings.PAYMENT_PROVIDER or settings.BILLING_ENABLED:
        return []
    missing = ", ".join(settings.BILLING_MISSING)
    return [
        checks.Warning(
            f"PAYMENT_PROVIDER is set but these are empty: {missing}. Billing is off.",
            hint="manage.py billing_setup makes the products and prints what to add.",
            id="billing.W001",
        )
    ]
