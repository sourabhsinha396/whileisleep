# Build a plugin

A plugin connects workspaces to one outside service: where a team works (Slack), or anything that should hear about chats
or answer them. It is one Python folder. It says what it needs, and the dashboard draws its pages from that, so there is
no frontend code to write.

Plugins are not for looking up customer data. Orders, accounts and invoices come from the agent's own tools (your APIs and
MCP servers), rules and playbooks, which work with any system.

## The smallest one

`backend/plugins/pager/__init__.py`:

```python
from apps.integrations.sdk import (
    PERSON_REQUESTED, Connection, Field, Plugin, PluginError, inbox_url, request,
)


class PagerPlugin(Plugin):
    id = "pager"
    name = "Pager"
    description = "Pages whoever is on call when a chat needs a person."
    icon = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'><circle cx='12' cy='12' r='10'/></svg>"
    connect_fields = (Field("key", "API key", kind="secret"),)
    settings_fields = (Field("level", "Level", default="high"),)

    def connect(self, values):
        answer = request("GET", "https://api.pager.example/me", headers={"Authorization": values["key"]})
        if answer.status_code != 200:
            raise PluginError("That key doesn't work.")
        me = answer.json()
        return Connection(account_id=me["id"], account_name=me["team"], credentials={"key": values["key"]})

    def wants(self, integration, event):
        return event.name == PERSON_REQUESTED

    def deliver(self, integration, event):
        answer = request(
            "POST",
            "https://api.pager.example/pages",
            headers={"Authorization": integration.credentials["key"], "Idempotency-Key": event.id},
            json={"text": event.data["reason"], "url": inbox_url(event.conversation), "level": integration.config["level"]},
        )
        if answer.status_code >= 400:
            raise PluginError(f"Pager answered HTTP {answer.status_code}.", retry=answer.status_code >= 500)


plugin = PagerPlugin()
```

Then list it: in `PLUGINS` in `backend/whileisleep/settings/base.py` to make it part of whileisleep, or, for a package of
your own, with `EXTRA_PLUGINS=pager_plugin` in `.env`.

`backend/plugins/slack` and `backend/plugins/webhooks` are complete examples, and `backend/apps/integrations/plugin.py`
describes every method.

## What a plugin can do

| | Methods |
|---|---|
| **Connect** by typed fields, or the service's own page (OAuth) | `connect`, or `authorize_url` and `finish_authorization` |
| **Let owners choose** text, secrets, one or several options, or a list from the service | `settings_fields`, `options`, `check_settings` |
| **Show owners** something to copy | `shown` |
| **Hear** what happens in chats | `wants`, `deliver` |
| **Act** on what the service sends to `/api/v1/integrations/<id>/webhook` | `receive`, `handle` |
| **Reply, write notes, resolve, reopen, give back to the AI**, as a teammate | `sdk.reply`, `add_note`, `resolve`, `reopen`, `give_to_ai` |
| **Remember** which chat a thread over there belongs to | `sdk.link_thread`, `thread_of`, `find_thread` |
| **Have several connections** in a workspace, or a log of what was sent | `many`, `keeps_log` |
| **Need something from whoever runs the server** | `server_options`: `PLUGIN_<ID>_<NAME>` in `.env` |

## Rules

1. **Import only from `apps.integrations.sdk`.** The rest of whileisleep may change; that won't. A test checks it.
2. **Never make anyone wait for the service.** `wants`, `receive`, `authorize_url` and `shown` run while a person waits:
   database at most. The rest run in a worker of their own, apart from the one that writes AI replies.
3. **Call the service with `sdk.request`.** It has a deadline for the whole call, and fails at once while the service is
   down. Pass `customer_address=True` for an address a customer typed: it refuses your private network. Write no `async`
   code around it: it blocks.
4. **Raise `PluginError`** with words an owner understands. `retry=True` if it may work later: after 10 seconds, then 1, 5,
   30 and 120 minutes. Anything else you raise is logged and tried again.
5. **Expect repeats.** A delivery may happen twice. Do first what can be done twice; use `event.id` if the service takes
   an idempotency key.
6. **Check that webhooks are genuine** in `receive`, with the signature, on the raw body, and refuse old ones. Give each
   `Job` the service's own id, and it is done once.
7. **Act only for teammates.** `sdk.teammate` finds the member with an email. Be sure the service vouches for that email.
8. **Keep nothing on `self`.** One instance serves every workspace, in many threads. What belongs to a workspace goes in
   its `integration.config`, or `integration.credentials` if it is secret (encrypted, never shown).
9. **Keep the visitor's words as words.** Escape them for the service: no mentions, no links in disguise.

## Test it

Real network calls fail in tests. Answer them with a stand-in for the service, as `backend/tests/fake_slack.py` does, and
cover at least: connecting with a key that doesn't work, a webhook that isn't genuine, the same webhook twice, someone who
isn't a teammate, and the service being down.
