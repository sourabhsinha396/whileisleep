"""What a plugin is. docs/plugins.md shows how to write one.

A plugin connects workspaces to one outside service. It says what it is and what it needs; the
dashboard draws its pages from that, so a plugin has no frontend code. It is told what happens
in conversations (`wants`, `deliver`) and may act on what the service sends (`receive`, `handle`).

One instance serves every workspace: keep nothing on `self`. What belongs to a workspace is in
its Integration.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from django.conf import settings


class PluginError(Exception):
    """Something at the other end went wrong. The message is safe to show the workspace's team.

    `retry` says it may work later (the service is down or busy), in `after` seconds if it said so.
    """

    def __init__(self, message: str, *, retry: bool = False, after: int | None = None):
        super().__init__(message)
        self.retry = retry
        self.after = after


class BadRequest(Exception):
    """A webhook that isn't genuine or makes no sense. Answered with this status."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


@dataclass(frozen=True)
class Option:
    value: str
    label: str


@dataclass(frozen=True)
class Field:
    """Something the owner fills in.

    - "text", "secret": typed
    - "choice": one of `options`, all shown
    - "select": one of what `Plugin.options` returns, in a dropdown
    """

    name: str
    label: str
    kind: str = "text"
    help: str = ""
    placeholder: str = ""
    options: tuple[Option, ...] = ()
    default: str = ""
    required: bool = True


@dataclass(frozen=True)
class Connection:
    """What connecting an account gave us."""

    account_id: str
    account_name: str
    credentials: dict = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class WebhookRequest:
    """`headers` finds names in any case."""

    headers: Mapping[str, str]
    body: bytes


@dataclass(frozen=True)
class Job:
    """Work for `handle`. `id` is the service's own id for it: the same one is done once."""

    id: str
    payload: dict


@dataclass(frozen=True)
class Received:
    """The answer to a webhook, sent at once, and the jobs it leaves for a worker."""

    jobs: tuple[Job, ...] = ()
    body: dict = field(default_factory=dict)


class Plugin:
    # Lowercase letters and digits. It is in URLs, the database and the server's settings.
    id = ""
    name = ""
    description = ""
    # Shown above the settings: what people should know before they use it.
    notice = ""
    # An SVG, as text.
    icon = ""
    # What whoever runs the server has to set, each as PLUGIN_<ID>_<NAME> in .env.
    server_options: tuple[str, ...] = ()
    # What an owner types to connect, for a service without a "Connect" page (`authorize_url`).
    connect_fields: tuple[Field, ...] = ()
    # What an owner chooses once it is connected.
    settings_fields: tuple[Field, ...] = ()

    # --- The server ---

    @classmethod
    def option_key(cls, name: str) -> str:
        return f"PLUGIN_{cls.id}_{name}".upper()

    def option(self, name: str) -> str:
        return settings.PLUGIN_OPTIONS.get(self.option_key(name), "")

    @property
    def missing_options(self) -> list[str]:
        return [self.option_key(name) for name in self.server_options if not self.option(name)]

    @property
    def available(self) -> bool:
        return not self.missing_options

    # --- Connecting ---

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        """The service's page where the owner allows the connection (OAuth). Empty: there is none,
        and they fill in `connect_fields`."""
        return ""

    def finish_authorization(self, code: str, redirect_uri: str) -> Connection:
        """They allowed it and came back with a code."""
        raise NotImplementedError

    def connect(self, values: dict) -> Connection:
        """They filled in `connect_fields`. Try them: what doesn't work shouldn't be saved."""
        raise NotImplementedError

    def disconnect(self, integration) -> None:
        """About to be removed. Nothing may depend on this working."""

    # --- Settings ---

    def options(self, integration, name: str) -> list[Option]:
        """What a "select" offers, asked from the service."""
        return []

    def check_settings(self, integration, values: dict) -> None:
        """The owner saved these. Raise PluginError to refuse them."""

    # --- From whileisleep to the service ---

    def wants(self, integration, event) -> bool:
        """Whether `deliver` should get this event (apps.conversations.signals.Event). Runs while
        someone waits: look at the database at most, never at the network."""
        return False

    def deliver(self, integration, event) -> None:
        """Tell the service, in a worker. A conversation's events come one at a time, in order.
        Raise PluginError when it didn't work."""

    # --- From the service to whileisleep ---

    def receive(self, request: WebhookRequest) -> Received:
        """POST /api/v1/integrations/<id>/webhook. Check that it is genuine, say what to do, and
        return within a second or two."""
        raise BadRequest("Not found.", 404)

    def handle(self, payload: dict) -> None:
        """Does a Job, in a worker. May run again after a PluginError with `retry`."""
