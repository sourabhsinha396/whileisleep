"""A stand-in for Slack's Web API: what it holds, and every call made to it."""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs, urlencode

import httpx
from django.test import Client

TEAM = "T1"
SECRET = "signing-secret"
WEBHOOK = "/api/v1/integrations/slack/webhook"


class FakeSlack:
    def __init__(self):
        self.calls: list[tuple[str, dict, str]] = []
        self.channels = [
            {"id": "C2", "name": "support", "is_private": False},
            {"id": "C1", "name": "general", "is_private": False},
            {"id": "G1", "name": "vip", "is_private": True},
        ]
        self.users: dict[str, dict] = {}
        # Method → the errors to answer with next: a word of Slack's, or a whole response.
        self.errors: dict[str, list] = {}
        self.count = 0

    def person(self, id: str, email: str, **fields) -> None:
        self.users[id] = {"id": id, "team_id": TEAM, "profile": {"email": email}} | fields

    def sent(self, method: str) -> list[dict]:
        return [params for called, params, _ in self.calls if called == method]

    @property
    def methods(self) -> list[str]:
        return [method for method, _, _ in self.calls]

    def handle(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://slack.com/api/"), request.url
        method = request.url.path.removeprefix("/api/")
        params = {key: values[0] for key, values in parse_qs(request.content.decode()).items()}
        self.calls.append((method, params, request.headers.get("Authorization", "").removeprefix("Bearer ")))
        if self.errors.get(method):
            error = self.errors[method].pop(0)
            if isinstance(error, Exception):
                raise error
            if isinstance(error, httpx.Response):
                return error
            return httpx.Response(200, json={"ok": False, "error": error})
        return httpx.Response(200, json={"ok": True, **self.answer(method, params)})

    def answer(self, method: str, params: dict) -> dict:
        if method == "oauth.v2.access":
            return {"access_token": "xoxb-1", "token_type": "bot", "team": {"id": TEAM, "name": "Acme HQ"}}
        if method == "conversations.list":
            return {"channels": self.channels}
        if method == "chat.postMessage":
            self.count += 1
            return {"ts": f"100.{self.count}"}
        if method == "users.info":
            return {"user": self.users[params["user"]]}
        if method == "users.lookupByEmail":
            return {"user": next(u for u in self.users.values() if u["profile"]["email"] == params["email"])}
        assert method in {
            "conversations.join",
            "chat.update",
            "chat.postEphemeral",
            "reactions.add",
            "auth.revoke",
            "auth.test",
        }, f"Unexpected call: {method}"
        return {}


def signed(body: bytes, at: float | None = None, secret: str = SECRET) -> dict:
    timestamp = str(int(time.time() if at is None else at))
    digest = hmac.new(secret.encode(), f"v0:{timestamp}:".encode() + body, hashlib.sha256).hexdigest()
    return {"X-Slack-Signature": f"v0={digest}", "X-Slack-Request-Timestamp": timestamp}


def post_event(event: dict, id: str = "Ev1", team: str = TEAM, **kwargs):
    body = json.dumps({"type": "event_callback", "team_id": team, "event_id": id, "event": event}).encode()
    return post(body, "application/json", **kwargs)


def post_action(payload: dict):
    body = urlencode({"payload": json.dumps(payload)}).encode()
    return post(body, "application/x-www-form-urlencoded")


def post(body: bytes, content_type: str, headers: dict | None = None):
    return Client().post(WEBHOOK, body, content_type=content_type, headers=headers or signed(body))
