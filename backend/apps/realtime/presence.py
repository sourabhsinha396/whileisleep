"""Who is on the site right now, kept in Redis instead of a Postgres write every 20 seconds.

A visitor is online while their key exists. Keys expire by themselves (TTL), so a browser
that vanishes without a goodbye goes offline within PRESENCE_TTL_SECONDS. What refreshes a
key:

- an open live stream (apps.realtime.views), on every keep-alive ping. Streams are
  counted per visitor, so closing one of two tabs doesn't mark them offline;
- a request from a widget that has no stream (POST /session on page load, GET /messages
  while it polls).

Each workspace also has a sorted set of its visitors by when their key expires, so the
Visitors page can list who is online without scanning keys. A visitor's first ping and
their last goodbye are published as `presence` events for the inbox.

Without Redis, presence falls back to Visitor.last_seen, written at most once per TTL.
`last_seen` is still saved on each page load and when the last stream closes, for "last
seen 5 minutes ago".
"""

import time
from datetime import timedelta

import redis
from django.conf import settings
from django.utils import timezone

from . import bus


def ttl() -> int:
    return settings.PRESENCE_TTL_SECONDS


def key(visitor_id: int) -> str:
    return f"{bus.PREFIX}presence:{visitor_id}"


def streams_key(visitor_id: int) -> str:
    return f"{bus.PREFIX}presence:{visitor_id}:streams"


def index_key(workspace_id: int) -> str:
    return f"{bus.PREFIX}online:{workspace_id}"


def announce(workspace_id: int, visitor_id: int, online: bool) -> None:
    bus.publish([bus.workspace_channel(workspace_id)], "presence", {"visitor_id": visitor_id, "online": online})


# --- Requests from the widget (sync) ---


def touch(visitor) -> None:
    """The visitor's widget just called us: they are online for another TTL."""
    connection = bus.client()
    if connection is None:
        if visitor.last_seen is None or timezone.now() - visitor.last_seen > timedelta(seconds=ttl() / 3):
            visitor.last_seen = timezone.now()
            type(visitor).objects.filter(pk=visitor.pk).update(last_seen=visitor.last_seen)
        return
    try:
        with connection.pipeline(transaction=False) as pipe:
            pipe.set(key(visitor.id), 1, ex=ttl(), get=True)
            pipe.zadd(index_key(visitor.workspace_id), {visitor.id: time.time() + ttl()})
            pipe.expire(index_key(visitor.workspace_id), ttl())
            was, *_ = pipe.execute()
    except redis.RedisError:
        return
    if was is None:
        announce(visitor.workspace_id, visitor.id, True)


def online_ids(visitor_ids) -> set[int] | None:
    """Which of these visitors are online, in one round trip; None without Redis."""
    visitor_ids = list(visitor_ids)
    connection = bus.client()
    if connection is None:
        return None
    if not visitor_ids:
        return set()
    try:
        values = connection.mget([key(i) for i in visitor_ids])
    except redis.RedisError:
        return set()
    return {i for i, value in zip(visitor_ids, values, strict=True) if value is not None}


def is_online(visitor) -> bool:
    found = online_ids([visitor.id])
    if found is None:
        return last_seen_recently(visitor)
    return visitor.id in found


def last_seen_recently(visitor) -> bool:
    return visitor.last_seen is not None and (timezone.now() - visitor.last_seen).total_seconds() < ttl()


def online_in(workspace_id: int) -> list[int] | None:
    """Ids of the workspace's visitors online now; None without Redis (ask the database)."""
    connection = bus.client()
    if connection is None:
        return None
    try:
        index = index_key(workspace_id)
        connection.zremrangebyscore(index, "-inf", time.time())
        candidates = [int(i) for i in connection.zrangebyscore(index, time.time(), "+inf")]
    except redis.RedisError:
        return []
    # A visitor whose last stream closed is gone from the keys before the index catches up.
    return [i for i in candidates if i in online_ids(candidates)]


# --- Live streams (async, one Redis client per stream) ---


async def stream_opened(client, workspace_id: int, visitor_id: int) -> None:
    async with client.pipeline(transaction=False) as pipe:
        pipe.incr(streams_key(visitor_id))
        pipe.expire(streams_key(visitor_id), ttl())
        pipe.set(key(visitor_id), 1, ex=ttl(), get=True)
        pipe.zadd(index_key(workspace_id), {visitor_id: time.time() + ttl()})
        pipe.expire(index_key(workspace_id), ttl())
        _, _, was, *_ = await pipe.execute()
    if was is None:
        await client.publish(bus.workspace_channel(workspace_id), presence_payload(visitor_id, True))


async def stream_alive(client, workspace_id: int, visitor_id: int) -> None:
    async with client.pipeline(transaction=False) as pipe:
        pipe.set(key(visitor_id), 1, ex=ttl())
        pipe.expire(streams_key(visitor_id), ttl())
        pipe.zadd(index_key(workspace_id), {visitor_id: time.time() + ttl()})
        pipe.expire(index_key(workspace_id), ttl())
        await pipe.execute()


async def stream_closed(client, workspace_id: int, visitor_id: int) -> bool:
    """Returns True if that was the visitor's last stream (they are now offline)."""
    left = await client.decr(streams_key(visitor_id))
    if left > 0:
        return False
    async with client.pipeline(transaction=False) as pipe:
        pipe.delete(key(visitor_id), streams_key(visitor_id))
        pipe.zrem(index_key(workspace_id), visitor_id)
        pipe.publish(bus.workspace_channel(workspace_id), presence_payload(visitor_id, False))
        await pipe.execute()
    return True


def presence_payload(visitor_id: int, online: bool) -> str:
    return bus.encode("presence", {"visitor_id": visitor_id, "online": online})
