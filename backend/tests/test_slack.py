"""The Slack plugin, against a fake Slack (fake_slack.py)."""

import json
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from django.utils import timezone

from apps.conversations.models import Conversation, Message
from apps.conversations.services import add_message, reply_as, request_human, set_human_requested, set_status
from apps.conversations.signals import CONTACT_UPDATED, announce
from apps.integrations import tasks
from apps.integrations.models import Delivery, Integration, Thread
from plugins.slack import plugin as slack_plugin
from plugins.slack.connector import BOT_EVENTS, SCOPES

from .conftest import Api, assistant, final, tool_call
from .factories import (
    AuthTokenFactory,
    ConversationFactory,
    MembershipFactory,
    UserFactory,
    VisitorFactory,
    WorkspaceFactory,
)
from .fake_slack import SECRET, TEAM, WEBHOOK, FakeSlack, post, post_action, post_event, signed

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def slack(settings, monkeypatch):
    settings.PLUGIN_OPTIONS = {
        "PLUGIN_SLACK_CLIENT_ID": "client-1",
        "PLUGIN_SLACK_CLIENT_SECRET": "secret-1",
        "PLUGIN_SLACK_SIGNING_SECRET": SECRET,
    }
    settings.SITE_URL = "https://chat.example.com"
    fake = FakeSlack()
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda self, request: fake.handle(request))
    return fake


@pytest.fixture
def base(workspace):
    return f"/workspaces/{workspace.id}/integrations"


@pytest.fixture
def integration(workspace):
    return Integration.objects.create(
        workspace=workspace,
        plugin="slack",
        account_id=TEAM,
        account_name="Acme HQ",
        credentials={"token": "xoxb-1"},
        config={"channel": "C2", "chats": "person", "mention": "nobody"},
    )


@pytest.fixture
def conversation(workspace):
    visitor = VisitorFactory(workspace=workspace, name="Maya", current_url="https://acme.com/orders/1042?x=1")
    return ConversationFactory(workspace=workspace, visitor=visitor)


@pytest.fixture
def priya(workspace, slack):
    user = UserFactory(first_name="Priya", email="priya@acme.com")
    MembershipFactory(user=user, workspace=workspace, role="agent")
    slack.person("U1", "Priya@acme.com")
    return user


@pytest.fixture
def thread(integration, conversation, priya, slack):
    """Handed over: there is a thread, and it has caught up."""
    add_message(conversation, Message.Sender.VISITOR, "My order came broken")
    request_human(conversation, "wants a refund")
    slack.calls.clear()
    conversation.refresh_from_db()
    return Thread.objects.get()


def text_of(params: dict) -> str:
    """Everything a post says."""
    words = [params["text"]]
    for block in json.loads(params.get("blocks", "[]")):
        words += [block["text"]["text"]] if block["type"] == "section" else []
        words += [e["text"] for e in block["elements"]] if block["type"] == "context" else []
    return "\n".join(words)


def buttons(params: dict) -> list[str]:
    (actions,) = [b for b in json.loads(params["blocks"]) if b["type"] == "actions"]
    return [b["text"]["text"] for b in actions["elements"]]


def in_thread(text="On it", **fields) -> dict:
    return {
        "type": "message",
        "channel": "C2",
        "user": "U1",
        "text": text,
        "ts": "200.1",
        "thread_ts": "100.1",
    } | fields


def pressed(action: str, **fields) -> dict:
    return {
        "type": "block_actions",
        "trigger_id": f"trigger-{action}",
        "team": {"id": TEAM},
        "user": {"id": "U1"},
        "channel": {"id": "C2"},
        "message": {"ts": "100.1"},
        "actions": [{"action_id": action}],
    } | fields


# --- Connecting ---


def start(api, base) -> dict:
    """The query of the Slack page an owner is sent to."""
    url = api.post(f"{base}/slack/connect").json()["url"]
    assert url.startswith("https://slack.com/oauth/v2/authorize?")
    return {key: values[0] for key, values in parse_qs(urlsplit(url).query).items()}


def test_connecting_goes_through_slack_s_own_page(api, base, workspace, slack, membership):
    query = start(api, base)
    assert query["client_id"] == "client-1"
    assert query["redirect_uri"] == "https://chat.example.com/integrations/callback"
    assert set(query["scope"].split(",")) == set(SCOPES)

    back = api.job(api.post("/integrations/callback", {"code": "c1", "state": query["state"]}))["result"]
    assert (back["workspace"], back["plugin"]) == (workspace.slug, "slack")
    (sent,) = slack.sent("oauth.v2.access")
    assert sent["code"] == "c1" and sent["client_secret"] == "secret-1"
    row = Integration.objects.get()
    assert (row.account_id, row.account_name, row.credentials) == (TEAM, "Acme HQ", {"token": "xoxb-1"})
    assert row.connected_by == membership.user


def test_only_who_started_connecting_can_finish(api, base, workspace):
    state = start(api, base)["state"]
    other = Api(AuthTokenFactory(user=MembershipFactory(workspace=workspace).user).key)
    assert other.post("/integrations/callback", {"code": "c", "state": state}).status_code == 403
    assert api.post("/integrations/callback", {"code": "c", "state": state + "x"}).status_code == 400
    assert Api().post("/integrations/callback", {"code": "c", "state": state}).status_code == 401
    assert not Integration.objects.exists()


def test_a_link_kept_too_long_no_longer_connects(api, base, monkeypatch):
    state = start(api, base)["state"]
    later = time.time() + 3600
    monkeypatch.setattr("django.core.signing.time.time", lambda: later)
    assert api.post("/integrations/callback", {"code": "c", "state": state}).status_code == 400


def test_someone_who_lost_the_workspace_meanwhile_cannot_finish(api, base, membership):
    state = start(api, base)["state"]
    membership.delete()
    assert api.post("/integrations/callback", {"code": "c", "state": state}).status_code == 404


@pytest.mark.parametrize(
    "answer",
    [
        "invalid_code",
        httpx.Response(200, json={"ok": True, "access_token": "x", "team": None}),
        httpx.Response(200, json={"ok": True, "access_token": "x", "team": {"id": "T"}, "is_enterprise_install": True}),
        httpx.ConnectError("no route"),
    ],
)
def test_a_connection_that_does_not_work_is_not_saved(api, base, slack, answer):
    state = start(api, base)["state"]
    slack.errors["oauth.v2.access"] = [answer]
    assert api.job(api.post("/integrations/callback", {"code": "c", "state": state}))["error"]
    assert not Integration.objects.exists()


def test_not_set_up_on_this_server(api, base, settings):
    settings.PLUGIN_OPTIONS = {}
    (row,) = [r for r in api.get(base).json() if r["plugin"] == "slack"]
    assert not row["available"] and "PLUGIN_SLACK_CLIENT_ID" in row["missing_options"]


def test_the_manifest_asks_for_what_the_code_needs():
    """People make their Slack app from it: what is missing there fails only when used."""
    manifest = json.loads((Path(__file__).parent.parent / "plugins/slack/manifest.json").read_text())
    assert manifest["oauth_config"]["scopes"]["bot"] == list(SCOPES)
    assert manifest["settings"]["event_subscriptions"]["bot_events"] == list(BOT_EVENTS)
    assert manifest["oauth_config"]["redirect_urls"] == ["https://YOUR_DOMAIN/integrations/callback"]
    for part in ("event_subscriptions", "interactivity"):
        assert manifest["settings"][part]["request_url"] == f"https://YOUR_DOMAIN{WEBHOOK}"


# --- Choosing the channel ---


@pytest.fixture
def one(base, integration):
    return f"{base}/slack/{integration.pk}"


def test_the_channels_are_offered_by_name(api, one):
    options = api.job(api.post(f"{one}/options"))["result"]["options"]
    assert [o["label"] for o in options["channel"]] == ["#general", "#support", "private: vip"]


def test_more_channels_than_a_page(integration, slack):
    pages = [
        httpx.Response(
            200,
            json={"ok": True, "channels": [{"id": "C9", "name": "zzz"}], "response_metadata": {"next_cursor": "n"}},
        )
    ]
    slack.errors["conversations.list"] = pages
    assert len(slack_plugin.options(integration, "channel")) == 4
    assert slack.sent("conversations.list")[1]["cursor"] == "n"


def test_saving_joins_the_channel_and_sends_a_test(api, one, integration, slack):
    values = {"channel": "C1", "chats": "all", "mention": "here"}
    assert api.job(api.put(one, {"values": values}))["error"] == ""
    integration.refresh_from_db()
    assert integration.config == values
    assert slack.sent("conversations.join") == [{"channel": "C1"}]
    (test,) = slack.sent("chat.postMessage")
    assert test["channel"] == "C1" and integration.workspace.name in test["text"]
    assert {token for _, _, token in slack.calls} == {"xoxb-1"}


def test_a_private_channel_needs_no_joining(api, one, slack):
    slack.errors["conversations.join"] = ["method_not_supported_for_channel_type"]
    assert api.job(api.put(one, {"values": {"channel": "G1"}}))["error"] == ""


def test_a_channel_apps_cannot_post_in_is_not_saved(api, one, integration, slack):
    slack.errors["chat.postMessage"] = ["restricted_action_read_only_channel"]
    assert "doesn't let apps post" in api.job(api.put(one, {"values": {"channel": "C1"}}))["error"]
    integration.refresh_from_db()
    assert integration.config["channel"] == "C2"


# --- A chat that needs a person ---


def test_a_hand_off_starts_a_thread_with_the_chat_so_far(integration, conversation, slack):
    add_message(conversation, Message.Sender.VISITOR, "My order came broken")
    add_message(conversation, Message.Sender.BOT, "Sorry about that. See [orders](https://acme.com/o).")
    assert slack.calls == []  # the AI has it
    request_human(conversation, "wants a refund")

    root, story = slack.sent("chat.postMessage")
    assert root["channel"] == "C2" and "thread_ts" not in root
    for words in ("Maya needs a person", "wants a refund", conversation.workspace.name):
        assert words in text_of(root)
    assert buttons(root) == ["Open in inbox", "Resolve", "Back to AI"]
    assert f"/w/{conversation.workspace.slug}/inbox?c={conversation.pk}" in root["blocks"]
    assert story["thread_ts"] == "100.1"
    said = text_of(story)
    assert said.index("*Maya:* My order") < said.index("*AI:* Sorry") and "<https://acme.com/o|orders>" in said
    assert "note:" in said
    assert Thread.objects.get().external_id == "C2/100.1"


def test_the_link_to_the_page_says_where_it_goes(integration, conversation, slack):
    conversation.visitor.current_url = "https://evil.example/<x>|https://acme.com"
    conversation.visitor.save()
    request_human(conversation)
    assert "<https://evil.example/&lt;x&gt;%7Chttps://acme.com|evil.example/" in text_of(
        slack.sent("chat.postMessage")[0]
    )


def test_a_page_that_is_not_a_web_address_is_not_a_link(integration, conversation, slack):
    conversation.visitor.current_url = "javascript:alert(1)"
    conversation.visitor.save()
    request_human(conversation)
    assert "<javascript" not in text_of(slack.sent("chat.postMessage")[0])


@pytest.mark.parametrize(("verified", "shown"), [("verified", True), ("visitor", False)])
def test_whether_the_email_is_verified(integration, conversation, slack, verified, shown):
    visitor = conversation.visitor
    visitor.email = "maya@example.com"
    visitor.attributes = {"email": {"value": visitor.email, "source": verified}}
    visitor.save()
    request_human(conversation)
    text = text_of(slack.sent("chat.postMessage")[0])
    assert "maya@example.com" in text and ("(verified)" in text) is shown


def test_visitors_cannot_mention_people_or_disguise_links(integration, conversation, slack):
    conversation.visitor.name = "<!channel>"
    conversation.visitor.save()
    add_message(conversation, Message.Sender.VISITOR, "<!here> <https://evil.example|Click> & co")
    request_human(conversation, "<!everyone>")
    posted = "".join(json.dumps(p) for p in slack.sent("chat.postMessage"))
    for trick in ("<!channel>", "<!here>", "<!everyone>", "<https://evil.example|Click>"):
        assert trick not in posted
    assert all(p["unfurl_links"] == "false" for p in slack.sent("chat.postMessage"))


def test_the_chat_goes_on_in_the_thread(thread, conversation, slack, membership):
    add_message(conversation, Message.Sender.VISITOR, "Are you there?")
    reply_as(membership.user, conversation, "Yes, **one** moment")
    reply_as(membership.user, conversation, "courier again", is_note=True)
    posts = slack.sent("chat.postMessage")
    assert [p["thread_ts"] for p in posts] == ["100.1"] * 3
    assert "*Maya* (visitor)\nAre you there?" in text_of(posts[0])
    assert "Yes, *one* moment" in text_of(posts[1]) and membership.user.first_name in text_of(posts[1])
    assert "Note from" in text_of(posts[2])


def test_files_and_forms_are_mentioned(thread, conversation, slack, workspace):
    from apps.conversations.models import Attachment

    file = Attachment.objects.create(
        workspace=workspace, name="a|b>.png", url="https://cdn.example.com/a.png", content_type="image/png", size=1
    )
    add_message(conversation, Message.Sender.VISITOR, attachments=[file])
    add_message(conversation, Message.Sender.BOT, "Fill this in", form={"fields": []})
    files, form = slack.sent("chat.postMessage")
    assert "<https://cdn.example.com/a.png|a/b&gt;.png>" in text_of(files)
    assert "form" in text_of(form)


def test_a_visitor_leaving_their_email_shows_on_the_first_message(thread, conversation, slack):
    conversation.visitor.email = "maya@example.com"
    conversation.visitor.save()
    announce(CONTACT_UPDATED, conversation, data={"changed": ["email"]})
    assert "maya@example.com" in text_of(slack.sent("chat.update")[0])
    assert "Maya left their email" in slack.sent("chat.postMessage")[0]["text"]


def test_internal_system_notes_stay_out(thread, conversation, slack):
    add_message(conversation, Message.Sender.SYSTEM, "Bot looked up: secret", is_note=True)
    assert slack.calls == []


def test_what_is_said_before_the_thread_is_there_is_not_lost(integration, conversation, slack, monkeypatch):
    """A worker is slower than the chat: the AI's goodbye comes before the thread exists."""
    jobs = []
    monkeypatch.setattr("apps.integrations.deliveries.send_later", lambda *args, **kwargs: jobs.append(args))
    request_human(conversation)
    add_message(conversation, Message.Sender.BOT, "A teammate will reply here")
    add_message(conversation, Message.Sender.VISITOR, "Thanks")
    assert len(jobs) == 3
    for job in jobs:
        tasks.deliver(*job)
    said = "".join(text_of(p) for p in slack.sent("chat.postMessage"))
    assert said.count("A teammate will reply here") == 1 and said.count("Thanks") == 1


def test_with_the_ai_off_every_chat_needs_a_person(integration, conversation, slack, workspace):
    workspace.ai_enabled = False
    workspace.save()
    conversation.workspace.refresh_from_db()
    add_message(conversation, Message.Sender.VISITOR, "Hello?")
    root, story = slack.sent("chat.postMessage")
    assert "Maya needs a person" in text_of(root) and "Hello?" in text_of(story)
    assert "Back to AI" not in buttons(root)


def test_every_chat_can_be_shown(integration, conversation, slack):
    Integration.objects.update(config=integration.config | {"chats": "all"})
    add_message(conversation, Message.Sender.VISITOR, "Hello")
    add_message(conversation, Message.Sender.BOT, "Hi! How can I help?")
    root, story, answer = slack.sent("chat.postMessage")
    assert "The AI is answering Maya" in text_of(root) and "Hello" in text_of(story)
    assert "Hi! How can I help?" in text_of(answer)
    slack.calls.clear()
    request_human(conversation, "refund")
    (alert,) = slack.sent("chat.postMessage")
    # Seen in the channel again, not only in the thread.
    assert alert["reply_broadcast"] == "true" and "Maya needs a person" in text_of(alert) and "refund" in text_of(alert)
    assert "Maya needs a person" in text_of(slack.sent("chat.update")[0])


def test_nothing_is_sent_before_a_channel_is_chosen(integration, conversation, slack):
    Integration.objects.update(config={})
    request_human(conversation)
    assert slack.calls == [] and not Delivery.objects.exists()


def test_the_ai_handing_over_tells_the_team(integration, conversation, slack, llm, workspace, anon):
    workspace.organization.provider_keys = {"openrouter": "sk-or-test-key-1234"}
    workspace.organization.llm_model = "test/model"
    workspace.organization.save()
    llm(
        assistant(tool_call("handoff_to_human", {"reason": "Refund for a broken order"})),
        final("I'll get a teammate."),
    )
    anon.visitor_token = conversation.visitor.token
    anon.post(f"/widget/{workspace.public_key}/messages", {"body": "My order came broken"})
    said = "\n".join(text_of(p) for p in slack.sent("chat.postMessage"))
    for words in ("Refund for a broken order", "My order came broken", "I'll get a teammate."):
        assert words in said


# --- Mentions ---


def test_here_is_mentioned_if_asked(integration, conversation, slack):
    Integration.objects.update(config=integration.config | {"mention": "here"})
    request_human(conversation)
    assert "<!here>" in text_of(slack.sent("chat.postMessage")[0])


def test_the_assignee_is_mentioned_if_they_are_in_this_slack(integration, conversation, slack, priya):
    Integration.objects.update(config=integration.config | {"mention": "assignee"})
    priya.email = "Priya@acme.com"
    priya.save()
    conversation.assignee = priya
    conversation.save()
    request_human(conversation)
    assert "<@U1>" in text_of(slack.sent("chat.postMessage")[0])


def test_an_assignee_who_is_not_in_this_slack_is_not_missed(integration, conversation, slack, priya):
    Integration.objects.update(config=integration.config | {"mention": "assignee"})
    conversation.assignee = priya
    conversation.save()
    slack.errors["users.lookupByEmail"] = ["users_not_found"]
    request_human(conversation)
    assert "Maya needs a person" in text_of(slack.sent("chat.postMessage")[0])


# --- The first message follows the conversation ---


def test_resolving_reopening_and_giving_back_show_on_the_first_message(thread, conversation, slack, priya):
    set_status(conversation, "resolved", by=priya)
    set_status(conversation, "open", by=priya)
    set_human_requested(conversation, False, by=priya)
    resolved, reopened, ai = slack.sent("chat.update")
    assert resolved["ts"] == "100.1"
    assert "Resolved: Maya" in text_of(resolved) and buttons(resolved) == ["Open in inbox", "Reopen"]
    assert "wants a refund" in text_of(reopened)
    assert "The AI is answering Maya" in text_of(ai) and buttons(ai) == ["Open in inbox", "Resolve"]
    lines = [p["text"] for p in slack.sent("chat.postMessage")]
    assert "Resolved by Priya" in lines[0] and "Reopened by Priya" in lines[1] and "AI by Priya" in lines[2]


def test_a_first_message_someone_deleted_is_not_a_problem(thread, conversation, slack, integration):
    slack.errors["chat.update"] = ["message_not_found"]
    set_status(conversation, "resolved")
    integration.refresh_from_db()
    assert len(slack.sent("chat.postMessage")) == 1 and integration.last_error == ""


# --- Replying from Slack ---


def test_a_reply_in_the_thread_reaches_the_visitor(thread, conversation, slack, priya):
    assert post_event(in_thread("Refunded!")).status_code == 200
    message = conversation.messages.last()
    assert (message.body, message.sender, message.author, message.is_note) == ("Refunded!", "agent", priya, False)
    conversation.refresh_from_db()
    assert conversation.assignee == priya
    assert slack.sent("reactions.add") == [{"channel": "C2", "timestamp": "200.1", "name": "white_check_mark"}]
    # It isn't posted back into the thread.
    assert slack.sent("chat.postMessage") == []


def test_the_visitor_s_widget_gets_it(thread, conversation, priya, workspace, anon):
    post_event(in_thread("Refunded!"))
    anon.visitor_token = conversation.visitor.token
    messages = anon.get(f"/widget/{workspace.public_key}/messages").json()["messages"]
    assert messages[-1]["body"] == "Refunded!" and messages[-1]["author_name"] == "Priya"


@pytest.mark.parametrize("text", ["note: same courier", "NOTE:same courier", "  Note:  same courier"])
def test_a_note_stays_with_the_team(thread, conversation, slack, text):
    post_event(in_thread(text))
    message = conversation.messages.last()
    assert (message.body, message.is_note) == ("same courier", True)
    assert slack.sent("reactions.add")[0]["name"] == "memo"


def test_a_note_in_bold_is_still_a_note(thread, conversation):
    """Formatting the word must not send the team's words to the visitor."""
    section = {"type": "rich_text_section", "elements": [{"type": "text", "text": "note:", "style": {"bold": True}}]}
    section["elements"].append({"type": "text", "text": " same courier"})
    post_event(in_thread("*note:* same courier", blocks=[{"type": "rich_text", "elements": [section]}]))
    message = conversation.messages.last()
    assert message.is_note and "same courier" in message.body


def test_the_same_event_sent_again_is_one_reply(thread, conversation):
    before = conversation.messages.count()
    for _ in range(3):
        assert post_event(in_thread()).status_code == 200
    assert conversation.messages.count() == before + 1


@pytest.mark.parametrize(
    "event",
    [
        in_thread(bot_id="B1"),
        in_thread(subtype="message_changed"),
        in_thread(subtype="message_deleted"),
        in_thread(subtype="bot_message"),
        in_thread(subtype="channel_join"),
        in_thread(thread_ts=None),
        in_thread(ts="100.1"),
        in_thread(user=None),
        in_thread(thread_ts="999.9"),
        in_thread(channel="C1"),
        in_thread(text="   "),
        in_thread(text="note:"),
        {"type": "reaction_added", "user": "U1"},
    ],
)
def test_everything_else_in_the_channel_is_left_alone(thread, conversation, slack, event):
    before = conversation.messages.count()
    assert post_event(event).status_code == 200
    assert conversation.messages.count() == before and slack.sent("reactions.add") == []


def test_another_slack_s_thread_with_the_same_id_is_not_ours(thread, conversation):
    before = conversation.messages.count()
    post_event(in_thread(), team="T2")
    assert conversation.messages.count() == before


def test_one_slack_for_two_workspaces(thread, conversation, slack, priya):
    other = WorkspaceFactory()
    MembershipFactory(user=priya, workspace=other)
    Integration.objects.create(
        workspace=other, plugin="slack", account_id=TEAM, credentials={"token": "xoxb-1"}, config={"channel": "C2"}
    )
    theirs = ConversationFactory(workspace=other)
    request_human(theirs)
    ts = Thread.objects.get(conversation=theirs).external_id.split("/")[1]
    post_event(in_thread("for them", thread_ts=ts))
    assert theirs.messages.last().body == "for them"
    assert not conversation.messages.filter(body="for them").exists()


# --- Who may reply ---


def refused(conversation, slack, words="Not sent"):
    (whisper,) = slack.sent("chat.postEphemeral")
    assert whisper["user"] == "U9" and whisper["thread_ts"] == "100.1" and words in whisper["text"]
    assert not conversation.messages.filter(sender="agent").exists()
    assert slack.sent("reactions.add") == []


@pytest.mark.parametrize(
    "person",
    [
        {"email": "stranger@acme.com"},
        {"email": ""},
        # Their Slack, not ours, says what their email is.
        {"email": "priya@acme.com", "team_id": "T2"},
        {"email": "priya@acme.com", "is_stranger": True},
        {"email": "priya@acme.com", "is_bot": True},
        {"email": "priya@acme.com", "deleted": True},
        {"email": "priya@acme.com", "is_email_confirmed": False},
    ],
)
def test_only_teammates_can_reply(thread, conversation, slack, person):
    slack.person("U9", person.pop("email"), **person)
    post_event(in_thread("let me in", user="U9"))
    refused(conversation, slack)


def test_a_member_of_another_workspace_cannot_reply(thread, conversation, slack):
    stranger = MembershipFactory().user
    slack.person("U9", stranger.email)
    post_event(in_thread("let me in", user="U9"))
    refused(conversation, slack)


def test_someone_removed_from_the_workspace_can_no_longer_reply(thread, conversation, slack, priya, workspace):
    post_event(in_thread("first"), id="Ev1")
    workspace.memberships.filter(user=priya).delete()
    post_event(in_thread("second"), id="Ev2")
    assert not conversation.messages.filter(body="second").exists()


def test_only_teammates_can_press_buttons(thread, conversation, slack):
    slack.person("U9", "stranger@acme.com")
    post_action(pressed("resolve", user={"id": "U9"}))
    refused(conversation, slack, "Nothing was changed")
    conversation.refresh_from_db()
    assert conversation.status == "open"


def test_slack_being_down_when_looking_someone_up_is_tried_again(thread, conversation, slack):
    slack.errors["users.info"] = [httpx.ConnectError("no route")]
    post_event(in_thread("Refunded!"))
    assert conversation.messages.filter(body="Refunded!").count() == 1


def test_a_tick_that_fails_does_not_send_the_reply_twice(thread, conversation, slack):
    slack.errors["reactions.add"] = [httpx.ConnectError("no route")]
    post_event(in_thread("Refunded!"))
    assert conversation.messages.filter(body="Refunded!").count() == 1


def test_files_are_not_sent_and_the_sender_knows(thread, conversation, slack):
    post_event(in_thread("See this", subtype="file_share", files=[{"id": "F1"}]), id="Ev1")
    assert conversation.messages.last().body == "See this"
    before = conversation.messages.count()
    post_event(in_thread("", subtype="file_share", files=[{"id": "F1"}]), id="Ev2")
    assert conversation.messages.count() == before
    assert [w["user"] for w in slack.sent("chat.postEphemeral")] == ["U1", "U1"]


# --- Buttons ---


def test_the_buttons_act_as_the_teammate(thread, conversation, slack, priya):
    assert post_action(pressed("resolve")).status_code == 200
    conversation.refresh_from_db()
    assert conversation.status == Conversation.Status.RESOLVED
    assert "Resolved by Priya" in slack.sent("chat.postMessage")[0]["text"]
    post_action(pressed("reopen"))
    post_action(pressed("to_ai"))
    conversation.refresh_from_db()
    assert conversation.status == "open" and not conversation.human_requested


@pytest.mark.parametrize(
    "payload",
    [pressed("open"), pressed("something_else"), {"type": "view_submission"}, pressed("resolve", team={"id": "T2"})],
)
def test_other_presses_change_nothing(thread, conversation, payload):
    assert post_action(payload).status_code == 200
    conversation.refresh_from_db()
    assert conversation.status == "open"


# --- Genuine requests only ---


def test_the_address_is_confirmed_to_slack():
    body = json.dumps({"type": "url_verification", "challenge": "abc"}).encode()
    assert post(body, "application/json").json() == {"challenge": "abc"}


@pytest.mark.parametrize(
    "headers",
    [
        lambda body: signed(body, secret="wrong"),
        lambda body: signed(b"something else"),
        lambda body: signed(body, at=time.time() - 600),
        lambda body: signed(body, at=time.time() + 600),
        lambda body: signed(body) | {"X-Slack-Request-Timestamp": "soon"},
        lambda body: signed(body) | {"X-Slack-Request-Timestamp": "²"},
        lambda body: signed(body) | {"X-Slack-Signature": "v0=é"},
        lambda body: {"X-Other": "1"},
    ],
)
def test_requests_slack_did_not_sign_are_refused(thread, conversation, headers):
    event = {"type": "event_callback", "team_id": TEAM, "event_id": "E", "event": in_thread()}
    body = json.dumps(event).encode()
    before = conversation.messages.count()
    assert post(body, "application/json", headers=headers(body)).status_code == 401
    assert conversation.messages.count() == before


@pytest.mark.parametrize("body", [b"not json", b"[]", b"{}", b'{"type": "event_callback"}', b"null"])
def test_nonsense_is_refused(body):
    assert post(body, "application/json").status_code == 400
    assert post(body, "application/x-www-form-urlencoded").status_code == 400


# --- When things go wrong ---


def test_a_busy_slack_is_tried_again_without_posting_twice(integration, conversation, slack):
    """The first message went out, the rest of the thread didn't: the next try goes on from there."""
    add_message(conversation, Message.Sender.VISITOR, "Hello")
    real, slow = slack.answer, iter([False, True])

    def answer(method, params):
        if method == "chat.postMessage" and next(slow, False):
            raise httpx.ReadTimeout("slow")
        return real(method, params)

    slack.answer = answer
    request_human(conversation)
    assert Delivery.objects.get().attempts == 1 and Thread.objects.count() == 1
    Delivery.objects.update(due_at=timezone.now())
    tasks.deliver(integration.pk, conversation.pk)
    roots = [p for p in slack.sent("chat.postMessage") if "thread_ts" not in p]
    assert len(roots) == 1 and not Delivery.objects.exists()
    assert "Hello" in text_of(slack.sent("chat.postMessage")[-1])
    assert not any("again" in text_of(p) for p in slack.sent("chat.postMessage"))


@pytest.mark.parametrize(
    ("answer", "retried"),
    [
        (httpx.Response(429, headers={"Retry-After": "42"}, json={"ok": False}), True),
        (httpx.Response(503, text="oops"), True),
        (httpx.Response(200, text="not json"), True),
        ("internal_error", True),
        (httpx.ConnectError("no route"), True),
        ("channel_not_found", False),
        ("invalid_auth", False),
    ],
)
def test_which_failures_are_worth_another_try(integration, conversation, slack, answer, retried):
    slack.errors["chat.postMessage"] = [answer]
    request_human(conversation)
    assert Delivery.objects.get().status == ("pending" if retried else "failed")
    integration.refresh_from_db()
    assert bool(integration.last_error) is not retried


def test_the_owner_sees_why_it_stopped(api, base, one, integration, conversation, slack):
    slack.errors["chat.postMessage"] = ["is_archived"]
    request_human(conversation)
    assert api.get(base).json()[0]["connections"][0]["last_error"] == "The channel is archived. Pick another."
    api.put(one, {"values": {"channel": "C1"}})
    assert api.get(base).json()[0]["connections"][0]["last_error"] == ""


def test_a_thread_in_a_channel_that_is_gone_moves_to_the_new_one(thread, conversation, slack, integration):
    Integration.objects.update(config=integration.config | {"channel": "C1"})
    slack.errors["chat.postMessage"] = ["is_archived"]
    add_message(conversation, Message.Sender.VISITOR, "Still there?")
    assert Thread.objects.get().external_id.startswith("C1/")
    assert "Still there?" in text_of(slack.sent("chat.postMessage")[-1])


def test_being_removed_in_slack_stops_everything_and_says_so(thread, conversation, slack, integration):
    slack.errors["auth.test"] = ["account_inactive"]
    post_event({"type": "app_uninstalled"})
    integration.refresh_from_db()
    assert integration.credentials == {} and "removed from Slack" in integration.last_error
    slack.calls.clear()
    add_message(conversation, Message.Sender.VISITOR, "Hello?")
    assert slack.calls == [] and not Delivery.objects.exists()


def test_old_news_of_being_removed_does_not_end_a_new_connection(thread, integration):
    post_event({"type": "tokens_revoked", "tokens": {"bot": ["U0"]}})
    integration.refresh_from_db()
    assert integration.credentials == {"token": "xoxb-1"}


def test_connecting_again_restores_the_channel_and_the_threads(api, base, thread, integration):
    Integration.objects.update(credentials={}, last_error="removed")
    api.post("/integrations/callback", {"code": "c", "state": start(api, base)["state"]})
    integration.refresh_from_db()
    assert integration.credentials == {"token": "xoxb-1"} and integration.last_error == ""
    assert integration.config["channel"] == "C2" and Thread.objects.exists()


def test_disconnecting_gives_the_token_back_unless_another_workspace_uses_it(api, base, integration, slack):
    other = Integration.objects.create(
        workspace=WorkspaceFactory(), plugin="slack", account_id=TEAM, credentials={"token": "xoxb-1"}
    )
    api.delete(f"{base}/slack/{integration.pk}")
    assert "auth.revoke" not in slack.methods
    other.workspace = integration.workspace
    other.save()
    api.delete(f"{base}/slack/{other.pk}")
    assert "auth.revoke" in slack.methods and slack.calls[-1][2] == "xoxb-1"
