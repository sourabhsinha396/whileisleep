"""Slack: a conversation that needs a person is a thread in the team's channel, and what
teammates reply there goes to the visitor.

The thread's id is "<channel>/<timestamp of its first message>". One Slack can serve several
workspaces: each finds its own threads.
"""

import hashlib
import hmac
import json
import logging
import re
import time
from pathlib import Path
from urllib.parse import parse_qs

from django.core.cache import cache

from apps.integrations.sdk import (
    AI_RESUMED,
    MESSAGE,
    PERSON_REQUESTED,
    REOPENED,
    RESOLVED,
    BadRequest,
    Connection,
    Event,
    Field,
    Integration,
    Job,
    Message,
    Option,
    Plugin,
    Received,
    Thread,
    WebhookRequest,
    add_note,
    display_name,
    find_thread,
    give_to_ai,
    integrations_of_account,
    link_thread,
    needs_person,
    reopen,
    reply,
    resolve,
    teammate,
    thread_expected,
    thread_of,
    transcript,
)

from . import client, posts, text
from .client import SlackError

log = logging.getLogger(__name__)

SCOPES = (
    "channels:history",
    "channels:join",
    "channels:read",
    "chat:write",
    "groups:history",
    "groups:read",
    "reactions:write",
    "users:read",
    "users:read.email",
)
BOT_EVENTS = ("app_uninstalled", "message.channels", "message.groups", "tokens_revoked")
ICON = (Path(__file__).parent / "icon.svg").read_text(encoding="utf-8")

# A request older (or newer) than this is refused, so a captured one can't be replayed later.
TOLERANCE_SECONDS = 300
TRANSCRIPT_MESSAGES = 8
EMAIL_CACHE_SECONDS = 600
# In any formatting: a bold "note:" is still a note.
NOTE = re.compile(r"^[\s*_]*note\s*:[*_]*\s*", re.IGNORECASE)
# What a person typed; every other kind of message event is Slack's own bookkeeping.
TYPED = {None, "file_share", "thread_broadcast"}
FILES_NOT_SENT = "Files can't be sent from Slack yet. Attach them in the inbox."


class SlackPlugin(Plugin):
    id = "slack"
    name = "Slack"
    description = "Get told when a chat needs you, and answer it from Slack."
    notice = "Everyone in the channel can read these chats. Only members of this workspace can answer them."
    icon = ICON
    server_options = ("CLIENT_ID", "CLIENT_SECRET", "SIGNING_SECRET")
    save_label = "Save and send a test"
    settings_fields = (
        Field(
            "channel",
            "Channel",
            kind="select",
            help="For a private channel, invite whileisleep to it in Slack first.",
        ),
        Field(
            "chats",
            "Tell us about",
            kind="choice",
            options=(Option("person", "Chats that need a person"), Option("all", "Every chat, as it happens")),
            default="person",
        ),
        Field(
            "mention",
            "Mention in Slack",
            kind="choice",
            options=(
                Option("nobody", "Nobody"),
                Option("here", "@here"),
                Option("assignee", "The person the chat is assigned to"),
            ),
            default="nobody",
        ),
    )

    # --- Connecting ---

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        return client.authorize_url(self.option("CLIENT_ID"), SCOPES, state, redirect_uri)

    def finish_authorization(self, code: str, redirect_uri: str) -> Connection:
        answer = client.call(
            "oauth.v2.access",
            client_id=self.option("CLIENT_ID"),
            client_secret=self.option("CLIENT_SECRET"),
            code=code,
            redirect_uri=redirect_uri,
        )
        team, token = answer.get("team") or {}, answer.get("access_token")
        if not team.get("id") or not token or answer.get("is_enterprise_install"):
            raise SlackError(message="Install whileisleep in one Slack workspace, not a whole organization.")
        return Connection(team["id"], team.get("name") or "Slack", {"token": token})

    def disconnect(self, integration: Integration) -> None:
        # The token is the Slack's, not the workspace's: another workspace may still use it.
        if not integrations_of_account(self, integration.account_id).exists():
            client.call("auth.revoke", self.token(integration))

    def token(self, integration: Integration) -> str:
        return integration.credentials.get("token", "")

    # --- Settings ---

    def options(self, integration: Integration, name: str) -> list[Option]:
        return [
            Option(channel["id"], f"{'private: ' if channel.get('is_private') else '#'}{channel['name']}")
            for channel in client.channels(self.token(integration))
        ]

    def check_settings(self, integration: Integration) -> None:
        values = integration.config
        client.join(self.token(integration), values["channel"])
        which = "Every chat" if values["chats"] == "all" else "Chats that need a person"
        name = text.escape(integration.workspace.name)
        client.call(
            "chat.postMessage",
            self.token(integration),
            channel=values["channel"],
            text=f":wave: It works. {which} from *{name}* will show up here.",
        )

    # --- To Slack ---

    def wants(self, integration: Integration, event: Event) -> bool:
        if not integration.config.get("channel") or not self.token(integration):
            return False
        if event.name == MESSAGE and event.message.sender == Message.Sender.SYSTEM:
            return False
        return self.starts(integration, event) or thread_expected(integration, event.conversation)

    def starts(self, integration: Integration, event: Event) -> bool:
        """Whether a conversation without a thread gets one for this."""
        if event.name == PERSON_REQUESTED:
            return True
        if event.name != MESSAGE or event.message.sender != Message.Sender.VISITOR:
            return False
        return integration.config.get("chats") == "all" or needs_person(event.conversation)

    def deliver(self, integration: Integration, event: Event) -> None:
        thread = thread_of(integration, event.conversation)
        try:
            if thread is None:
                if self.starts(integration, event):
                    self.start(integration, event)
                return
            self.follow(integration, thread, event)
        except SlackError as error:
            if error.code not in client.CHANNEL_GONE or thread is None:
                raise
            if thread.external_id.split("/")[0] == integration.config.get("channel"):
                raise
            # It was in a channel that is gone, and another has been chosen since.
            thread.delete()
            if self.starts(integration, event):
                self.start(integration, event)

    def start(self, integration: Integration, event: Event) -> None:
        conversation, channel = event.conversation, integration.config["channel"]
        reason = event.data.get("reason", "")
        post = posts.root(conversation, reason, self.mention(integration, conversation))
        sent = self.post(integration, channel, post)
        # Linked at once: if what follows fails, the next try continues this thread.
        thread = link_thread(integration, conversation, f"{channel}/{sent['ts']}", reason=reason, seen=0)
        self.catch_up(integration, thread)

    def follow(self, integration: Integration, thread: Thread, event: Event) -> None:
        caught_up = self.catch_up(integration, thread)
        if event.name == MESSAGE:
            if event.message.pk > thread.data["seen"]:
                self.post_in(integration, thread, posts.said(event.message))
            return
        if event.name == PERSON_REQUESTED:
            thread.data["reason"] = event.data.get("reason", "")
            thread.save(update_fields=["data"])
        # First what can be done twice without harm.
        self.update_root(integration, thread, event)
        if caught_up and event.name == PERSON_REQUESTED:
            # Another try at what started the thread: its first message says so already.
            return
        self.post_in(integration, thread, {"text": self.line(integration, event)}, aloud=event.name == PERSON_REQUESTED)

    def catch_up(self, integration: Integration, thread: Thread) -> bool:
        """The chat up to now, once, at the top of the thread. Whether that was just now."""
        if thread.data["seen"]:
            return False
        messages = transcript(thread.conversation, TRANSCRIPT_MESSAGES)
        self.post_in(integration, thread, posts.transcript(messages))
        thread.data["seen"] = messages[-1].pk if messages else 1
        thread.save(update_fields=["data"])
        return True

    def line(self, integration: Integration, event: Event) -> str:
        by = f" by {text.escape(display_name(event.by))}" if event.by else ""
        if event.name == PERSON_REQUESTED:
            reason = text.escape(event.data.get("reason", ""))
            mention = self.mention(integration, event.conversation)
            name = text.escape(event.conversation.visitor.display_name)
            return text.clip(f"{mention} :bell: {name} needs a person again.{' ' + reason if reason else ''}".strip())
        return {
            RESOLVED: f":white_check_mark: Resolved{by}",
            REOPENED: f":arrows_counterclockwise: Reopened{by}",
            AI_RESUMED: f":robot_face: Given back to the AI{by}",
        }[event.name]

    def mention(self, integration: Integration, conversation) -> str:
        choice = integration.config.get("mention")
        if choice == "here":
            return "<!here>"
        if choice == "assignee" and conversation.assignee:
            try:
                found = client.call("users.lookupByEmail", self.token(integration), email=conversation.assignee.email)
                return f"<@{found['user']['id']}>"
            except SlackError as error:
                # Not in this Slack: nobody to mention. Anything else isn't worth losing the post.
                log.info("No Slack user to mention: %s", error)
        return ""

    def post(self, integration: Integration, channel: str, post: dict, **extra) -> dict:
        return client.call(
            "chat.postMessage",
            self.token(integration),
            channel=channel,
            unfurl_links=False,
            unfurl_media=False,
            **post,
            **extra,
        )

    def post_in(self, integration: Integration, thread: Thread, post: dict, aloud: bool = False) -> None:
        """`aloud` shows it in the channel too."""
        channel, ts = thread.external_id.split("/")
        self.post(integration, channel, post, thread_ts=ts, reply_broadcast=aloud or None)

    def update_root(self, integration: Integration, thread: Thread, event: Event) -> None:
        channel, ts = thread.external_id.split("/")
        post = posts.root(event.conversation, thread.data.get("reason", ""))
        try:
            client.call("chat.update", self.token(integration), channel=channel, ts=ts, **post)
        except SlackError as error:
            # Someone deleted it. The thread still says what happened.
            if error.code not in ("message_not_found", "cant_update_message", "edit_window_closed"):
                raise

    # --- From Slack ---

    def receive(self, request: WebhookRequest) -> Received:
        self.check_signature(request)
        try:
            if request.headers.get("Content-Type", "").startswith("application/x-www-form-urlencoded"):
                return self.pressed(json.loads(parse_qs(request.body.decode())["payload"][0]))
            return self.happened(json.loads(request.body))
        except (ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
            raise BadRequest("Not a Slack request.") from error

    def check_signature(self, request: WebhookRequest) -> None:
        sent, timestamp = (request.headers.get(f"X-Slack-{name}", "") for name in ("Signature", "Request-Timestamp"))
        if not re.fullmatch(r"[0-9]{1,12}", timestamp) or abs(time.time() - int(timestamp)) > TOLERANCE_SECONDS:
            raise BadRequest("Bad signature.", 401)
        base = f"v0:{timestamp}:".encode() + request.body
        expected = "v0=" + hmac.new(self.option("SIGNING_SECRET").encode(), base, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected.encode(), sent.encode()):
            raise BadRequest("Bad signature.", 401)

    def happened(self, data: dict) -> Received:
        if data["type"] == "url_verification":
            return Received(body={"challenge": data["challenge"]})
        if data["type"] != "event_callback":
            return Received()
        event, team = data["event"], data["team_id"]
        if event["type"] == "app_uninstalled" or (event["type"] == "tokens_revoked" and event["tokens"].get("bot")):
            return Received(jobs=(Job(data["event_id"], {"kind": "removed", "team": team}),))
        if event["type"] != "message" or event.get("subtype") not in TYPED or event.get("bot_id"):
            return Received()
        thread_ts = event.get("thread_ts")
        if not event.get("user") or not thread_ts or thread_ts == event["ts"]:
            return Received()
        payload = {
            "kind": "message",
            "team": team,
            "thread": f"{event['channel']}/{thread_ts}",
            "ts": event["ts"],
            "user": event["user"],
            "text": event.get("text", ""),
            "blocks": event.get("blocks") or [],
            "files": bool(event.get("files")),
        }
        return Received(jobs=(Job(data["event_id"], payload),))

    def pressed(self, data: dict) -> Received:
        if data["type"] != "block_actions" or data["actions"][0]["action_id"] not in ACTIONS:
            return Received()
        payload = {
            "kind": "action",
            "team": data["team"]["id"],
            "thread": f"{data['channel']['id']}/{data['message']['ts']}",
            "user": data["user"]["id"],
            "action": data["actions"][0]["action_id"],
        }
        return Received(jobs=(Job(data["trigger_id"], payload),))

    def handle(self, payload: dict) -> None:
        if payload["kind"] == "removed":
            self.removed(payload["team"])
            return
        thread = find_thread(self, payload["team"], payload["thread"])
        if thread is None or not self.token(thread.integration):
            return
        user = self.teammate(thread, payload["team"], payload["user"])
        if user is None:
            name = text.escape(thread.conversation.workspace.name)
            why = f"Your Slack email isn't a member of {name} in whileisleep. Ask its owner to add you."
            done = "Not sent to the visitor" if payload["kind"] == "message" else "Nothing was changed"
            self.whisper(thread, payload["user"], f"{done}. {why}")
        elif payload["kind"] == "action":
            ACTIONS[payload["action"]](thread.integration, thread.conversation, user)
        else:
            self.answer(thread, payload, user)

    def answer(self, thread: Thread, payload: dict, user) -> None:
        body = text.to_markdown(payload["blocks"], payload["text"])
        note = bool(NOTE.match(body))
        body = NOTE.sub("", body, count=1) if note else body
        if body:
            send = add_note if note else reply
            send(thread.integration, thread.conversation, user, body)
            self.react(thread, payload["ts"], "memo" if note else "white_check_mark")
        if payload["files"]:
            self.whisper(thread, payload["user"], FILES_NOT_SENT)

    def teammate(self, thread: Thread, team: str, slack_user: str):
        """The workspace's member this Slack person is, by the email Slack has for them. Someone from
        another Slack (a shared channel) is nobody: their email is whatever that Slack says."""
        key = f"slack-email:{team}:{slack_user}"
        email = cache.get(key)
        if email is None:
            person = client.call("users.info", self.token(thread.integration), user=slack_user)["user"]
            ours = person.get("team_id") == team and not person.get("is_stranger")
            real = not person.get("is_bot") and not person.get("deleted") and person.get("is_email_confirmed", True)
            email = ((person.get("profile") or {}).get("email") or "") if ours and real else ""
            cache.set(key, email, EMAIL_CACHE_SECONDS)
        return teammate(thread.conversation.workspace, email)

    def whisper(self, thread: Thread, slack_user: str, message: str) -> None:
        """Only that person sees it."""
        channel, ts = thread.external_id.split("/")
        self.quietly(thread, "chat.postEphemeral", channel=channel, thread_ts=ts, user=slack_user, text=message)

    def react(self, thread: Thread, ts: str, name: str) -> None:
        self.quietly(thread, "reactions.add", channel=thread.external_id.split("/")[0], timestamp=ts, name=name)

    def quietly(self, thread: Thread, method: str, **params) -> None:
        """What was asked is done already: trying it all again for this would do it twice."""
        try:
            client.call(method, self.token(thread.integration), **params)
        except SlackError as error:
            log.warning("Slack %s: %s", method, error)

    def removed(self, team: str) -> None:
        """Someone removed whileisleep in Slack. Kept, so connecting again restores the channel."""
        for integration in integrations_of_account(self, team):
            try:
                # It may be news from before they connected again.
                client.call("auth.test", self.token(integration))
            except SlackError as error:
                if error.code not in client.DISCONNECTED:
                    raise
                integration.credentials = {}
                integration.last_error = "whileisleep was removed from Slack. Connect it again."
                integration.save(update_fields=["credentials", "last_error"])


ACTIONS = {posts.RESOLVE: resolve, posts.REOPEN: reopen, posts.TO_AI: give_to_ai}
