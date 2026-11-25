"""Log in with Google, which also makes the account when there is none. OpenID Connect, with the
authorization code: the browser goes to Google and back, and this server asks Google who it was.

Two cookies, both signed and out of reach of scripts, hold what passes through the browser: what a
login was started with, so nobody can be sent the end of someone else's, and for a minute after it a
ticket the page swaps for its token. Neither ever is in an address.
"""

import logging
import secrets
from urllib.parse import urlencode

import jwt
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.utils.crypto import constant_time_compare

from apps.conversations.limits import hit
from apps.integrations import http
from apps.workspaces.services import organization_for
from whileisleep.client_ip import client_ip

from .models import AuthToken, Profile

log = logging.getLogger(__name__)
User = get_user_model()

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
ISSUERS = ["https://accounts.google.com", "accounts.google.com"]
COOKIE_PATH = "/api/v1/auth/google"
START_COOKIE, START_SECONDS = "google_login", 600
TICKET_COOKIE, TICKET_SECONDS = "google_ticket", 60
# The person waits for Google's answer.
TOTAL_SECONDS = 4
LOGINS_PER_MINUTE = 20


class Refused(Exception):
    """Back to the log-in page, which knows what to say for each of these (frontend/src/lib/google.ts)."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def redirect_uri() -> str:
    return f"{settings.SITE_URL}{COOKIE_PATH}/callback"


def set_cookie(response, name: str, value: str, seconds: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=seconds,
        path=COOKIE_PATH,
        httponly=True,
        secure=settings.SITE_URL.startswith("https://"),
        # Lax, not Strict: coming back from Google is a link from another site.
        samesite="Lax",
    )


# --- The three requests ---


def start() -> HttpResponseRedirect:
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    query = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "prompt": "select_account",
    }
    response = HttpResponseRedirect(f"{AUTHORIZE_URL}?{urlencode(query)}")
    set_cookie(response, START_COOKIE, signing.dumps([state, nonce], salt=START_COOKIE), START_SECONDS)
    return response


def finish(request) -> HttpResponseRedirect:
    try:
        user = user_for(who(request))
    except Refused as refused:
        response = HttpResponseRedirect(f"{settings.SITE_URL}/login?error={refused.reason}")
    else:
        ticket = secrets.token_urlsafe(32)
        cache.set(f"google-ticket:{ticket}", user.pk, TICKET_SECONDS)
        response = HttpResponseRedirect(f"{settings.SITE_URL}/login/google")
        set_cookie(response, TICKET_COOKIE, ticket, TICKET_SECONDS)
    response.delete_cookie(START_COOKIE, path=COOKIE_PATH)
    return response


def swap_ticket(request):
    """The user a ticket was made for, once. None when it is gone."""
    ticket = request.COOKIES.get(TICKET_COOKIE, "")
    key = f"google-ticket:{ticket}"
    user_id = cache.get(key) if ticket else None
    # Deleting says whether it was still there, so of two requests at once only one gets it.
    if user_id is None or not cache.delete(key):
        return None
    return User.objects.filter(pk=user_id, is_active=True).first()


# --- Who it is ---


def who(request) -> dict:
    """Google's claims about who came back, checked."""
    if request.GET.get("error"):
        raise Refused("google_cancelled")
    try:
        state, nonce = signing.loads(request.COOKIES.get(START_COOKIE, ""), salt=START_COOKIE, max_age=START_SECONDS)
    except (signing.BadSignature, ValueError, TypeError):
        raise Refused("google_expired") from None
    code = request.GET.get("code", "")
    if not code or not constant_time_compare(request.GET.get("state", ""), state):
        raise Refused("google_expired")
    if not hit("google", client_ip(request) or "-", LOGINS_PER_MINUTE, 60):
        raise Refused("google_failed")
    return check(id_token(code), nonce)


def id_token(code: str) -> str:
    try:
        response = http.request(
            "POST",
            TOKEN_URL,
            data={
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": redirect_uri(),
            },
            total_seconds=TOTAL_SECONDS,
        )
        answer = response.json()
        if response.status_code != 200:
            # Such as redirect_uri_mismatch or invalid_client: for whoever runs the server.
            log.warning("Google refused a login: %s", str(answer.get("error", ""))[:100])
            raise Refused("google_failed")
        return answer["id_token"]
    except (http.Unreachable, ValueError, KeyError, TypeError, AttributeError) as error:
        log.warning("Google didn't answer a login as expected: %s", type(error).__name__)
        raise Refused("google_failed") from error


def check(token: str, nonce: str) -> dict:
    try:
        # Its signature needs no check: it comes from Google itself, over TLS (OpenID Connect Core, 3.1.3.7).
        claims = jwt.decode(
            token,
            options={
                "verify_signature": False,
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
                "require": ["exp", "aud", "iss", "sub"],
            },
            audience=settings.GOOGLE_CLIENT_ID,
            issuer=ISSUERS,
            leeway=60,
        )
    except jwt.InvalidTokenError as error:
        log.warning("Google's answer to a login is not valid: %s", type(error).__name__)
        raise Refused("google_failed") from error
    if not constant_time_compare(str(claims.get("nonce", "")), nonce):
        raise Refused("google_failed")
    if claims.get("email_verified") is not True or not claims.get("email"):
        raise Refused("google_unverified")
    return claims


def owns_email(claims: dict) -> bool:
    """Whether Google itself runs this mailbox. For any other address it only says that somebody
    once showed it was theirs."""
    return claims["email"].lower().endswith("@gmail.com") or bool(claims.get("hd"))


# --- Whose account it is ---


def user_for(claims: dict):
    """The account of this Google account, made or linked the first time."""
    profile = Profile.objects.select_related("user").filter(google_id=claims["sub"]).first()
    if profile:
        return active(profile.user)
    email = claims["email"].lower()
    try:
        with transaction.atomic():
            user = User.objects.select_for_update().filter(username=email).first()
            return link(user, claims) if user else create(email, claims)
    except IntegrityError:
        # Two logins at once; the other one made it.
        profile = Profile.objects.select_related("user").filter(google_id=claims["sub"]).first()
        if profile is None:
            raise Refused("google_failed") from None
        return active(profile.user)


def active(user):
    if not user.is_active:
        raise Refused("google_failed")
    return user


def create(email: str, claims: dict):
    if not settings.SIGNUP_ENABLED:
        raise Refused("signup_closed")
    name = str(claims.get("name") or email.partition("@")[0])[:150]
    # Without a password nobody can log in with one.
    user = User.objects.create_user(username=email, email=email, password=None, first_name=name)
    Profile.objects.create(user=user, google_id=claims["sub"])
    organization_for(user)
    return user


def link(user, claims: dict):
    """An account with this email exists. Nobody checked whose email it is when it was made, so its
    password may be someone else's, waiting for the owner to arrive: the password and the logins
    made with it end here, and the owner goes on with Google."""
    active(user)
    profile, _ = Profile.objects.get_or_create(user=user)
    # Someone who runs the server keeps their password, for the admin.
    if user.is_staff or user.is_superuser or profile.google_id or not owns_email(claims):
        raise Refused("google_use_password")
    profile.google_id = claims["sub"]
    profile.save(update_fields=["google_id"])
    user.set_unusable_password()
    user.save(update_fields=["password"])
    AuthToken.objects.filter(user=user).delete()
    return user
