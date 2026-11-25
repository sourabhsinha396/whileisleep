import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from django.contrib.auth.models import User
from django.core.cache import cache

from apps.accounts import google as google_login
from apps.accounts.models import AuthToken, Profile
from apps.workspaces.models import Organization

from .conftest import Api
from .factories import AuthTokenFactory, UserFactory

pytestmark = pytest.mark.django_db

SITE = "https://chat.example.com"


class Google:
    """Google's side: answers the code with an ID token."""

    def __init__(self):
        self.claims = {
            "iss": "https://accounts.google.com",
            "aud": "client-id",
            "sub": "1001",
            "email": "Ana@gmail.com",
            "email_verified": True,
            "name": "Ana",
        }
        self.status, self.error, self.asked = 200, None, []
        self.nonce = ""
        self.lasts = 3600

    def handle(self, _, request):
        assert str(request.url) == google_login.TOKEN_URL
        self.asked.append({key: value[0] for key, value in parse_qs(request.content.decode()).items()})
        if self.error:
            raise self.error
        claims = {"nonce": self.nonce, "exp": int(time.time()) + self.lasts} | self.claims
        token = jwt.encode(claims, "k" * 32, algorithm="HS256")
        return httpx.Response(self.status, json={"id_token": token, "error": "x"}, request=request)


@pytest.fixture
def google(settings, monkeypatch):
    settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET = "client-id", "client-secret"
    settings.GOOGLE_ENABLED, settings.SITE_URL = True, SITE
    fake = Google()
    monkeypatch.setattr(
        httpx.HTTPTransport, "handle_request", lambda transport, request: fake.handle(transport, request)
    )
    return fake


def log_in(google, api=None, **changes):
    """There and back: the page's response, in a browser of its own."""
    api = api or Api()
    sent = {k: v[0] for k, v in parse_qs(urlparse(api.get("/auth/google/start")["Location"]).query).items()}
    google.nonce = sent["nonce"]
    return api, api.get("/auth/google/callback", **({"state": sent["state"], "code": "c"} | changes))


def token_of(api) -> str:
    response = api.post("/auth/google/session")
    assert response.status_code == 200, response.content
    return response.json()["token"]


def refused(response) -> str:
    assert response.status_code == 302
    return response["Location"].removeprefix(f"{SITE}/login?error=")


def test_off_without_keys(anon):
    assert anon.get("/auth/google").json() == {"enabled": False}
    for response in (
        anon.get("/auth/google/start"),
        anon.get("/auth/google/callback"),
        anon.post("/auth/google/session"),
    ):
        assert response.status_code == 404


def test_sends_the_browser_to_google(anon, google):
    assert anon.get("/auth/google").json() == {"enabled": True}
    response = anon.get("/auth/google/start")
    address = urlparse(response["Location"])
    query = parse_qs(address.query)
    assert address.netloc == "accounts.google.com"
    assert query["redirect_uri"] == [f"{SITE}/api/v1/auth/google/callback"]
    assert query["scope"] == ["openid email profile"]
    assert "client-secret" not in response["Location"]
    cookie = response.cookies[google_login.START_COOKIE]
    assert cookie["httponly"] and cookie["secure"] and cookie["samesite"] == "Lax"


def test_the_first_time_makes_an_account(google):
    api, response = log_in(google)
    assert response["Location"] == f"{SITE}/login/google"
    me = Api(token=token_of(api)).get("/auth/me").json()
    assert (me["email"], me["name"]) == ("ana@gmail.com", "Ana")
    user = User.objects.get()
    assert not user.has_usable_password()
    assert Organization.objects.filter(owner=user).exists()
    assert google.asked[0]["client_secret"] == "client-secret"


def test_the_next_time_is_the_same_account_whatever_the_email(google):
    log_in(google)
    google.claims["email"] = "new@gmail.com"
    api, _ = log_in(google)
    token_of(api)
    assert User.objects.get().email == "ana@gmail.com"


def test_no_token_is_ever_in_an_address(google):
    api, response = log_in(google)
    ticket = response.cookies[google_login.TICKET_COOKIE]
    assert ticket["httponly"] and ticket.value not in response["Location"]


def test_a_ticket_is_good_once(google):
    api, _ = log_in(google)
    ticket = api.client.cookies[google_login.TICKET_COOKIE].value
    token_of(api)
    api.client.cookies[google_login.TICKET_COOKIE] = ticket
    assert api.post("/auth/google/session").status_code == 401


def test_a_session_needs_the_browser_that_logged_in(google):
    log_in(google)
    assert Api().post("/auth/google/session").status_code == 401
    assert AuthToken.objects.count() == 0


def test_a_ticket_ends(google):
    api, _ = log_in(google)
    cache.clear()
    assert api.post("/auth/google/session").status_code == 401


def test_another_browsers_login_cant_be_finished(google):
    _, response = log_in(google, state="someone-elses")
    assert refused(response) == "google_expired"
    assert refused(Api().get("/auth/google/callback", state="s", code="c")) == "google_expired"
    assert google.asked == []


def test_cancelling(google):
    _, response = log_in(google, error="access_denied")
    assert refused(response) == "google_cancelled"


@pytest.mark.parametrize(
    "changes",
    [{"aud": "another-app"}, {"iss": "https://evil.example.com"}, {"nonce": "replayed"}, {"exp": 1}],
)
def test_claims_not_meant_for_this_login_are_refused(google, changes):
    google.claims |= changes
    _, response = log_in(google)
    assert refused(response) == "google_failed"
    assert not User.objects.exists()


@pytest.mark.parametrize("verified", [False, None, "true"])
def test_an_unverified_email_is_refused(google, verified):
    google.claims["email_verified"] = verified
    assert refused(log_in(google)[1]) == "google_unverified"


def test_google_refusing_or_not_answering(google):
    google.status = 400
    assert refused(log_in(google)[1]) == "google_failed"
    google.error = httpx.ConnectTimeout("slow")
    assert refused(log_in(google)[1]) == "google_failed"


def test_closed_sign_up_still_lets_people_in(google, settings):
    log_in(google)
    settings.SIGNUP_ENABLED = False
    token_of(log_in(google)[0])
    google.claims |= {"sub": "2002", "email": "bo@gmail.com"}
    assert refused(log_in(google)[1]) == "signup_closed"
    assert User.objects.count() == 1


def test_a_password_account_is_linked_and_its_password_ends(google):
    """Whoever made it never showed that the email was theirs."""
    user = UserFactory(email="ana@gmail.com")
    AuthTokenFactory(user=user)
    api, _ = log_in(google)
    token_of(api)
    user.refresh_from_db()
    assert User.objects.count() == 1
    assert user.profile.google_id == "1001"
    assert not user.has_usable_password()
    # Only the one they just got.
    assert AuthToken.objects.filter(user=user).count() == 1
    old = {"email": "ana@gmail.com", "password": "password123"}
    assert Api().post("/auth/login", old).status_code == 401


def test_a_company_mailbox_at_google_is_linked(google):
    user = UserFactory(email="ana@company.com")
    google.claims |= {"email": "ana@company.com", "hd": "company.com"}
    token_of(log_in(google)[0])
    assert Profile.objects.get(user=user).google_id == "1001"


@pytest.mark.parametrize("who", ["mailbox elsewhere", "superuser", "other google account"])
def test_accounts_that_keep_their_password(google, who):
    user = UserFactory(email="ana@gmail.com")
    if who == "mailbox elsewhere":
        User.objects.update(email="ana@elsewhere.com", username="ana@elsewhere.com")
        google.claims["email"] = "ana@elsewhere.com"
    elif who == "superuser":
        User.objects.update(is_superuser=True)
    else:
        Profile.objects.create(user=user, google_id="9")
    assert refused(log_in(google)[1]) == "google_use_password"
    user.refresh_from_db()
    assert user.check_password("password123")


def test_a_closed_account_stays_closed(google):
    log_in(google)
    User.objects.update(is_active=False)
    assert refused(log_in(google)[1]) == "google_failed"


def test_an_account_closed_meanwhile_gets_no_token(google):
    api, _ = log_in(google)
    User.objects.update(is_active=False)
    assert api.post("/auth/google/session").status_code == 401


def test_logins_are_limited(google):
    for _ in range(google_login.LOGINS_PER_MINUTE):
        log_in(google)
    assert refused(log_in(google)[1]) == "google_failed"
