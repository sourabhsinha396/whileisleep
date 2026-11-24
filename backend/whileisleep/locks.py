"""A lock every process shares, kept in the cache (Redis in production)."""

import uuid
from contextlib import contextmanager

from django.core.cache import cache


@contextmanager
def cache_lock(key: str, seconds: int):
    """Yields True if this job now holds the lock, False if another job does. The lock expires by
    itself, so a worker that dies while holding it can't block others for long."""
    token = uuid.uuid4().hex
    # cache.add sets the key only if it is absent, atomically (SET NX on Redis).
    held = cache.add(key, token, timeout=seconds)
    try:
        yield held
    finally:
        # Only our own lock: after an expiry the key may belong to a newer job.
        if held and cache.get(key) == token:
            cache.delete(key)
