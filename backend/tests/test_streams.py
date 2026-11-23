"""The live streams (server-sent events) the widget and the inbox read with fetch()."""

import asyncio
import json

import pytest
from asgiref.sync import async_to_sync, sync_to_async
from django.test import AsyncClient

from apps.conversations.models import Message, Visitor
from apps.conversations.services import add_message
from apps.realtime import bus, events, presence, views

from .factories import AuthTokenFactory, ConversationFactory, MessageFactory, VisitorFactory

pytestmark = pytest.mark.django_db


def parse(chunk: str) -> list[dict]:
    """SSE text to frames: {"event", "id", "data"} or {"comment"}."""
    frames = []
    for block in chunk.strip("\n").split("\n\n"):
        frame = {}
        for line in block.split("\n"):
            if line.startswith(":"):
                frame["comment"] = line[1:].strip()
            else:
                field, _, value = line.partition(": ")
                frame[field] = json.loads(value) if field == "data" else value
        frames.append(frame)
    return frames


class Stream:
    def __init__(self, response):
        self.response = response
        self.chunks = response.streaming_content.__aiter__()
        # One read in flight, kept across timeouts: cancelling it would end the stream, as
        # a disconnect does.
        self.reading = None

    async def next(self, timeout: float = 2.0) -> list[dict]:
        if self.reading is None:
            self.reading = asyncio.ensure_future(self.chunks.__anext__())
        done, _ = await asyncio.wait({self.reading}, timeout=timeout)
        if not done:
            raise TimeoutError
        chunk, self.reading = self.reading.result(), None
        return parse(chunk if isinstance(chunk, str) else chunk.decode())

    async def next_event(self, timeout: float = 2.0) -> dict:
        """The next frame that isn't a comment."""
        while True:
            for frame in await self.next(timeout):
                if "event" in frame:
                    return frame

    async def silent(self, timeout: float = 0.2) -> bool:
        try:
            await self.next_event(timeout)
        except TimeoutError:
            return True
        return False

    async def close(self):
        """The browser goes away. Django's ASGI handler then cancels the task reading the
        stream, which runs the stream's cleanup at once (aclose() on Django's wrapper would
        leave our generator to the garbage collector)."""
        reading = self.reading or asyncio.ensure_future(self.chunks.__anext__())
        await asyncio.sleep(0.01)
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await reading


async def open_widget(conversation, last_id=None) -> Stream:
    headers = {"X-Visitor-Token": conversation.visitor.token}
    if last_id is not None:
        headers["Last-Event-ID"] = str(last_id)
    response = await AsyncClient().get(f"/api/v1/widget/{conversation.workspace.public_key}/stream", headers=headers)
    assert response.status_code == 200, response.content
    stream = Stream(response)
    opening = await stream.next()
    assert opening[0]["comment"] == "connected"
    return stream


async def open_inbox(token, workspace_id, last_id=None) -> Stream:
    headers = {"Authorization": f"Bearer {token}"}
    if last_id is not None:
        headers["Last-Event-ID"] = str(last_id)
    response = await AsyncClient().get(f"/api/v1/workspaces/{workspace_id}/stream", headers=headers)
    assert response.status_code == 200, response.content
    stream = Stream(response)
    await stream.next()
    return stream


def run(scenario):
    """Runs an async scenario (or a lambda returning a coroutine) from a sync test."""

    async def go():
        return await scenario()

    return async_to_sync(go)()


say = sync_to_async(add_message)


@pytest.fixture
def conversation(workspace):
    return ConversationFactory(workspace=workspace, visitor=VisitorFactory(workspace=workspace))


@pytest.fixture
def token(membership):
    return AuthTokenFactory(user=membership.user).key


# --- The widget ---


def test_the_widget_hears_a_reply_live(conversation, fake_redis):
    async def scenario():
        stream = await open_widget(conversation)
        response = stream.response
        assert response["Content-Type"] == "text/event-stream"
        assert response["Cache-Control"].startswith("no-cache")

        message = await say(conversation, Message.Sender.AGENT, "Hello!")
        frame = await stream.next_event()
        assert frame["event"] == "message"
        assert frame["id"] == str(message.id)
        assert frame["data"]["message"]["body"] == "Hello!"
        assert (await stream.next_event())["event"] == "conversation"
        await stream.close()

    run(scenario)


def test_the_widget_never_hears_notes(conversation, fake_redis):
    async def scenario():
        stream = await open_widget(conversation)
        await say(conversation, Message.Sender.AGENT, "VIP customer", is_note=True)
        frame = await stream.next_event()
        # Only that the conversation changed, not the note.
        assert frame["event"] == "conversation"
        assert await stream.silent()
        await stream.close()

    run(scenario)


def test_the_widget_resumes_after_the_last_message_it_has(conversation, fake_redis):
    seen = MessageFactory(conversation=conversation, sender="visitor", body="Hi")
    missed = MessageFactory(conversation=conversation, sender="bot", body="Hello! How can I help?")
    MessageFactory(conversation=conversation, sender="system", body="Bot looked up: ...", is_note=True)

    async def scenario():
        stream = await open_widget(conversation, last_id=seen.id)
        frame = await stream.next_event()
        assert frame["id"] == str(missed.id)
        # Then live events, with nothing else from the backlog.
        await sync_to_async(events.typing)(conversation, "agent", "Priya")
        assert (await stream.next_event())["event"] == "typing"
        await stream.close()

    run(scenario)


def test_a_message_in_both_the_backlog_and_the_live_feed_arrives_once(conversation, fake_redis, monkeypatch):
    seen = MessageFactory(conversation=conversation, sender="visitor", body="Hi")
    racing = MessageFactory(conversation=conversation, sender="bot", body="Hello!")
    original = views.widget_backlog

    def backlog_while_published(visitor, after):
        # The message is published live after the stream subscribed, while it reads the backlog.
        events.message_added(racing)
        return original(visitor, after)

    monkeypatch.setattr(views, "widget_backlog", backlog_while_published)

    async def scenario():
        stream = await open_widget(conversation, last_id=seen.id)
        assert (await stream.next_event())["id"] == str(racing.id)
        assert await stream.silent()
        await stream.close()

    run(scenario)


def test_the_stream_keeps_the_visitor_online_until_it_closes(conversation, fake_redis, settings):
    settings.STREAM_PING_SECONDS = 0.05
    visitor = conversation.visitor

    async def scenario():
        stream = await open_widget(conversation)
        assert visitor.id in await sync_to_async(presence.online_ids)([visitor.id])
        fake_redis.expire(presence.key(visitor.id), 5)
        frames = await stream.next()
        assert frames == [{"comment": "ping"}]
        await stream.next()  # the ping's refresh has run by the time the next one comes
        assert fake_redis.ttl(presence.key(visitor.id)) > 5
        await stream.close()

    before = Visitor.objects.get(pk=visitor.pk).last_seen
    run(scenario)
    assert not presence.is_online(visitor)
    assert Visitor.objects.get(pk=visitor.pk).last_seen > before


def test_the_stream_ends_after_its_maximum_age(conversation, fake_redis, settings):
    settings.STREAM_MAX_SECONDS = 0.1

    async def scenario():
        stream = await open_widget(conversation)
        with pytest.raises(StopAsyncIteration):
            while True:
                await stream.next()

    run(scenario)


@pytest.mark.parametrize(
    "token, key, status",
    [("", None, 401), ("vt_wrong", None, 401), (None, "ws_wrong", 404)],
)
def test_the_widget_stream_needs_its_visitor(conversation, fake_redis, token, key, status):
    headers = {"X-Visitor-Token": conversation.visitor.token if token is None else token}
    path = f"/api/v1/widget/{key or conversation.workspace.public_key}/stream"
    response = run(lambda: AsyncClient().get(path, headers=headers))
    assert response.status_code == status


def test_without_redis_the_stream_says_to_poll(conversation):
    response = run(
        lambda: AsyncClient().get(
            f"/api/v1/widget/{conversation.workspace.public_key}/stream",
            headers={"X-Visitor-Token": conversation.visitor.token},
        )
    )
    assert response.status_code == 503


def test_the_wsgi_process_refuses_streams(conversation, fake_redis, anon):
    """Served under WSGI, an endless stream would hold a worker forever."""
    anon.visitor_token = conversation.visitor.token
    assert anon.get(f"/widget/{conversation.workspace.public_key}/stream").status_code == 503


def test_another_visitors_token_hears_nothing_of_this_conversation(conversation, workspace, fake_redis):
    other = ConversationFactory(workspace=workspace, visitor=VisitorFactory(workspace=workspace))

    async def scenario():
        stream = await open_widget(other)
        await say(conversation, Message.Sender.AGENT, "Your order shipped")
        assert await stream.silent()
        await stream.close()

    run(scenario)


# --- The inbox ---


def test_the_inbox_hears_everything_in_its_workspace(conversation, token, fake_redis):
    async def scenario():
        stream = await open_inbox(token, conversation.workspace_id)
        await say(conversation, Message.Sender.SYSTEM, "Visitor asked for a person.", is_note=True)
        frame = await stream.next_event()
        assert frame["event"] == "message" and frame["data"]["message"]["is_note"]
        assert (await stream.next_event())["event"] == "conversation"
        await sync_to_async(events.typing)(conversation, "visitor")
        assert (await stream.next_event())["data"]["sender"] == "visitor"
        await stream.close()

    run(scenario)


def test_the_inbox_resumes_across_conversations(conversation, workspace, token, fake_redis):
    first = MessageFactory(conversation=conversation, body="one")
    second = MessageFactory(
        conversation=ConversationFactory(workspace=workspace, visitor=VisitorFactory(workspace=workspace)), body="two"
    )
    MessageFactory(body="another workspace")

    async def scenario():
        stream = await open_inbox(token, workspace.id, last_id=first.id - 1)
        ids = [(await stream.next_event())["id"] for _ in range(2)]
        assert ids == [str(first.id), str(second.id)]
        assert await stream.silent()
        await stream.close()

    run(scenario)


def test_the_inbox_stream_needs_a_member(conversation, fake_redis):
    path = f"/api/v1/workspaces/{conversation.workspace_id}/stream"
    assert run(lambda: AsyncClient().get(path)).status_code == 401
    stranger = AuthTokenFactory().key
    response = run(lambda: AsyncClient().get(path, headers={"Authorization": f"Bearer {stranger}"}))
    assert response.status_code == 404


def test_the_frame_format():
    data = {"conversation_id": 3, "message": {"id": 41, "body": "two\nlines"}}
    assert views.frame("message", data) == (
        'id: 41\nevent: message\ndata: {"conversation_id":3,"message":{"id":41,"body":"two\\nlines"}}\n\n'
    )
    assert views.frame("typing", {"sender": "visitor"}) == 'event: typing\ndata: {"sender":"visitor"}\n\n'


def test_replayed_and_live_messages_have_the_same_shape(conversation, fake_redis, listen):
    """Dates in ISO 8601 either way, as the REST API sends them."""
    widget = listen(bus.visitor_channel(conversation.visitor_id))
    message = add_message(conversation, Message.Sender.AGENT, "Hello!")
    live = widget.events()[0]["data"]
    [(_, replayed)] = views.widget_backlog(conversation.visitor, message.id - 1)
    framed = parse(views.frame("message", replayed))[0]["data"]
    assert framed == live
    assert "T" in framed["message"]["created_at"]


def test_publishing_and_listening_use_the_same_channel_names():
    assert bus.visitor_channel(7) == "whileisleep:visitor:7"
    assert bus.workspace_channel(7) == "whileisleep:workspace:7"
