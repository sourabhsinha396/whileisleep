from urllib.parse import parse_qs

import httpx
import pytest
from django.contrib.auth.models import User

from apps.accounts import captcha
from apps.integrations import http

from .factories import UserFactory

pytestmark = pytest.mark.django_db

SIGNUP = {"name": "Ana", "email": "ana@example.com", "password": "longpassword"}


@pytest.fixture
def google(settings, monkeypatch):
    """reCAPTCHA on, with a Google that answers `google.answer`."""
    settings.RECAPTCHA_SITE_KEY, settings.RECAPTCHA_SECRET_KEY = "site-key", "secret-key"
    settings.RECAPTCHA_ENABLED = True

    class Google:
        answer = {"success": True}
        error = None
        status = 200
        asked: list[dict] = []

    Google.asked = []

    def handle(self, request):
        assert str(request.url) == captcha.VERIFY_URL
        Google.asked.append({key: value[0] for key, value in parse_qs(request.content.decode()).items()})
        if Google.error:
            raise Google.error
        return httpx.Response(Google.status, json=Google.answer, request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    return Google


def test_without_keys_there_is_none(anon):
    assert anon.get("/auth/captcha").json() == {"site_key": ""}
    assert anon.post("/auth/signup", SIGNUP).status_code == 200


def test_the_page_gets_the_site_key_only(anon, google):
    response = anon.get("/auth/captcha")
    assert response.json() == {"site_key": "site-key"}
    assert "secret-key" not in response.content.decode()


def test_signup_and_login_with_a_ticked_box(anon, google):
    assert anon.post("/auth/signup", {**SIGNUP, "captcha": "t1"}).status_code == 200
    login = {"email": SIGNUP["email"], "password": SIGNUP["password"], "captcha": "t2"}
    assert anon.post("/auth/login", login).status_code == 200
    assert google.asked == [{"secret": "secret-key", "response": "t1"}, {"secret": "secret-key", "response": "t2"}]


@pytest.mark.parametrize("path", ["/auth/signup", "/auth/login"])
def test_an_unticked_box_is_refused_without_asking_google(anon, google, path):
    response = anon.post(path, SIGNUP)
    assert response.status_code == 400
    assert "Tick the box" in response.json()["detail"]
    assert google.asked == []


@pytest.mark.parametrize("path", ["/auth/signup", "/auth/login"])
def test_what_google_refuses_is_refused(anon, google, path):
    UserFactory(email="bo@example.com")
    google.answer = {"success": False, "error-codes": ["timeout-or-duplicate"]}
    assert anon.post(path, {**SIGNUP, "captcha": "old"}).status_code == 400
    assert not User.objects.filter(username=SIGNUP["email"]).exists()


def test_a_right_password_doesnt_replace_the_box(anon, google):
    user = UserFactory(email="bo@example.com")
    user.set_password("longpassword")
    user.save()
    google.answer = {"success": False}
    assert (
        anon.post("/auth/login", {"email": "bo@example.com", "password": "longpassword", "captcha": "t"}).status_code
        == 400
    )


@pytest.mark.parametrize("answer", [[], {}, "no", None, {"success": "yes"}])
def test_only_a_plain_yes_counts(anon, google, answer):
    google.answer = answer
    assert anon.post("/auth/signup", {**SIGNUP, "captcha": "t"}).status_code in (400, 503)


def test_nobody_gets_in_while_google_is_down(anon, google):
    google.error = httpx.ConnectTimeout("slow")
    for _ in range(http.FAILURES + 2):
        assert anon.post("/auth/signup", {**SIGNUP, "captcha": "t"}).status_code == 503
    # After a few, it counts as down and no thread waits for it.
    assert len(google.asked) == http.FAILURES


def test_tries_are_limited(anon, google):
    google.answer = {"success": False}
    for _ in range(captcha.CHECKS_PER_MINUTE):
        assert anon.post("/auth/login", {**SIGNUP, "captcha": "t"}).status_code == 400
    assert anon.post("/auth/login", {**SIGNUP, "captcha": "t"}).status_code == 429
    assert len(google.asked) == captcha.CHECKS_PER_MINUTE


def test_a_wrong_secret_is_logged(anon, google, caplog):
    google.answer = {"success": False, "error-codes": ["invalid-input-secret"]}
    anon.post("/auth/login", {**SIGNUP, "captcha": "t"})
    assert "RECAPTCHA_SECRET_KEY" in caplog.text
    assert "secret-key" not in caplog.text
