"""Rate limits for the public widget API and daily caps on AI replies.

Fixed-window counters in Django's cache. The default cache is per process, which is right
for one dev server; with several workers in production, point CACHES at Redis so the
counts are shared.
"""

import time

from django.conf import settings
from django.core.cache import cache


def hit(name: str, key: str, limit: int, window_seconds: int) -> bool:
    """Counts one event. True while the count in the current window is within `limit`."""
    bucket = int(time.time() // window_seconds)
    cache_key = f"rl:{name}:{key}:{bucket}"
    if cache.add(cache_key, 1, timeout=window_seconds + 5):
        return 1 <= limit
    try:
        return cache.incr(cache_key) <= limit
    except ValueError:  # expired between add and incr
        cache.add(cache_key, 1, timeout=window_seconds + 5)
        return True


def allow_new_visitor(ip: str | None) -> bool:
    return hit("new_visitor", ip or "-", settings.RATE_LIMITS["new_visitors_per_ip_per_hour"], 3600)


def allow_message(visitor_id: int, ip: str | None) -> bool:
    limits = settings.RATE_LIMITS
    # Both counters move on every message, so a script rotating visitor tokens still hits the IP limit.
    by_visitor = hit("msg_visitor", str(visitor_id), limits["messages_per_visitor_per_minute"], 60)
    by_ip = hit("msg_ip", ip or "-", limits["messages_per_ip_per_minute"], 60)
    return by_visitor and by_ip


def allow_upload(visitor_id: int, ip: str | None) -> bool:
    limits = settings.RATE_LIMITS
    by_visitor = hit("upload_visitor", str(visitor_id), limits["uploads_per_visitor_per_hour"], 3600)
    by_ip = hit("upload_ip", ip or "-", limits["uploads_per_ip_per_hour"], 3600)
    return by_visitor and by_ip


def allow_ai_reply(conversation) -> bool:
    """Counts one LLM reply against the visitor's and the workspace's daily caps."""
    limits = settings.RATE_LIMITS
    by_visitor = hit("ai_visitor", str(conversation.visitor_id), limits["ai_replies_per_visitor_per_day"], 86400)
    by_workspace = hit(
        "ai_workspace", str(conversation.workspace_id), limits["ai_replies_per_workspace_per_day"], 86400
    )
    return by_visitor and by_workspace
