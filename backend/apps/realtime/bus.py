"""Redis pub/sub between the processes that change things (the API, the Celery worker) and
the stream process that holds the browsers' open connections (apps.realtime.views).

Two kinds of channel:

- one per visitor, which their widget listens to: what the visitor may see (no notes,
  no system messages);
- one per workspace, which the team's inbox listens to: everything.

Publishing is fire-and-forget. A browser that misses an event catches up when it
reconnects (from the last message id it has) or on its next poll, so a Redis hiccup must
never fail the request that changed something. Without REDIS_URL nothing is published and
the stream endpoints answer 503; browsers then poll.
"""

import json
import logging

import redis
import redis.asyncio
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

log = logging.getLogger(__name__)

PREFIX = "whileisleep:"

_client: redis.Redis | None = None


def visitor_channel(visitor_id: int) -> str:
    return f"{PREFIX}visitor:{visitor_id}"


def workspace_channel(workspace_id: int) -> str:
    return f"{PREFIX}workspace:{workspace_id}"


def client() -> redis.Redis | None:
    """This process's Redis connection pool, or None when there is no Redis."""
    global _client
    if not settings.REDIS_URL:
        return None
    if _client is None:
        # Short timeouts: a slow Redis must not hold up the request that publishes.
        _client = redis.Redis.from_url(settings.REDIS_URL, socket_timeout=2, socket_connect_timeout=2)
    return _client


def async_client() -> redis.asyncio.Redis | None:
    """A new asyncio client, for one stream connection (it is bound to the running event loop)."""
    if not settings.REDIS_URL:
        return None
    return redis.asyncio.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)


def encode(event: str, data: dict) -> str:
    return json.dumps({"event": event, "data": data}, cls=DjangoJSONEncoder)


def publish(channels: list[str], event: str, data: dict) -> None:
    connection = client()
    if connection is None or not channels:
        return
    payload = encode(event, data)
    try:
        with connection.pipeline(transaction=False) as pipe:
            for channel in channels:
                pipe.publish(channel, payload)
            pipe.execute()
    except redis.RedisError as error:
        log.warning("Couldn't publish %s to %s: %s", event, channels, error)
