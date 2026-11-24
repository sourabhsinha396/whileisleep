import json
import sys

import httpx
import pytest
from botocore.httpsession import URLLib3Session
from django.core.cache import cache
from django.db import transaction
from django.test import Client

from apps.agent import openrouter
from apps.billing import services as billing_services
from whileisleep import outbound

from .factories import AuthTokenFactory, MembershipFactory, OrganizationFactory, UserFactory, WorkspaceFactory
from .fake_dodo import SECRET, FakeDodo
from .fake_s3 import SETTINGS, FakeBucket

# No __pycache__ folders from test runs.
sys.dont_write_bytecode = True


@pytest.fixture(autouse=True)
def clear_cache():
    # Rate-limit counts live in the cache. Without this, one test's requests count against the next.
    cache.clear()


@pytest.fixture(autouse=True)
def on_commit_runs_now(request, monkeypatch):
    """Each test runs in a transaction that is rolled back, never committed, so work queued
    with transaction.on_commit (the AI's reply job) would never start. Run it at once
    instead. Tests marked `django_db(transaction=True)` commit for real and keep the real
    behaviour; test_jobs.py checks that."""
    marker = request.node.get_closest_marker("django_db")
    if marker is None or marker.kwargs.get("transaction"):
        return
    monkeypatch.setattr(transaction, "on_commit", lambda function, using=None, robust=False: function())


@pytest.fixture(autouse=True)
def no_real_http(monkeypatch):
    """Fail any test that reaches a real service. Fake the call instead. RuntimeError, not an
    httpx error, so code that handles network errors can't hide it."""

    def refuse(self, request):
        raise RuntimeError(f"Test tried a real HTTP request: {request.method} {request.url}. Mock it.")

    def refuse_s3(self, request):
        raise RuntimeError(f"Test tried a real S3 request: {request.method} {request.url}. Mock it.")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
    monkeypatch.setattr(URLLib3Session, "send", refuse_s3)


@pytest.fixture
def fake_redis(monkeypatch):
    """Real-time features on an in-memory Redis. The sync client (publishers, presence) and
    every async client (streams) share one fake server, so pub/sub crosses between them."""
    import fakeredis
    import fakeredis.aioredis

    from apps.realtime import bus

    # redis-py 8.2's asyncio client checks writer.transport.is_closing() before each command;
    # fakeredis 2.34's fake writer has no transport. (Later fakeredis releases fix that but
    # break the sync client on redis-py 8.2.)
    class Transport:
        def __init__(self, writer):
            self.writer = writer

        def is_closing(self):
            return self.writer._socket is None

    monkeypatch.setattr(fakeredis.aioredis.FakeWriter, "transport", property(Transport), raising=False)

    server = fakeredis.FakeServer()
    sync = fakeredis.FakeRedis(server=server)
    monkeypatch.setattr(bus, "client", lambda: sync)
    monkeypatch.setattr(bus, "async_client", lambda: fakeredis.FakeAsyncRedis(server=server))
    return sync


class Listener:
    """Subscribes to channels on the fake Redis and collects what is published there."""

    def __init__(self, connection, *channels):
        self.pubsub = connection.pubsub()
        self.pubsub.subscribe(*channels)

    def events(self) -> list[dict]:
        found = []
        while (message := self.pubsub.get_message(timeout=0.01)) is not None:
            if message["type"] == "message":
                found.append(json.loads(message["data"]))
        return found

    def names(self) -> list[str]:
        return [e["event"] for e in self.events()]


@pytest.fixture
def listen(fake_redis):
    return lambda *channels: Listener(fake_redis, *channels)


class Api:
    """Django test client that speaks JSON and sends a bearer or visitor token."""

    def __init__(self, token: str = "", visitor_token: str = ""):
        self.client = Client()
        self.token = token
        self.visitor_token = visitor_token

    def _headers(self):
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.visitor_token:
            headers["X-Visitor-Token"] = self.visitor_token
        return headers

    def request(self, method: str, path: str, data=None):
        kwargs = {"headers": self._headers()}
        if data is not None:
            kwargs |= {"data": json.dumps(data), "content_type": "application/json"}
        return getattr(self.client, method)(f"/api/v1{path}", **kwargs)

    def get(self, path, **params):
        query = "&".join(f"{k}={v}" for k, v in params.items())
        return self.request("get", f"{path}?{query}" if query else path)

    def post(self, path, data=None):
        return self.request("post", path, data if data is not None else {})

    def upload(self, path, file):
        """POSTs a file as a browser's form does."""
        return self.client.post(f"/api/v1{path}", {"file": file}, headers=self._headers())

    def put(self, path, data):
        return self.request("put", path, data)

    def patch(self, path, data):
        return self.request("patch", path, data)

    def delete(self, path):
        return self.request("delete", path)


@pytest.fixture
def membership(db):
    """The owner of a fresh workspace, who also owns its organization."""
    user = UserFactory()
    workspace = WorkspaceFactory(organization=OrganizationFactory(owner=user))
    return MembershipFactory(user=user, workspace=workspace)


@pytest.fixture
def workspace(membership):
    return membership.workspace


@pytest.fixture
def api(membership):
    """Signed in as the workspace owner."""
    return Api(token=AuthTokenFactory(user=membership.user).key)


@pytest.fixture
def anon():
    return Api()


# --- A customer's bucket ---


@pytest.fixture
def s3(monkeypatch):
    """A customer's bucket in memory. Requests run through real httpx and stop at the socket."""
    fake = FakeBucket()
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda self, request: fake.handle(request))
    monkeypatch.setattr(outbound, "resolve", lambda host, port: ["93.184.216.34"])
    return fake


@pytest.fixture
def connected(api, s3):
    """`s3`, connected to the owner's organization."""
    assert api.put("/organization/storage", SETTINGS).status_code == 200
    s3.requests.clear()
    return s3


# --- Fake OpenRouter ---


def tool_call(name: str, arguments: dict, id: str = "call_1") -> dict:
    return {"id": id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


def assistant(*calls: dict, content: str | None = None) -> dict:
    """An assistant message as OpenRouter returns it (choices[0].message)."""
    return {"role": "assistant", "content": content, "tool_calls": list(calls) or None}


def final(reply: str, article_ids=(), offer_human=False) -> dict:
    """The model finishing with reply_to_visitor."""
    args = {"reply": reply, "article_ids": list(article_ids), "offer_human": offer_human}
    return assistant(tool_call("reply_to_visitor", args, id="call_final"))


class FakeOpenRouter:
    """Returns scripted messages in order and records each request. Each response counts as
    `usage` tokens, so tests can check what a reply cost."""

    def __init__(self, responses, usage=None):
        self.responses = list(responses)
        self.requests = []
        self.usage = usage or {"input_tokens": 100, "cached_tokens": 0, "output_tokens": 20}

    def complete(self, api_key, model, messages, tools):
        # Copy the messages: the bot appends to the same list after the call.
        self.requests.append({"api_key": api_key, "model": model, "messages": list(messages), "tools": tools})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return openrouter.Completion(message=response, **self.usage)


@pytest.fixture
def llm(monkeypatch):
    """Install a fake OpenRouter. Call it with the scripted assistant messages. The
    conversation's organization must be ready (OrganizationFactory(ready=True))."""

    def install(*responses, usage=None):
        fake = FakeOpenRouter(responses, usage)
        monkeypatch.setattr(openrouter, "complete", fake.complete)
        return fake

    return install


# --- Payments ---


@pytest.fixture
def billing(settings, monkeypatch):
    """Billing switched on."""
    settings.BILLING_ENABLED = True
    settings.PAYMENT_PROVIDER = "dodo"
    settings.DODO_BASE_URL = "https://test.dodopayments.com"
    settings.DODO_API_KEY = "dodo-key"
    settings.DODO_PRODUCT_MONTHLY, settings.DODO_PRODUCT_YEARLY = "pdt_m", "pdt_y"
    settings.DODO_WEBHOOK_KEY = SECRET
    settings.SITE_URL = "https://chat.example.com"
    fake = FakeDodo()
    monkeypatch.setattr(
        httpx.HTTPTransport, "handle_request", lambda transport, request: fake.handle(transport, request)
    )
    return fake


@pytest.fixture
def account(billing, workspace):
    return billing_services.account_for(workspace.organization)
