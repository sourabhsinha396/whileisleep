"""Calls to outside services (apps.integrations.http): none may keep a thread for long."""

import gzip
import time

import httpx
import pytest

from apps.integrations import http
from apps.integrations.plugin import PluginError
from whileisleep import outbound

URL = "https://api.example.com/do"


class Service:
    """Answers with what it is given, and counts."""

    def __init__(self, monkeypatch):
        self.answer = httpx.Response(200, json={"ok": True})
        self.calls = []
        monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda transport, request: self.handle(request))

    def handle(self, request):
        self.calls.append(request)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


@pytest.fixture
def service(monkeypatch):
    return Service(monkeypatch)


class Drip(httpx.SyncByteStream):
    """A body that comes in small pieces, taking its time."""

    def __init__(self, pieces=1000, seconds=0.01, size=1):
        self.pieces, self.seconds, self.size = pieces, seconds, size
        self.sent = 0

    def __iter__(self):
        for _ in range(self.pieces):
            time.sleep(self.seconds)
            self.sent += 1
            yield b"x" * self.size


def test_an_answer_whatever_its_status(service):
    service.answer = httpx.Response(418, json={"tea": True})
    response = http.request("POST", URL, json={"a": 1}, headers={"X-A": "b"})
    assert (response.status_code, response.json()) == (418, {"tea": True})
    assert service.calls[0].headers["X-A"] == "b" and service.calls[0].content == b'{"a":1}'


def test_a_compressed_answer(service):
    body = gzip.compress(b'{"ok": true}')
    service.answer = httpx.Response(200, headers={"Content-Encoding": "gzip"}, stream=httpx.ByteStream(body))
    assert http.request("GET", URL).json() == {"ok": True}


def test_every_wait_has_a_limit(service):
    http.request("GET", URL)
    limits = service.calls[0].extensions["timeout"]
    assert limits["connect"] <= 3 and max(limits.values()) <= 5


def test_a_service_that_drips_is_cut_off(service, monkeypatch):
    """Each piece comes in time, so no read ever times out; together they would take forever."""
    monkeypatch.setattr(http, "TOTAL_SECONDS", 0.1)
    drip = Drip()
    service.answer = httpx.Response(200, stream=drip)
    started = time.monotonic()
    with pytest.raises(http.Unreachable) as error:
        http.request("GET", URL)
    assert time.monotonic() - started < 2 and drip.sent < 100 and error.value.retry


def test_an_endless_answer_is_cut_off(service, monkeypatch):
    monkeypatch.setattr(http, "MAX_BYTES", 1000)
    service.answer = httpx.Response(200, stream=Drip(seconds=0, size=400))
    with pytest.raises(http.Unreachable):
        http.request("GET", URL)


def test_redirects_are_not_followed(service):
    service.answer = httpx.Response(302, headers={"Location": "https://elsewhere.example"})
    assert http.request("GET", URL).status_code == 302 and len(service.calls) == 1


def test_a_service_that_is_down_is_left_alone_for_a_while(service):
    service.answer = httpx.ConnectTimeout("slow")
    for _ in range(http.FAILURES):
        with pytest.raises(http.Unreachable):
            http.request("GET", URL)
    with pytest.raises(http.Unreachable) as error:
        http.request("GET", "https://api.example.com/other")
    # Not called, so nobody waited.
    assert len(service.calls) == http.FAILURES and error.value.after == http.DOWN_SECONDS
    service.answer = httpx.Response(200)
    assert http.request("GET", "https://other.example.com").status_code == 200


def test_failures_now_and_then_are_not_down(service):
    for _ in range(http.FAILURES * 2):
        service.answer = httpx.ConnectTimeout("slow")
        with pytest.raises(http.Unreachable):
            http.request("GET", URL)
        service.answer = httpx.Response(500)
        assert http.request("GET", URL).status_code == 500


def test_a_customer_s_address_fails_for_that_customer_only(service, monkeypatch):
    """Many have theirs at the same host (hooks.zapier.com)."""
    monkeypatch.setattr(outbound, "resolve", lambda host, port: ["93.184.216.34"])
    service.answer = httpx.ConnectTimeout("slow")
    for _ in range(http.FAILURES):
        with pytest.raises(http.Unreachable):
            http.request("POST", "https://hooks.example.com/a", customer_address=True)
    service.answer = httpx.Response(200)
    assert http.request("POST", "https://hooks.example.com/b", customer_address=True).status_code == 200
    with pytest.raises(http.Unreachable):
        http.request("POST", "https://hooks.example.com/a", customer_address=True)


@pytest.mark.parametrize("address", ["10.0.0.5", "127.0.0.1", "169.254.169.254"])
def test_a_customer_s_address_cannot_be_inside_our_network(service, monkeypatch, address):
    monkeypatch.setattr(outbound, "resolve", lambda host, port: [address])
    with pytest.raises(PluginError) as error:
        http.request("POST", "https://inside.example.com", customer_address=True)
    assert not error.value.retry and service.calls == []


def test_a_customer_s_address_is_called_at_the_address_that_was_checked(service, monkeypatch):
    monkeypatch.setattr(outbound, "resolve", lambda host, port: ["93.184.216.34"])
    http.request("POST", "https://hooks.example.com/a", customer_address=True)
    (request,) = service.calls
    assert request.url.host == "93.184.216.34" and request.headers["Host"] == "hooks.example.com"
