"""Who is online, from Redis keys with a TTL (and from last_seen when there is no Redis)."""

import time
from datetime import timedelta

import fakeredis
import pytest
from asgiref.sync import async_to_sync
from django.utils import timezone

from apps.conversations.models import Visitor
from apps.realtime import bus, presence

from .factories import ConversationFactory, VisitorFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def visitor(workspace):
    return VisitorFactory(workspace=workspace)


def test_a_page_load_puts_the_visitor_online(workspace, anon, fake_redis, listen):
    inbox = listen(bus.workspace_channel(workspace.id))
    response = anon.post(f"/widget/{workspace.public_key}/session", {"url": "https://shop.example.com/"})
    visitor = Visitor.objects.get(token=response.json()["token"])

    assert visitor.is_online
    assert fake_redis.ttl(presence.key(visitor.id)) == pytest.approx(45, abs=2)
    assert inbox.events() == [{"event": "presence", "data": {"visitor_id": visitor.id, "online": True}}]

    # Only the first touch is news.
    anon.visitor_token = visitor.token
    anon.get(f"/widget/{workspace.public_key}/messages")
    assert inbox.events() == []


def test_polling_keeps_the_visitor_online_without_writing_postgres(workspace, visitor, anon, fake_redis):
    before = visitor.last_seen
    anon.visitor_token = visitor.token
    anon.get(f"/widget/{workspace.public_key}/messages")
    visitor.refresh_from_db()
    assert visitor.is_online
    assert visitor.last_seen == before


def test_the_key_expiring_takes_the_visitor_offline(visitor, fake_redis):
    presence.touch(visitor)
    fake_redis.delete(presence.key(visitor.id))  # what the TTL does
    assert not visitor.is_online


def test_the_visitors_page_lists_who_is_online(workspace, api, fake_redis):
    here, gone, elsewhere = VisitorFactory(workspace=workspace), VisitorFactory(workspace=workspace), VisitorFactory()
    for v in (here, gone, elsewhere):
        presence.touch(v)
    fake_redis.delete(presence.key(gone.id))

    rows = api.get(f"/workspaces/{workspace.id}/visitors", online="true").json()
    assert [(r["id"], r["online"]) for r in rows] == [(here.id, True)]

    week = {r["id"]: r["online"] for r in api.get(f"/workspaces/{workspace.id}/visitors").json()}
    assert week == {here.id: True, gone.id: False}


def test_the_index_forgets_expired_entries(workspace, visitor, fake_redis):
    fake_redis.zadd(presence.index_key(workspace.id), {visitor.id: time.time() - 1})
    fake_redis.set(presence.key(visitor.id), 1)
    assert presence.online_in(workspace.id) == []
    assert fake_redis.zcard(presence.index_key(workspace.id)) == 0


def test_the_inbox_shows_who_is_online(workspace, api, fake_redis):
    online, offline = (
        ConversationFactory(workspace=workspace, visitor=VisitorFactory(workspace=workspace)) for _ in "ab"
    )
    presence.touch(online.visitor)
    rows = {r["id"]: r["visitor"]["online"] for r in api.get(f"/workspaces/{workspace.id}/conversations").json()}
    assert rows == {online.id: True, offline.id: False}


# --- Streams ---


def stream(server, call, *args):
    async def run():
        client = fakeredis.FakeAsyncRedis(server=server)
        try:
            return await call(client, *args)
        finally:
            await client.aclose()

    return async_to_sync(run)()


@pytest.fixture
def server(fake_redis):
    return fake_redis.connection_pool.connection_kwargs["server"]


def test_two_tabs_keep_the_visitor_online_until_both_close(workspace, visitor, fake_redis, server, listen):
    inbox = listen(bus.workspace_channel(workspace.id))
    stream(server, presence.stream_opened, workspace.id, visitor.id)
    stream(server, presence.stream_opened, workspace.id, visitor.id)
    assert inbox.events() == [{"event": "presence", "data": {"visitor_id": visitor.id, "online": True}}]

    assert stream(server, presence.stream_closed, workspace.id, visitor.id) is False
    assert visitor.is_online
    assert inbox.events() == []

    assert stream(server, presence.stream_closed, workspace.id, visitor.id) is True
    assert not visitor.is_online
    assert presence.online_in(workspace.id) == []
    assert inbox.events() == [{"event": "presence", "data": {"visitor_id": visitor.id, "online": False}}]


def test_a_live_stream_refreshes_the_ttl(workspace, visitor, fake_redis, server):
    stream(server, presence.stream_opened, workspace.id, visitor.id)
    fake_redis.expire(presence.key(visitor.id), 3)
    stream(server, presence.stream_alive, workspace.id, visitor.id)
    assert fake_redis.ttl(presence.key(visitor.id)) == pytest.approx(45, abs=2)


# --- Without Redis ---


def test_without_redis_presence_is_last_seen(workspace, visitor):
    visitor.last_seen = timezone.now() - timedelta(minutes=5)
    assert not visitor.is_online
    presence.touch(visitor)
    visitor.refresh_from_db()
    assert visitor.is_online
    assert presence.online_in(workspace.id) is None


def test_without_redis_last_seen_is_written_once_per_window(visitor, django_assert_num_queries):
    presence.touch(visitor)
    with django_assert_num_queries(0):
        presence.touch(visitor)
