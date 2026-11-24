"""Webhooks: any system hears what happens in chats, and can answer them.

Out: signed JSON to the owner's endpoints, for the events each chose (payload.py).
In: a request signed with the same secret replies, writes a note, or changes a conversation.
frontend/content/docs/webhooks.md is for the people on the other end.
"""

import json
import secrets
from urllib.parse import urlsplit

from django.conf import settings
from django.utils import timezone

from apps.integrations.sdk import (
    BadRequest,
    Connection,
    Event,
    Field,
    Integration,
    Job,
    Plugin,
    PluginError,
    Received,
    Shown,
    WebhookRequest,
    add_note,
    conversation_in,
    find_integration,
    give_to_ai,
    icon_of,
    reopen,
    reply,
    request,
    resolve,
    teammate,
    webhook_url,
)

from . import payload, signing

USER_AGENT = "whileisleep-webhooks/1"
MAX_TEXT = 10000
# What people may ask for, and whether it takes a text.
WRITE = {"reply": reply, "note": add_note}
CHANGE = {"resolve": resolve, "reopen": reopen, "give_to_ai": give_to_ai}


class WebhooksPlugin(Plugin):
    id = "webhooks"
    name = "Webhooks"
    description = "Tell any system what happens in your chats, and let it answer them."
    notice = "Works with Zapier, Make, n8n or your own server. Each endpoint gets what visitors write and who they are."
    icon = icon_of(__file__)
    many = True
    keeps_log = True
    save_label = "Save and send a test"
    connect_fields = (Field("url", "Endpoint", placeholder="https://example.com/whileisleep"),)
    settings_fields = (
        Field("url", "Endpoint"),
        Field("events", "Send when", kind="choices", options=payload.CHOICES, default=payload.DEFAULT),
        Field(
            "authorization",
            "Authorization header",
            kind="secret",
            required=False,
            help="Only if your endpoint asks for one, for example: Bearer abc123.",
        ),
    )

    # --- Connecting ---

    def connect(self, values: dict) -> Connection:
        host = check_url(values["url"])
        account = secrets.token_urlsafe(12)
        return Connection(account, host, {"secret": signing.new_secret()}, {"url": values["url"]})

    def shown(self, integration: Integration) -> list[Shown]:
        return [
            Shown("Signing secret", integration.credentials["secret"], True, "Check each request came from us."),
            Shown("Endpoint id", integration.account_id, help="To answer chats: the webhook-endpoint header."),
            Shown("Answer at", webhook_url(self), help="Send signed requests here to reply to chats."),
        ]

    def check_settings(self, integration: Integration) -> None:
        integration.account_name = check_url(integration.config["url"])
        test = {
            "id": f"msg_test_{secrets.token_hex(8)}",
            "type": "test",
            "created_at": timezone.now().isoformat(),
            "workspace": payload.workspace_out(integration.workspace),
            "data": {},
        }
        try:
            self.send(integration, test)
        except PluginError as error:
            raise PluginError(f"The test didn't work, so nothing was saved. {error}") from error

    # --- Out ---

    def wants(self, integration: Integration, event: Event) -> bool:
        if event.origin == integration.origin:
            # It asked for that itself.
            return False
        type = payload.type_of(event)
        return bool(type) and type in integration.config.get("events", "").split(",")

    def deliver(self, integration: Integration, event: Event) -> str:
        return self.send(integration, payload.build(event))

    def send(self, integration: Integration, data: dict) -> str:
        body = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
        headers |= signing.headers(integration.credentials["secret"], data["id"], body)
        if authorization := integration.credentials.get("authorization"):
            headers["Authorization"] = authorization
        response = request("POST", integration.config["url"], customer_address=True, headers=headers, content=body)
        status = response.status_code
        if 200 <= status < 300:
            return f"HTTP {status}"
        if status == 410:
            raise PluginError("The endpoint says it is gone (HTTP 410).")
        if 300 <= status < 400:
            raise PluginError(f"The endpoint redirects (HTTP {status}). Use the address it leads to.")
        after = response.headers.get("Retry-After", "")
        raise PluginError(
            f"The endpoint answered HTTP {status}.", retry=True, after=int(after) if after.isdecimal() else None
        )

    # --- In ---

    def receive(self, request: WebhookRequest) -> Received:
        integration = find_integration(self, request.headers.get("webhook-endpoint", ""))
        # The same answer whichever is wrong, so ids can't be tried out.
        if integration is None or not signing.is_genuine(
            integration.credentials["secret"], request.headers, request.body
        ):
            raise BadRequest("Bad signature, or no such endpoint.", 401)
        try:
            data = json.loads(request.body)
        except ValueError:
            data = None
        if not isinstance(data, dict):
            raise BadRequest("Send a JSON object.")
        action, text = data.get("action"), data.get("text", "")
        if not isinstance(action, str) or (action not in WRITE and action not in CHANGE):
            raise BadRequest(f"action must be one of: {', '.join([*WRITE, *CHANGE])}.")
        if action in WRITE and (not isinstance(text, str) or not 0 < len(text.strip()) <= MAX_TEXT):
            raise BadRequest(f"text must be 1 to {MAX_TEXT} characters.")
        conversation = conversation_in(integration, data.get("conversation_id"))
        if conversation is None:
            raise BadRequest("No such conversation.", 404)
        if self.author(integration, data.get("author_email")) is None:
            raise BadRequest("author_email must be a member of the workspace.")
        work = {
            "endpoint": integration.account_id,
            "conversation": conversation.pk,
            "action": action,
            "text": text.strip() if action in WRITE else "",
            "author": data.get("author_email") or "",
        }
        return Received(
            jobs=(Job(f"{integration.account_id}:{request.headers['webhook-id']}", work),), body={"ok": True}
        )

    def author(self, integration: Integration, email):
        """Who it is done as: the member they name, or whoever connected the endpoint."""
        if email:
            return teammate(integration.workspace, email) if isinstance(email, str) else None
        return teammate(integration.workspace, integration.connected_by.email) if integration.connected_by else None

    def handle(self, work: dict) -> None:
        integration = find_integration(self, work["endpoint"])
        if integration is None:
            return
        conversation = conversation_in(integration, work["conversation"])
        user = self.author(integration, work["author"])
        if conversation is None or user is None:
            return
        if work["action"] in WRITE:
            WRITE[work["action"]](integration, conversation, user, work["text"])
        else:
            CHANGE[work["action"]](integration, conversation, user)


def check_url(url: str) -> str:
    """The host, for people to recognize it by."""
    parts = urlsplit(url)
    # http only where the addresses are the server's own business anyway.
    allowed = {"https", "http"} if settings.OUTBOUND_ALLOW_PRIVATE_NETWORKS else {"https"}
    if parts.scheme not in allowed or not parts.hostname:
        raise PluginError("Enter an address that starts with https://.")
    if parts.username or parts.password:
        raise PluginError("Leave the password out of the address. Use the Authorization header.")
    return parts.hostname
