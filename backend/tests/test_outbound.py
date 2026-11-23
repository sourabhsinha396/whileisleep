import httpx
import pytest

from whileisleep import outbound


class Recorder:
    """Stands in for outbound.send, the last step before the network."""

    def __init__(self):
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": str(url), **kwargs})
        return httpx.Response(200, text="ok", request=httpx.Request(method, url))


@pytest.fixture
def sent(monkeypatch):
    recorder = Recorder()
    monkeypatch.setattr(outbound, "send", recorder)
    return recorder


@pytest.fixture
def wire(monkeypatch):
    """Lets requests run through real httpx, stopping at the socket: records what would
    have been sent and answers 302 (to prove redirects aren't followed)."""
    seen = []

    def handle(self, request):
        seen.append(request)
        return httpx.Response(302, headers={"Location": "http://169.254.169.254/"}, request=request)

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", handle)
    return seen


@pytest.fixture
def dns(monkeypatch):
    """Make every host name resolve to the given addresses."""

    def install(*addresses):
        monkeypatch.setattr(outbound, "resolve", lambda host, port: list(addresses))

    return install


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # private
        "172.17.0.1",  # the Docker bridge
        "192.168.1.10",  # private
        "169.254.169.254",  # cloud metadata
        "100.64.0.1",  # carrier-grade NAT
        "0.0.0.0",
        "::1",
        "fd00::1",  # private IPv6
        "fe80::1",  # link-local IPv6
        "::ffff:10.0.0.5",  # private IPv4 written as IPv6
    ],
)
def test_private_addresses_are_not_public(address):
    assert not outbound.is_public(address)


@pytest.mark.parametrize("address", ["93.184.216.34", "2606:2800:220:1:248:1893:25c8:1946"])
def test_internet_addresses_are_public(address):
    assert outbound.is_public(address)


def test_request_connects_to_the_checked_address(sent, dns):
    dns("93.184.216.34")
    outbound.request("GET", "https://api.example.com/orders?id=7", headers={"X-Key": "k"})
    call = sent.calls[0]
    assert call["url"] == "https://93.184.216.34/orders?id=7"
    assert call["headers"] == {"X-Key": "k", "Host": "api.example.com"}
    assert call["extensions"] == {"sni_hostname": "api.example.com"}


def test_the_pinned_request_survives_real_httpx(wire, dns):
    """Through httpx itself, not a stand-in: an argument httpx rejects, or a Host header it
    rewrites, would only show up here."""
    dns("93.184.216.34")
    response = outbound.request(
        "POST", "https://api.example.com/orders", params={"id": "7"}, json={"q": "x"}, headers={"X-Key": "k"}
    )
    [request] = wire
    assert str(request.url) == "https://93.184.216.34/orders?id=7"
    assert request.headers["host"] == "api.example.com"
    assert request.headers["x-key"] == "k"
    assert request.extensions["sni_hostname"] == "api.example.com"
    assert request.content == b'{"q":"x"}'
    # The redirect to the metadata address was returned, not followed.
    assert response.status_code == 302 and len(wire) == 1


def test_an_allowed_private_request_survives_real_httpx(wire, settings):
    settings.OUTBOUND_ALLOW_PRIVATE_NETWORKS = True
    outbound.request("GET", "http://host.docker.internal:8006/api", headers={"X-Key": "k"})
    [request] = wire
    assert str(request.url) == "http://host.docker.internal:8006/api"
    assert request.headers["host"] == "host.docker.internal:8006"


def test_host_header_keeps_an_unusual_port(sent, dns):
    dns("93.184.216.34")
    outbound.request("GET", "http://api.example.com:8080/x")
    assert sent.calls[0]["url"] == "http://93.184.216.34:8080/x"
    assert sent.calls[0]["headers"]["Host"] == "api.example.com:8080"


def test_a_host_header_from_the_tool_cannot_replace_ours(sent, dns):
    dns("93.184.216.34")
    outbound.request("GET", "https://api.example.com/", headers={"host": "internal.service"})
    assert sent.calls[0]["headers"] == {"Host": "api.example.com"}


def test_private_host_is_blocked_before_any_request(sent, dns):
    dns("10.0.0.5")
    with pytest.raises(outbound.BlockedAddress):
        outbound.request("GET", "http://intranet.example.com/")
    assert sent.calls == []


def test_one_private_address_among_public_ones_blocks_the_host(sent, dns):
    # A name that answers with both: an attacker hopes we check one and connect to the other.
    dns("93.184.216.34", "127.0.0.1")
    with pytest.raises(outbound.BlockedAddress):
        outbound.request("GET", "http://sneaky.example.com/")


def test_ip_literals_are_checked_too(sent):
    with pytest.raises(outbound.BlockedAddress):
        outbound.request("GET", "http://169.254.169.254/latest/meta-data/")
    with pytest.raises(outbound.BlockedAddress):
        outbound.request("GET", "http://[::1]:5432/")
    assert sent.calls == []


@pytest.mark.parametrize("url", ["ftp://example.com/x", "file:///etc/passwd", "gopher://example.com", "not a url"])
def test_other_schemes_are_refused(sent, url):
    with pytest.raises(outbound.BlockedAddress):
        outbound.request("GET", url)
    assert sent.calls == []


def test_unknown_host_is_a_network_error(sent, monkeypatch):
    def fail(*args, **kwargs):
        raise outbound.socket.gaierror("no such host")

    monkeypatch.setattr(outbound.socket, "getaddrinfo", fail)
    with pytest.raises(httpx.ConnectError):
        outbound.request("GET", "http://nowhere.invalid/")


def test_private_networks_can_be_allowed(sent, settings):
    settings.OUTBOUND_ALLOW_PRIVATE_NETWORKS = True
    outbound.request("GET", "http://host.docker.internal:8006/api", headers={"X-Key": "k"})
    call = sent.calls[0]
    assert call["url"] == "http://host.docker.internal:8006/api"
    assert call["headers"] == {"X-Key": "k"}
    assert call["extensions"] == {}
