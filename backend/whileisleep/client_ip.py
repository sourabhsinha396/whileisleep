"""The address a request really came from, for rate limits.

X-Forwarded-For is a list each proxy appends to, and its left end is whatever the sender
typed, so trusting the first entry lets anyone pick their own "IP" and dodge the limits.
Only the entries added by our own proxies can be believed: with TRUSTED_PROXY_COUNT proxies
in front, the client is the entry that many places from the right.
"""

import ipaddress

from django.conf import settings


def client_ip(request) -> str | None:
    remote = request.META.get("REMOTE_ADDR") or None
    proxies = settings.TRUSTED_PROXY_COUNT
    if proxies <= 0:
        return remote
    hops = [hop.strip() for hop in request.headers.get("X-Forwarded-For", "").split(",") if hop.strip()]
    if len(hops) < proxies:
        # Fewer hops than proxies: the request skipped a proxy, so the header proves nothing.
        return remote
    candidate = hops[-proxies]
    try:
        return str(ipaddress.ip_address(candidate))
    except ValueError:
        return remote
