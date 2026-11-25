"""Calls to outside services, which may be slow or down.

A thread that waits can do nothing else, so no call may keep one for long:

- A call has a deadline for all of it, not only for each read: a service that answers a few bytes
  at a time is cut off too.
- After a few calls in a row that got no answer, the service counts as down for half a minute. Calls
  then fail at once, instead of each thread finding out for itself.

Only worker jobs call services (deliveries, jobs); web requests don't, but for the captcha and Google
at log-in (apps/accounts). This is for threads: in
async code it would block the event loop.
"""

import hashlib
import time

import httpx
from django.core.cache import cache

from whileisleep import outbound

from .plugin import PluginError

CONNECT_SECONDS = 3
READ_SECONDS = 5
TOTAL_SECONDS = 8
MAX_BYTES = 5 * 1024 * 1024

# This many calls without an answer, within the first time, and the service is down for the second.
FAILURES = 5
FAILURE_WINDOW_SECONDS = 60
DOWN_SECONDS = 30


class Unreachable(PluginError):
    """No answer, or not in time. Worth another try later."""

    def __init__(self, message: str, after: int | None = None):
        super().__init__(message, retry=True, after=after)


def request(
    method: str,
    url: str,
    *,
    customer_address: bool = False,
    headers: dict | None = None,
    total_seconds: float | None = None,
    **kwargs,
):
    """An httpx.Response, whatever its status, or Unreachable. Pass `customer_address=True` when a
    customer typed the URL: private addresses are then refused (whileisleep.outbound)."""
    host = httpx.URL(url).host
    # A customer's address fails on its own: thousands of them share hooks.zapier.com.
    service = hashlib.sha256(url.encode()).hexdigest() if customer_address else host
    if cache.get(f"service-down:{service}"):
        raise Unreachable(f"{host} isn't answering right now.", after=DOWN_SECONDS)
    total_seconds = total_seconds or TOTAL_SECONDS
    ends = time.monotonic() + total_seconds
    target, headers, extensions = httpx.URL(url), dict(headers or {}), {}
    try:
        if customer_address:
            target, headers, extensions = outbound.prepare(url, headers)
        timeout = httpx.Timeout(min(READ_SECONDS, total_seconds), connect=min(CONNECT_SECONDS, total_seconds))
        with httpx.Client(timeout=timeout, follow_redirects=False, verify=outbound.tls()) as client:
            with client.stream(method, target, headers=headers, extensions=extensions, **kwargs) as response:
                body = read(response, ends)
    except outbound.BlockedAddress as error:
        raise PluginError(str(error)) from error
    except httpx.HTTPError as error:
        no_answer(service)
        raise Unreachable(f"{host} couldn't be reached ({type(error).__name__}).") from error
    cache.delete(f"service-failures:{service}")
    # Already decoded, so it must not say how it was encoded.
    kept = [(name, value) for name, value in response.headers.items() if name != "content-encoding"]
    return httpx.Response(response.status_code, headers=kept, content=body, request=response.request)


def read(response: httpx.Response, ends: float) -> bytes:
    chunks, size = [], 0
    for chunk in response.iter_bytes():
        chunks.append(chunk)
        size += len(chunk)
        if time.monotonic() > ends:
            raise httpx.ReadTimeout("It took too long.")
        if size > MAX_BYTES:
            raise httpx.ReadError("It was too long.")
    return b"".join(chunks)


def no_answer(service: str) -> None:
    key = f"service-failures:{service}"
    cache.add(key, 0, FAILURE_WINDOW_SECONDS)
    try:
        failures = cache.incr(key)
    except ValueError:
        # It expired in between.
        return
    if failures >= FAILURES:
        cache.set(f"service-down:{service}", 1, DOWN_SECONDS)
        cache.delete(key)
