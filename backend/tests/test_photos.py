"""A person's photo: shown to their team, and to visitors next to their replies."""

import re

import pytest
from django.core.files.storage import default_storage
from django.test.utils import CaptureQueriesContext

from apps.conversations.models import Message

from .conftest import Api
from .factories import (
    AuthTokenFactory,
    ConversationFactory,
    MembershipFactory,
    MessageFactory,
    VisitorFactory,
)
from .test_images import picture

pytestmark = pytest.mark.django_db


def photos(user) -> list[str]:
    try:
        return default_storage.listdir(f"users/{user.id}/photo")[1]
    except FileNotFoundError:
        return []


def test_uploading_a_photo(api, membership):
    assert api.get("/auth/me").json()["photo_url"] == ""
    url = api.upload("/auth/me/photo", picture(size=(400, 300))).json()["photo_url"]
    assert re.fullmatch(rf"https://cdn\.example\.com/users/{membership.user_id}/photo/[0-9a-f]{{32}}\.png", url)
    assert api.get("/auth/me").json()["photo_url"] == url


def test_a_new_photo_replaces_the_old_file_and_removing_deletes_it(api, membership):
    api.upload("/auth/me/photo", picture())
    second = api.upload("/auth/me/photo", picture("JPEG")).json()["photo_url"]
    assert photos(membership.user) == [second.rsplit("/", 1)[1]]
    assert api.delete("/auth/me/photo").json()["photo_url"] == ""
    assert photos(membership.user) == []


def test_removing_a_photo_that_was_never_set(api):
    assert api.delete("/auth/me/photo").json()["photo_url"] == ""


def test_a_refused_photo_changes_nothing(api, membership):
    assert api.upload("/auth/me/photo", picture("GIF")).status_code == 400
    assert photos(membership.user) == []


def test_signing_in_is_required():
    assert Api().upload("/auth/me/photo", picture()).status_code == 401
    assert Api().delete("/auth/me/photo").status_code == 401


def test_without_a_bucket_uploads_are_off(api, settings):
    settings.UPLOADS_ENABLED = False
    assert api.upload("/auth/me/photo", picture()).status_code == 503


def test_the_team_list_shows_photos(api, workspace, membership):
    url = api.upload("/auth/me/photo", picture()).json()["photo_url"]
    MembershipFactory(workspace=workspace)
    rows = {m["user_id"]: m["photo_url"] for m in api.get(f"/workspaces/{workspace.id}/members").json()}
    assert rows.pop(membership.user_id) == url
    assert list(rows.values()) == [""]


def test_replies_carry_their_authors_photo_to_both_sides(api, workspace):
    url = api.upload("/auth/me/photo", picture()).json()["photo_url"]
    visitor = VisitorFactory(workspace=workspace)
    conversation = ConversationFactory(workspace=workspace, visitor=visitor)
    MessageFactory(conversation=conversation, sender=Message.Sender.VISITOR, body="Hi")
    base = f"/workspaces/{workspace.id}/conversations/{conversation.id}"
    assert api.post(f"{base}/messages", {"body": "Hello"}).json()["author_photo"] == url
    for messages in (
        api.get(base).json()["messages"],
        Api(visitor_token=visitor.token).get(f"/widget/{workspace.public_key}/messages").json()["messages"],
    ):
        assert [m["author_photo"] for m in messages] == ["", url]


def test_live_events_carry_the_photo(api, workspace, listen):
    from apps.realtime import bus

    url = api.upload("/auth/me/photo", picture()).json()["photo_url"]
    visitor = VisitorFactory(workspace=workspace)
    conversation = ConversationFactory(workspace=workspace, visitor=visitor)
    heard = listen(bus.visitor_channel(visitor.id))
    base = f"/workspaces/{workspace.id}/conversations/{conversation.id}"
    api.post(f"{base}/typing")
    api.post(f"{base}/messages", {"body": "Hello"})
    events = heard.events()
    typing = next(e["data"] for e in events if e["event"] == "typing")
    message = next(e["data"]["message"] for e in events if e["event"] == "message")
    assert typing["photo"] == url and message["author_photo"] == url


def test_more_authors_cost_no_more_queries(api, workspace, membership):
    from django.db import connection

    conversation = ConversationFactory(workspace=workspace, visitor=VisitorFactory(workspace=workspace))
    path = f"/workspaces/{workspace.id}/conversations/{conversation.id}"

    def reply_from_someone_new():
        author = MembershipFactory(workspace=workspace).user
        Api(token=AuthTokenFactory(user=author).key).post(f"{path}/messages", {"body": "Hi"})

    def queries():
        with CaptureQueriesContext(
            connection,
        ) as captured:
            api.get(path)
        return len(captured)

    reply_from_someone_new()
    api.get(path)  # clears "unread", which is a query of its own
    one = queries()
    for _ in range(4):
        reply_from_someone_new()
    assert queries() == one
