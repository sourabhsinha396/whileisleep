"""A forgotten password: a link by email, good once and for an hour, to choose a new one.

The answer never says whether an address has an account. The link's secret is after the "#", which a
browser keeps to itself, so it is in no server's log.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from whileisleep.mail import Mail

from .models import AuthToken

User = get_user_model()


def reset_mail(email: str) -> Mail | None:
    """The email for whoever has this address. None: nobody has."""
    user = User.objects.filter(username=email.lower(), is_active=True).first()
    if user is None:
        return None
    key = f"{urlsafe_base64_encode(force_bytes(user.pk))}.{default_token_generator.make_token(user)}"
    return Mail(
        to=user.email,
        subject="Choose a new password",
        lines=["Someone asked for a new password for your whileisleep account. If it was you, choose one here:"],
        button=("Choose a new password", f"{settings.SITE_URL}/reset-password#{key}"),
        note="The link works once, for one hour. If it wasn't you, ignore this email: your password stays as it is.",
    )


def changed_mail(email: str) -> Mail:
    return Mail(
        to=email,
        subject="Your password was changed",
        lines=[
            "The password of your whileisleep account was just changed, and every other device was logged out.",
        ],
        note=f"If it wasn't you, choose a new one now: {settings.SITE_URL}/forgot-password",
    )


@transaction.atomic
def reset(key: str, password: str):
    """The user, with the new password and without the old logins. None when the link is no good."""
    uid, _, token = key.partition(".")
    try:
        pk = int(force_str(urlsafe_base64_decode(uid)))
        # Locked, so the same link can't be used twice at the same moment.
        user = User.objects.select_for_update().get(pk=pk, is_active=True)
    except (ValueError, OverflowError, User.DoesNotExist):
        return None
    if not default_token_generator.check_token(user, token):
        return None
    user.set_password(password)
    user.save(update_fields=["password"])
    AuthToken.objects.filter(user=user).delete()
    return user
