"""A small plugin for tests: connects with a typed key, sends messages to a list, and answers
webhooks signed with a shared word. docs/plugins.md is close to this."""

import json

from apps.integrations.sdk import (
    MESSAGE,
    BadRequest,
    Connection,
    Field,
    Job,
    Option,
    Plugin,
    PluginError,
    Received,
    find_thread,
    link_thread,
    reply,
    teammate,
    thread_of,
)


class ExamplePlugin(Plugin):
    id = "example"
    name = "Example"
    description = "Copies messages to a room."
    icon = "<svg></svg>"
    server_options = ("WORD",)
    connect_fields = (Field("key", "API key", kind="secret"),)
    settings_fields = (
        Field("room", "Room", kind="select"),
        Field("mode", "Mode", kind="choice", options=(Option("all", "All"), Option("few", "Few")), default="all"),
        Field("prefix", "Prefix", required=False),
    )

    # The service: what arrived there, and the errors to fail with next.
    sent: list = []
    errors: list = []
    gone: list = []

    def connect(self, values):
        if values["key"] != "good":
            raise PluginError("That key doesn't work.")
        return Connection("acct_1", "Acme", {"key": values["key"]})

    def disconnect(self, integration):
        self.gone.append(integration.account_id)
        if self.errors:
            raise self.errors.pop(0)

    def options(self, integration, name):
        if self.errors:
            raise self.errors.pop(0)
        return [Option("r1", "Room one"), Option("r2", "Room two")]

    def check_settings(self, integration, values):
        if values["prefix"] == "bad":
            raise PluginError("Not that prefix.")

    def wants(self, integration, event):
        if event.data.get("crash"):
            raise ValueError("a bug")
        return bool(integration.config.get("room")) and event.name == MESSAGE

    def deliver(self, integration, event):
        if self.errors:
            raise self.errors.pop(0)
        if thread_of(integration, event.conversation) is None:
            link_thread(integration, event.conversation, f"t{event.conversation.pk}")
        self.sent.append(event.message.body)

    def receive(self, request):
        if request.headers.get("X-Word") != self.option("WORD"):
            raise BadRequest("Wrong word.", 401)
        data = json.loads(request.body)
        return Received(jobs=(Job(data["id"], data),), body={"got": data["id"]})

    def handle(self, payload):
        if self.errors:
            raise self.errors.pop(0)
        thread = find_thread(self, "acct_1", payload["thread"])
        user = teammate(thread.conversation.workspace, payload["email"])
        reply(thread.integration, thread.conversation, user, payload["text"])


plugin = ExamplePlugin()
