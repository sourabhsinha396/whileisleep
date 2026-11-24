"""HTTP requests to addresses that workspace owners typed in (tools, MCP servers).

A workspace owner controls the URL, so without a guard a tool could read services that are
only reachable from this server: the database, a cloud metadata endpoint, another
container. Every such request goes through `request()`, which

- allows only http and https,
- resolves the host and refuses any address that isn't on the public internet,
- connects to the address it checked (not to the name again), so a DNS answer that changes
  between the check and the connection can't slip through, and
- never follows redirects, which could point back inside.

Self-hosters whose tools live on a private network set OUTBOUND_ALLOW_PRIVATE_NETWORKS.
"""

import ipaddress
import socket

import httpx
from django.conf import settings

ALLOWED_SCHEMES = {"http", "https"}
DEFAULT_PORTS = {"http": 80, "https": 443}


class BlockedAddress(Exception):
    """The URL points somewhere this server must not call. The message is safe to show."""


def is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    # ::ffff:10.0.0.1 is 10.0.0.1 in an IPv6 coat.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def resolve(host: str, port: int) -> list[str]:
    """Every address the host name points to."""
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as error:
        raise httpx.ConnectError(f"Could not resolve {host}") from error
    return [info[4][0] for info in infos]


def public_address(host: str, port: int) -> str:
    """An address to connect to, after checking that all of the host's addresses are public."""
    addresses = resolve(host, port)
    if not addresses:
        raise httpx.ConnectError(f"Could not resolve {host}")
    for address in addresses:
        if not is_public(address):
            raise BlockedAddress(f"{host} is on a private network, which tools may not call.")
    return addresses[0]


def pin(url: httpx.URL, address: str) -> tuple[httpx.URL, dict, dict]:
    """The same request aimed at `address`: (url, extra headers, httpx extensions).

    The Host header and the TLS server name keep the original host, so virtual hosting and
    certificate checks work as if we had connected by name.
    """
    default_port = url.port is None or url.port == DEFAULT_PORTS[url.scheme]
    host_header = url.host if default_port else f"{url.host}:{url.port}"
    return url.copy_with(host=address), {"Host": host_header}, {"sni_hostname": url.host}


def prepare(url: str, headers: dict | None = None) -> tuple[httpx.URL, dict, dict]:
    """(url, headers, httpx extensions) for a request to a URL we don't control, after checking
    it. Raises BlockedAddress or httpx.HTTPError."""
    try:
        target = httpx.URL(url)
    except httpx.InvalidURL as error:
        raise BlockedAddress("That URL isn't valid.") from error
    if target.scheme not in ALLOWED_SCHEMES or not target.host:
        raise BlockedAddress("Only http:// and https:// URLs can be called.")

    headers = dict(headers or {})
    extensions = {}
    if not settings.OUTBOUND_ALLOW_PRIVATE_NETWORKS:
        address = public_address(target.host, target.port or DEFAULT_PORTS[target.scheme])
        target, host_headers, extensions = pin(target, address)
        headers = {k: v for k, v in headers.items() if k.lower() != "host"} | host_headers
    return target, headers, extensions


def request(method: str, url: str, *, headers: dict | None = None, timeout: float = 10, **kwargs) -> httpx.Response:
    """Like httpx.request, for a URL we don't control. Raises BlockedAddress or httpx.HTTPError."""
    target, headers, extensions = prepare(url, headers)
    return send(method, target, headers=headers, timeout=timeout, extensions=extensions, **kwargs)


def send(method: str, url: httpx.URL, *, headers: dict, timeout: float, extensions: dict, **kwargs) -> httpx.Response:
    """The one place a guarded request leaves this process. Redirects are never followed:
    one could lead back inside the network we just refused."""
    with httpx.Client(follow_redirects=False, timeout=timeout) as client:
        return client.request(method, url, headers=headers, extensions=extensions, **kwargs)
