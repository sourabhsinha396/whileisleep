import json
from datetime import timedelta

import httpx
import pytest
from django.contrib.auth.models import User
from django.contrib.auth.tokens import PasswordResetTokenGenerator

from apps.accounts import apis, tasks
from apps.accounts.models import AuthToken
from whileisleep import mail as mails

from .conftest import Api
from .factories import AuthTokenFactory, UserFactory

pytestmark = pytest.mark.django_db

NEW = "a-brand-new-password"


@pytest.fixture
def brevo(settings, monkeypatch):
    """Mail on, with a Brevo that keeps what it was given."""
    settings.BREVO_API_KEY, settings.MAIL_FROM, settings.MAIL_FROM_NAME = "brevo-key", "hi@wis.test", "whileisleep"
    settings.MAIL_ENABLED, settings.SITE_URL = True, "https://chat.example.com"

    class Brevo:
        status = 201
        body = {"messageId": "1"}
        error = None
        sent: list[dict] = []

    Brevo.sent = []

    def handle(self, request):
        assert str(request.url) == mails.SEND_URL
        assert request.headers["api-key"] == "brevo-key"
        Brevo.sent.append(json.loads(request.content))
        if Brevo.error:
            raise Brevo.error
        return httpx.Response(Brevo.status, json=Brevo.body, request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    return Brevo


@pytest.fixture
def user():
    return UserFactory(email="ana@example.com")


def forgot(email="ana@example.com"):
    return Api().post("/auth/password/forgot", {"email": email})


def key_in(mail: dict) -> str:
    text = mail["textContent"]
    return text[text.index("/reset-password#") + len("/reset-password#") :].split()[0]


def reset(key: str, password=NEW):
    return Api().post("/auth/password/reset", {"key": key, "password": password})


def test_off_without_mail(anon, user):
    assert anon.get("/auth/password").json() == {"can_reset": False}
    assert forgot().status_code == 404


def test_the_whole_way(anon, brevo, user):
    AuthTokenFactory(user=user)
    assert anon.get("/auth/password").json() == {"can_reset": True}
    assert forgot("Ana@Example.com").status_code == 200
    mail = brevo.sent[0]
    assert mail["to"] == [{"email": "ana@example.com"}]
    assert mail["sender"] == {"email": "hi@wis.test", "name": "whileisleep"}
    assert "https://chat.example.com/reset-password#" in mail["htmlContent"]

    done = reset(key_in(mail))
    assert done.status_code == 200
    # Logged in here, and nowhere else.
    assert list(AuthToken.objects.filter(user=user).values_list("key", flat=True)) == [done.json()["token"]]
    old, new = ({"email": user.email, "password": password} for password in ("password123", NEW))
    assert anon.post("/auth/login", old).status_code == 401
    assert anon.post("/auth/login", new).status_code == 200
    assert brevo.sent[1]["subject"] == "Your password was changed"


def test_nobody_learns_who_has_an_account(brevo, user):
    known, unknown = forgot(), forgot("nobody@example.com")
    assert (known.status_code, known.content) == (unknown.status_code, unknown.content)
    assert len(brevo.sent) == 1


def test_a_closed_account_gets_no_mail(brevo, user):
    User.objects.update(is_active=False)
    assert forgot().status_code == 200
    assert brevo.sent == []


def test_an_account_made_with_google_can_choose_a_password(anon, brevo, user):
    user.set_unusable_password()
    user.save()
    forgot()
    assert reset(key_in(brevo.sent[0])).status_code == 200
    assert anon.post("/auth/login", {"email": user.email, "password": NEW}).status_code == 200


def test_a_link_works_once(brevo, user):
    forgot()
    key = key_in(brevo.sent[0])
    assert reset(key).status_code == 200
    assert reset(key, "another-password").status_code == 400


def test_using_a_link_ends_the_others(brevo, user):
    forgot()
    forgot()
    first, second = (key_in(mail) for mail in brevo.sent)
    reset(second)
    assert reset(first, "another-password").status_code == 400


def test_a_link_ends_after_an_hour(brevo, user, monkeypatch):
    forgot()
    now = PasswordResetTokenGenerator._now
    monkeypatch.setattr(PasswordResetTokenGenerator, "_now", lambda self: now(self) + timedelta(minutes=61))
    assert reset(key_in(brevo.sent[0])).status_code == 400


def test_a_link_is_for_one_account(brevo, user):
    other = UserFactory(email="bo@example.com")
    forgot()
    forgot(other.email)
    mine, theirs = (key_in(mail).split(".") for mail in brevo.sent)
    assert reset(f"{theirs[0]}.{mine[1]}").status_code == 400


@pytest.mark.parametrize("key", ["", "x", ".", "MQ.", "w7w.x", "!!!.x", "OTk5OTk5OTk5OTk5OTk5OTk5OTk5.x", "MQ.a-b-c"])
def test_made_up_links(brevo, user, key):
    assert reset(key).status_code == 400


def test_a_short_password_is_refused(brevo, user):
    forgot()
    assert reset(key_in(brevo.sent[0]), "short").status_code == 422


def test_one_address_gets_only_so_many(brevo, user):
    for _ in range(apis.RESETS_PER_EMAIL + 2):
        # The same answer, so the limit doesn't say anything either.
        assert forgot().status_code == 200
    assert len(brevo.sent) == apis.RESETS_PER_EMAIL


def test_one_visitor_may_ask_only_so_often(brevo):
    for number in range(apis.RESETS_PER_ADDRESS):
        assert forgot(f"u{number}@example.com").status_code == 200
    assert forgot("last@example.com").status_code == 429


def test_the_robot_check_is_there_too(brevo, user, settings):
    settings.RECAPTCHA_ENABLED = True
    assert forgot().status_code == 400
    assert brevo.sent == []


# --- Sending ---


def message(**changes):
    return mails.Mail(**{"to": "a@x.test", "subject": "S", "lines": ["Hi"]} | changes)


def test_what_is_in_a_mail_is_escaped():
    html = message(lines=["<b>"], button=("Go", 'https://x.test/?a=1&b="')).html()
    assert "<b>" not in html
    assert "a=1&amp;b=&quot;" in html


@pytest.mark.parametrize("problem", [429, 500, 503, "unreachable"])
def test_a_brevo_that_is_down_is_worth_another_try(brevo, problem):
    if problem == "unreachable":
        brevo.error = httpx.ConnectTimeout("slow")
    else:
        brevo.status = problem
    with pytest.raises(mails.NotSent):
        mails.send(message())


def test_retries_end(brevo, user):
    brevo.status = 500
    # Celery's own retries, each at once.
    conf = tasks.send_reset.app.conf
    before, conf.task_eager_propagates = conf.task_eager_propagates, False
    try:
        tasks.send_reset.delay(user.email)
    finally:
        conf.task_eager_propagates = before
    assert len(brevo.sent) == len(tasks.DELAYS) + 1


def test_what_brevo_refuses_is_logged_and_left(brevo, caplog):
    brevo.status, brevo.body = 401, {"message": "Key not found"}
    mails.send(message())
    assert "Key not found" in caplog.text
    assert "brevo-key" not in caplog.text
