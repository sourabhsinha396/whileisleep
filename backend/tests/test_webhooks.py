"""The webhooks plugin: signed events out, signed answers in."""

import json
import time

import httpx
import pytest
from django.test import Client

from apps.conversations.models import Message
from apps.conversations.services import add_message, reply_as, request_human, set_status
from apps.integrations.models import Delivery, Integration
from plugins.webhooks import payload, signing
from plugins.webhooks import plugin as webhooks
from whileisleep import outbound

from .factories import ConversationFactory, MembershipFactory, VisitorFactory, WorkspaceFactory

pytestmark = pytest.mark.django_db

URL = "https://hooks.example.com/in"
ALL = ",".join(option.value for option in payload.CHOICES)


class Endpoint:
    """The customer's server."""

    def __init__(self):
        self.requests = []
        self.answers = []

    def handle(self, request):
        self.requests.append(request)
        answer = self.answers.pop(0) if self.answers else httpx.Response(204)
        if isinstance(answer, Exception):
            raise answer
        return answer

    @property
    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.requests]

    @property
    def types(self) -> list[str]:
        return [body["type"] for body in self.bodies]


@pytest.fixture(autouse=True)
def endpoint(monkeypatch, settings):
    settings.SITE_URL = "https://chat.example.com"
    fake = Endpoint()
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda self, request: fake.handle(request))
    monkeypatch.setattr(outbound, "resolve", lambda host, port: ["93.184.216.34"])
    return fake


@pytest.fixture
def base(workspace):
    return f"/workspaces/{workspace.id}/integrations/webhooks"


def connect(api, base, url=URL):
    return api.job(api.post(f"{base}/connect", {"values": {"url": url}}))


@pytest.fixture
def integration(workspace, membership):
    return Integration.objects.create(
        workspace=workspace,
        plugin="webhooks",
        account_id="ep_1",
        account_name="hooks.example.com",
        credentials={"secret": signing.new_secret()},
        config={"url": URL, "events": ALL},
        connected_by=membership.user,
    )


@pytest.fixture
def conversation(workspace):
    visitor = VisitorFactory(workspace=workspace, name="Maya", external_id="u_7", page_title="Orders")
    return ConversationFactory(workspace=workspace, visitor=visitor)


# --- Connecting ---


def test_connecting_makes_a_secret_and_says_where_to_answer(api, base):
    connection_id = connect(api, base)["result"]["connection"]
    (connection,) = api.get(base).json()["connections"]
    assert connection["id"] == connection_id and connection["account_name"] == "hooks.example.com"
    assert connection["settings"]["url"] == URL and not connection["ready"]
    secret, id, address = connection["shown"]
    assert secret["value"].startswith("whsec_") and secret["secret"]
    assert id["value"] == Integration.objects.get().account_id
    assert address["value"] == "https://chat.example.com/api/v1/integrations/webhooks/webhook"


def test_nothing_is_sent_before_events_are_chosen(api, base, conversation, endpoint):
    connect(api, base)
    request_human(conversation)
    assert endpoint.requests == [] and not Delivery.objects.exists()


def test_each_endpoint_has_its_own_secret(api, base):
    for path in "ab":
        connect(api, base, f"{URL}/{path}")
    one, two = Integration.objects.all()
    assert one.credentials["secret"] != two.credentials["secret"] and one.account_id != two.account_id


@pytest.mark.parametrize(
    "url", ["http://example.com", "ftp://example.com", "example.com", "https://", "https://me:pw@example.com"]
)
def test_which_addresses_are_refused(api, base, url):
    assert connect(api, base, url)["error"] and not Integration.objects.exists()


def test_saving_sends_a_test(api, base, integration, endpoint):
    values = {"url": URL, "events": "conversation.resolved", "authorization": "Bearer abc"}
    assert api.job(api.put(f"{base}/{integration.pk}", {"values": values}))["error"] == ""
    (sent,) = endpoint.requests
    assert endpoint.types == ["test"] and sent.headers["Authorization"] == "Bearer abc"
    (connection,) = api.get(base).json()["connections"]
    assert connection["ready"] and connection["secrets"] == ["authorization"]
    assert "abc" not in json.dumps(connection)


@pytest.mark.parametrize("answer", [httpx.Response(404), httpx.ConnectError("no"), httpx.Response(301)])
def test_settings_that_do_not_work_are_not_saved(api, base, integration, endpoint, answer):
    endpoint.answers = [answer]
    error = api.job(api.put(f"{base}/{integration.pk}", {"values": {"url": f"{URL}/new", "events": "note.created"}}))
    assert "nothing was saved" in error["error"]
    integration.refresh_from_db()
    assert integration.config == {"url": URL, "events": ALL}


def test_an_endpoint_inside_our_network_is_refused(api, base, integration, monkeypatch, endpoint):
    monkeypatch.setattr(outbound, "resolve", lambda host, port: ["10.0.0.5"])
    result = api.job(api.put(f"{base}/{integration.pk}", {"values": {"url": URL, "events": "note.created"}}))
    assert "private network" in result["error"] and endpoint.requests == []


# --- Out ---


def test_a_request_can_be_checked_as_standard_webhooks_says(integration, conversation, endpoint):
    request_human(conversation, "refund")
    (sent,) = endpoint.requests
    body = json.loads(sent.content)
    assert sent.headers["webhook-id"] == body["id"]
    secret = integration.credentials["secret"]
    assert signing.is_genuine(secret, sent.headers, sent.content)
    assert not signing.is_genuine(signing.new_secret(), sent.headers, sent.content)
    assert not signing.is_genuine(secret, sent.headers, sent.content + b" ")


def test_the_signature_is_the_one_in_the_specification():
    """The example of https://github.com/standard-webhooks/standard-webhooks."""
    secret = "whsec_MfKQ9r8GKYqrTwjUPD8ILPZIo2LaLaSw"
    body = b'{"test": 2432232314}'
    assert (
        signing.signature(secret, "msg_p5jXN8AQM9LWM0D4loKWxJek", "1614265330", body)
        == "v1,g0hM9SsE+OTPJTGt/tmIKtSyZlE3uFJELVlNIOLJ1OE="
    )


def test_what_an_event_says(integration, conversation, endpoint, workspace, membership):
    conversation.assignee = membership.user
    conversation.tags = ["vip"]
    conversation.save()
    request_human(conversation, "refund")
    (body,) = endpoint.bodies
    assert body["type"] == "conversation.needs_person"
    assert body["workspace"] == {"id": workspace.pk, "name": workspace.name, "slug": workspace.slug}
    chat, contact = body["data"]["conversation"], body["data"]["contact"]
    assert chat["id"] == conversation.pk and chat["needs_person"] and chat["tags"] == ["vip"]
    assert chat["url"] == f"https://chat.example.com/w/{workspace.slug}/inbox?c={conversation.pk}"
    assert chat["assignee"]["email"] == membership.user.email
    assert (contact["name"], contact["external_id"], contact["email_verified"]) == ("Maya", "u_7", False)
    assert contact["page"]["title"] == "Orders" and body["data"]["reason"] == "refund"


def test_messages_say_who_wrote_them(integration, conversation, endpoint, membership):
    add_message(conversation, Message.Sender.VISITOR, "Hi")
    add_message(conversation, Message.Sender.BOT, "Hello")
    reply_as(membership.user, conversation, "I'm here")
    reply_as(membership.user, conversation, "internal", is_note=True)
    add_message(conversation, Message.Sender.SYSTEM, "Bot looked up: secret", is_note=True)
    assert [(b["type"], b["data"]["message"]["from"]) for b in endpoint.bodies] == [
        ("message.created", "visitor"),
        ("message.created", "ai"),
        ("message.created", "teammate"),
        ("note.created", "teammate"),
    ]
    assert endpoint.bodies[2]["data"]["message"]["author"]["email"] == membership.user.email
    assert "secret" not in str(endpoint.bodies)


def test_a_new_chat_from_the_widget(integration, endpoint, anon, workspace, api):
    visitor = VisitorFactory(workspace=workspace)
    anon.visitor_token = visitor.token
    anon.post(f"/widget/{workspace.public_key}/messages", {"body": "Hi"})
    assert endpoint.types[:2] == ["conversation.started", "message.created"]
    anon.post(f"/widget/{workspace.public_key}/messages", {"body": "Again"})
    assert endpoint.types.count("conversation.started") == 1
    endpoint.requests.clear()
    other = VisitorFactory(workspace=workspace)
    api.post(f"/workspaces/{workspace.id}/visitors/{other.pk}/conversations", {"body": "Need help?"})
    assert endpoint.types[0] == "conversation.started" and endpoint.bodies[0]["data"]["by"]


def test_a_visitor_leaving_their_email(integration, endpoint, anon, workspace, conversation):
    anon.visitor_token = conversation.visitor.token
    add_message(conversation, Message.Sender.VISITOR, "Hi")
    anon.post(f"/widget/{workspace.public_key}/actions", {"name": "talk_to_human", "surfaceId": "", "context": {}})
    form = conversation.messages.exclude(form__isnull=True).get()
    surface = form.form["surface_id"]
    context = {"fields": {"email": "maya@example.com"}}
    sent = anon.post(
        f"/widget/{workspace.public_key}/actions", {"name": "submit_form", "surfaceId": surface, "context": context}
    )
    assert sent.status_code == 200
    (body,) = [b for b in endpoint.bodies if b["type"] == "contact.updated"]
    assert body["data"]["changed"] == ["email"] and body["data"]["contact"]["email"] == "maya@example.com"


def test_only_the_chosen_events_are_sent(integration, conversation, endpoint):
    Integration.objects.update(config={"url": URL, "events": "conversation.resolved"})
    request_human(conversation)
    set_status(conversation, "resolved")
    set_status(conversation, "open")
    assert endpoint.types == ["conversation.resolved"]


def test_two_endpoints_hear_about_it_each_once(integration, conversation, endpoint, workspace):
    Integration.objects.create(
        workspace=workspace,
        plugin="webhooks",
        account_id="ep_2",
        credentials={"secret": signing.new_secret()},
        config={"url": f"{URL}/2", "events": "conversation.needs_person"},
    )
    request_human(conversation)
    assert sorted(r.url.path for r in endpoint.requests) == ["/in", "/in/2"]


def test_a_failed_try_is_repeated_with_the_same_id(integration, conversation, endpoint, api, base):
    endpoint.answers = [httpx.Response(500)]
    request_human(conversation)
    delivery = Delivery.objects.get()
    assert (delivery.status, delivery.detail) == ("pending", "The endpoint answered HTTP 500.")
    Delivery.objects.update(status="failed")
    api.post(f"{base}/{integration.pk}/deliveries/{delivery.pk}/again")
    assert len({r.headers["webhook-id"] for r in endpoint.requests}) == 1
    (row,) = api.get(f"{base}/{integration.pk}/deliveries").json()
    assert (row["status"], row["detail"]) == ("sent", "HTTP 204")


@pytest.mark.parametrize(
    ("answer", "retried"),
    [
        (httpx.Response(404), True),
        (httpx.Response(429, headers={"Retry-After": "60"}), True),
        (httpx.Response(503, headers={"Retry-After": "soon"}), True),
        (httpx.ReadTimeout("slow"), True),
        (httpx.Response(410), False),
        (httpx.Response(302, headers={"Location": "https://elsewhere.example"}), False),
    ],
)
def test_which_failures_are_worth_another_try(integration, conversation, endpoint, answer, retried):
    endpoint.answers = [answer]
    request_human(conversation)
    assert Delivery.objects.get().status == ("pending" if retried else "failed")
    assert len(endpoint.requests) == 1


# --- In ---


def answer(integration, data, *, id="m1", secret=None, at=None, headers=None):
    body = json.dumps(data).encode()
    timestamp = str(int(at or time.time()))
    signed = {
        "webhook-endpoint": integration.account_id,
        "webhook-id": id,
        "webhook-timestamp": timestamp,
        "webhook-signature": signing.signature(secret or integration.credentials["secret"], id, timestamp, body),
    } | (headers or {})
    return Client().post("/api/v1/integrations/webhooks/webhook", body, content_type="application/json", headers=signed)


def test_a_reply_reaches_the_visitor(integration, conversation, endpoint, membership):
    sent = answer(integration, {"action": "reply", "conversation_id": conversation.pk, "text": " Refunded! "})
    assert sent.json() == {"ok": True}
    message = conversation.messages.get()
    assert (message.body, message.sender, message.author) == ("Refunded!", "agent", membership.user)
    # The endpoint isn't told what it just said.
    assert endpoint.requests == []


def test_others_hear_what_came_from_one(integration, conversation, endpoint, workspace):
    Integration.objects.create(
        workspace=workspace,
        plugin="webhooks",
        account_id="ep_2",
        credentials={"secret": signing.new_secret()},
        config={"url": f"{URL}/2", "events": ALL},
    )
    answer(integration, {"action": "reply", "conversation_id": conversation.pk, "text": "Hi"})
    assert [r.url.path for r in endpoint.requests] == ["/in/2"]


def test_a_teammate_can_be_named(integration, conversation, workspace):
    other = MembershipFactory(workspace=workspace, role="agent").user
    data = {"action": "note", "conversation_id": conversation.pk, "text": "x", "author_email": other.email.upper()}
    assert answer(integration, data).status_code == 200
    message = conversation.messages.get()
    assert message.author == other and message.is_note
    stranger = MembershipFactory().user
    assert answer(integration, data | {"author_email": stranger.email}, id="m2").status_code == 400
    assert conversation.messages.count() == 1


def test_the_one_who_connected_it_must_still_be_a_member(integration, conversation, membership):
    membership.delete()
    assert answer(integration, {"action": "resolve", "conversation_id": conversation.pk}).status_code == 400


def test_conversations_can_be_changed(integration, conversation, endpoint):
    request_human(conversation)
    endpoint.requests.clear()
    for number, action in enumerate(["resolve", "reopen", "give_to_ai"]):
        data = {"action": action, "conversation_id": conversation.pk}
        assert answer(integration, data, id=f"m{number}").status_code == 200
    conversation.refresh_from_db()
    assert conversation.status == "open" and not conversation.human_requested and endpoint.requests == []


def test_the_same_request_again_does_nothing(integration, conversation):
    data = {"action": "reply", "conversation_id": conversation.pk, "text": "Hi"}
    for _ in range(3):
        assert answer(integration, data).status_code == 200
    assert conversation.messages.count() == 1


def test_another_workspace_s_conversations_are_out_of_reach(integration):
    theirs = ConversationFactory(workspace=WorkspaceFactory())
    data = {"action": "reply", "conversation_id": theirs.pk, "text": "Hi"}
    assert answer(integration, data).status_code == 404 and not theirs.messages.exists()


@pytest.mark.parametrize(
    "data",
    [
        [],
        "x",
        {},
        {"action": "delete", "conversation_id": 1},
        {"action": ["reply"], "conversation_id": 1, "text": "x"},
        {"action": "reply", "conversation_id": 1},
        {"action": "reply", "conversation_id": 1, "text": "  "},
        {"action": "reply", "conversation_id": 1, "text": 5},
        {"action": "reply", "conversation_id": 1, "text": "x" * 10001},
        {"action": "reply", "conversation_id": "1", "text": "x"},
        {"action": "reply", "conversation_id": True, "text": "x"},
        {"action": "reply", "conversation_id": 10**30, "text": "x"},
    ],
)
def test_requests_that_make_no_sense(integration, conversation, data):
    assert answer(integration, data).status_code in (400, 404)
    assert not conversation.messages.exists()


@pytest.mark.parametrize(
    "wrong",
    [
        {"secret": signing.new_secret()},
        {"at": time.time() - 3600},
        {"headers": {"webhook-endpoint": "ep_unknown"}},
        {"headers": {"webhook-endpoint": ""}},
        {"headers": {"webhook-signature": ""}},
        {"headers": {"webhook-signature": "v1,é"}},
        {"headers": {"webhook-timestamp": "soon"}},
        {"headers": {"webhook-id": ""}},
    ],
)
def test_requests_that_are_not_genuine(integration, conversation, wrong):
    data = {"action": "reply", "conversation_id": conversation.pk, "text": "Hi"}
    assert answer(integration, data, **wrong).status_code == 401
    assert not conversation.messages.exists()


def test_a_removed_endpoint_can_no_longer_answer(integration, conversation, api, base):
    api.delete(f"{base}/{integration.pk}")
    data = {"action": "reply", "conversation_id": conversation.pk, "text": "Hi"}
    assert answer(integration, data).status_code == 401


def test_every_event_people_can_choose_exists():
    real = {*payload.TYPES.values(), payload.MESSAGE_CREATED, payload.NOTE_CREATED}
    assert {option.value for option in payload.CHOICES} == real
    assert set(payload.DEFAULT.split(",")) <= real and webhooks.many
