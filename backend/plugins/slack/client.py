"""Calls to Slack's Web API (https://docs.slack.dev/apis/web-api)."""

import json
from urllib.parse import urlencode

from apps.integrations.sdk import PluginError, Unreachable, request

API = "https://slack.com/api/"
AUTHORIZE = "https://slack.com/oauth/v2/authorize"
# Enough channels to choose from; a Slack with more lists the first ones.
CHANNEL_PAGES = 5

# Slack's own trouble: worth trying again.
PASSING = {"ratelimited", "rate_limited", "internal_error", "fatal_error", "service_unavailable", "request_timeout"}
DISCONNECTED = {"invalid_auth", "not_authed", "account_inactive", "token_revoked", "token_expired"}
# The channel can't be used anymore, whatever we send.
CHANNEL_GONE = {"channel_not_found", "not_in_channel", "is_archived"}
MEANING = {
    **dict.fromkeys(DISCONNECTED, "Slack no longer accepts this connection. Connect it again."),
    "channel_not_found": "The channel is gone, or whileisleep isn't in it. Pick another, or invite whileisleep to it.",
    "not_in_channel": "whileisleep isn't in the channel. Invite it there, or pick another.",
    "is_archived": "The channel is archived. Pick another.",
    "missing_scope": "whileisleep needs more permissions in Slack. Connect it again.",
    "invalid_code": "That took too long. Connect again.",
    "code_already_used": "That link was used already. Connect again.",
}


class SlackError(PluginError):
    """`code` is Slack's own word for what went wrong; empty when it wasn't reached."""

    def __init__(self, code: str = "", message: str = "", **kwargs):
        self.code = code
        if not message and code.startswith("restricted_action"):
            message = "Slack doesn't let apps post in that channel. Pick another."
        super().__init__(message or MEANING.get(code) or f"Slack refused: {code}.", **kwargs)


def call(method: str, token: str = "", **params) -> dict:
    """Blocks and other structures go as JSON inside a form, which every method takes."""
    data = {
        name: value if isinstance(value, str) else json.dumps(value)
        for name, value in params.items()
        if value is not None
    }
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        response = request("POST", API + method, data=data, headers=headers)
    except Unreachable as error:
        raise SlackError(message="Slack isn't answering.", retry=True, after=error.after) from error
    if response.status_code == 429:
        after = response.headers.get("Retry-After", "")
        raise SlackError("ratelimited", "Slack is busy.", retry=True, after=int(after) if after.isdigit() else None)
    try:
        body = response.json()
    except ValueError:
        body = None
    if response.status_code >= 500 or not isinstance(body, dict):
        raise SlackError(message=f"Slack answered HTTP {response.status_code}.", retry=True)
    if not body.get("ok"):
        code = str(body.get("error", "unknown"))
        raise SlackError(code, retry=code in PASSING)
    return body


def authorize_url(client_id: str, scopes: tuple[str, ...], state: str, redirect_uri: str) -> str:
    query = {"client_id": client_id, "scope": ",".join(scopes), "state": state, "redirect_uri": redirect_uri}
    return f"{AUTHORIZE}?{urlencode(query)}"


def channels(token: str) -> list[dict]:
    """The channels that can be posted to: public ones, and private ones the app was invited to."""
    found, cursor = [], ""
    for _ in range(CHANNEL_PAGES):
        page = call(
            "conversations.list",
            token,
            types="public_channel,private_channel",
            exclude_archived=True,
            limit=200,
            cursor=cursor or None,
        )
        found += page.get("channels") or []
        cursor = (page.get("response_metadata") or {}).get("next_cursor") or ""
        if not cursor:
            break
    return sorted(found, key=lambda channel: channel["name"])


def join(token: str, channel: str) -> None:
    try:
        call("conversations.join", token, channel=channel)
    except SlackError as error:
        # A private channel: the app is in it, or it wouldn't have been listed.
        if error.code != "method_not_supported_for_channel_type":
            raise
