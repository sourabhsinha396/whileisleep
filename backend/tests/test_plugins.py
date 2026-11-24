"""The plugin system (apps.integrations), with the plugin in example_plugin.py."""

import ast
import json
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from apps.conversations.models import Message
from apps.conversations.services import add_message
from apps.conversations.signals import announce
from apps.integrations import apps as integrations_app
from apps.integrations import deliveries, registry, tasks
from apps.integrations.models import Delivery, Integration, Thread
from apps.integrations.plugin import PluginError
from whileisleep.locks import cache_lock

from .conftest import Api
from .example_plugin import plugin
from .factories import AuthTokenFactory, ConversationFactory, MembershipFactory, VisitorFactory, WorkspaceFactory

pytestmark = pytest.mark.django_db

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def installed(settings):
    settings.PLUGINS = ["tests.example_plugin"]
    settings.PLUGIN_OPTIONS = {"PLUGIN_EXAMPLE_WORD": "sesame"}
    for log in (plugin.sent, plugin.errors, plugin.gone):
        log.clear()
    return settings


@pytest.fixture
def base(workspace):
    return f"/workspaces/{workspace.id}/integrations"


@pytest.fixture
def integration(workspace):
    return Integration.objects.create(
        workspace=workspace, plugin="example", account_id="acct_1", account_name="Acme", config={"room": "r1"}
    )


@pytest.fixture
def conversation(workspace):
    return ConversationFactory(workspace=workspace, visitor=VisitorFactory(workspace=workspace))


def say(conversation, body="Hi", sender=Message.Sender.VISITOR, **kwargs):
    return add_message(conversation, sender, body, **kwargs)


# --- Which plugins there are ---


@pytest.mark.parametrize("modules", [["no.such.module"], ["json"], ["tests.example_plugin"] * 2])
def test_a_plugin_that_cannot_load_stops_the_server(installed, modules):
    installed.PLUGINS = modules
    with pytest.raises(ImproperlyConfigured):
        registry.plugins()


def test_half_set_or_misspelled_options_are_reported(installed, monkeypatch):
    monkeypatch.setattr(type(plugin), "server_options", ("WORD", "OTHER"))
    installed.PLUGIN_OPTIONS = {"PLUGIN_EXAMPLE_WORD": "x", "PLUGIN_EXMAPLE_OTHER": "y"}
    messages = [w.msg for w in integrations_app.plugin_options(None)]
    assert any("PLUGIN_EXMAPLE_OTHER" in m for m in messages)
    assert any("Example is off until these are set: PLUGIN_EXAMPLE_OTHER" in m for m in messages)


def test_our_plugins_only_use_the_sdk():
    """So the rest of whileisleep can change without breaking plugins."""
    for path in (BACKEND / "plugins").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            names = [node.module or ""] if isinstance(node, ast.ImportFrom) and not node.level else []
            names += [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
            for name in names:
                ours = name.split(".")[0] in ("apps", "whileisleep")
                assert not ours or name == "apps.integrations.sdk", f"{path.name} imports {name}"


# --- Connecting and choosing ---


def test_the_list_says_what_there_is_and_what_is_connected(api, base, integration):
    (row,) = api.get(base).json()
    assert row["plugin"] == "example" and row["connected"] and row["account_name"] == "Acme"
    assert row["settings"] == {"room": "r1", "mode": "all", "prefix": ""} and row["ready"]
    assert row["icon"] == "<svg></svg>"


def test_connecting_with_typed_fields(api, base, workspace, membership):
    assert api.post(f"{base}/example/connect", {"values": {"key": "bad"}}).json()["detail"] == "That key doesn't work."
    assert api.post(f"{base}/example/connect", {"values": {}}).status_code == 400
    assert not Integration.objects.exists()
    assert api.post(f"{base}/example/connect", {"values": {"key": "good"}}).json() == {"url": ""}
    row = Integration.objects.get()
    assert (row.account_id, row.credentials, row.connected_by) == ("acct_1", {"key": "good"}, membership.user)


def test_credentials_are_encrypted_and_never_returned(api, base):
    api.post(f"{base}/example/connect", {"values": {"key": "good"}})
    raw = Integration.objects.extra(select={"raw": "credentials"}).values_list("raw", flat=True)[0]
    assert "good" not in raw
    assert "good" not in json.dumps(api.get(f"{base}/example").json())


def test_the_detail_offers_what_the_service_has(api, base, integration):
    fields = {f["name"]: f for f in api.get(f"{base}/example").json()["settings_fields"]}
    assert [o["label"] for o in fields["room"]["options"]] == ["Room one", "Room two"]
    assert [o["value"] for o in fields["mode"]["options"]] == ["all", "few"]


def test_a_service_that_is_down_still_shows_the_page(api, base, integration):
    plugin.errors.append(PluginError("Example is down."))
    body = api.get(f"{base}/example").json()
    assert body["options_error"] == "Example is down." and body["connected"]


@pytest.mark.parametrize(
    ("values", "problem"),
    [
        ({"room": "r9"}, "Room: pick one from the list."),
        ({"room": ""}, "Room: this is needed."),
        ({"room": "r1", "mode": "x"}, "Mode: pick one from the list."),
        ({"room": "r1", "prefix": "bad"}, "Not that prefix."),
    ],
)
def test_settings_are_checked(api, base, integration, values, problem):
    response = api.put(f"{base}/example", {"values": values})
    assert (response.status_code, response.json()["detail"]) == (400, problem)
    integration.refresh_from_db()
    assert integration.config == {"room": "r1"}


def test_saving_settings_keeps_only_known_ones(api, base, integration):
    body = api.put(f"{base}/example", {"values": {"room": "r2", "mode": "few", "evil": "1"}}).json()
    integration.refresh_from_db()
    assert integration.config == {"room": "r2", "mode": "few", "prefix": ""} == body["settings"]


def test_connecting_another_account_starts_over(api, base, integration, conversation):
    Thread.objects.create(integration=integration, conversation=conversation, external_id="t1")
    Integration.objects.update(account_id="acct_old")
    api.post(f"{base}/example/connect", {"values": {"key": "good"}})
    row = Integration.objects.get()
    assert row.account_id == "acct_1" and row.config == {} and not Thread.objects.exists()


def test_connecting_the_same_account_again_keeps_everything(api, base, integration, conversation):
    Thread.objects.create(integration=integration, conversation=conversation, external_id="t1")
    api.post(f"{base}/example/connect", {"values": {"key": "good"}})
    assert Integration.objects.get().config == {"room": "r1"} and Thread.objects.exists()


def test_disconnecting_works_even_if_the_service_fails(api, base, integration):
    plugin.errors.append(PluginError("down"))
    assert api.delete(f"{base}/example").status_code == 200
    assert plugin.gone == ["acct_1"] and not Integration.objects.exists()


def test_a_plugin_the_server_lacks_the_options_for(api, base, installed):
    installed.PLUGIN_OPTIONS = {}
    (row,) = api.get(base).json()
    assert row["available"] is False and row["missing_options"] == ["PLUGIN_EXAMPLE_WORD"]
    assert api.post(f"{base}/example/connect", {"values": {"key": "good"}}).status_code == 409


def test_members_look_owners_change_and_others_see_nothing(base, workspace, integration, api):
    member = Api(AuthTokenFactory(user=MembershipFactory(workspace=workspace, role="agent").user).key)
    stranger = Api(AuthTokenFactory(user=MembershipFactory().user).key)
    assert member.get(base).status_code == 200 and stranger.get(base).status_code == 404
    for someone in (member, stranger):
        assert someone.get(f"{base}/example").status_code == 404
        assert someone.put(f"{base}/example", {"values": {"room": "r2"}}).status_code == 404
        assert someone.delete(f"{base}/example").status_code == 404
        assert someone.post(f"{base}/example/connect", {"values": {"key": "good"}}).status_code == 404
    assert api.get(f"{base}/nothere").status_code == 404


# --- Events going out ---


def test_an_event_reaches_the_plugin_and_leaves_nothing_behind(integration, conversation):
    say(conversation, "Hello")
    assert plugin.sent == ["Hello"] and not Delivery.objects.exists()


def test_only_the_workspace_s_own_integrations_hear(integration):
    say(ConversationFactory(workspace=WorkspaceFactory()))
    assert plugin.sent == []


def test_an_event_that_came_through_an_integration_is_not_sent_back(integration, conversation):
    say(conversation, "From there", Message.Sender.AGENT, origin=integration.origin)
    assert plugin.sent == []


def test_a_plugin_that_does_not_want_an_event_gets_no_delivery(integration, conversation):
    Integration.objects.update(config={})
    say(conversation)
    assert plugin.sent == [] and not Delivery.objects.exists()


def test_a_plugin_s_bug_does_not_break_the_chat(integration, conversation):
    announce("message", conversation, data={"crash": True})
    assert not Delivery.objects.exists()


def test_no_queue_does_not_break_the_chat(integration, conversation, monkeypatch):
    def down(*args, **kwargs):
        raise ConnectionError("no redis")

    monkeypatch.setattr(tasks.deliver, "apply_async", down)
    say(conversation)
    assert Delivery.objects.get().status == "pending"


def test_a_busy_service_is_tried_again_and_order_is_kept(integration, conversation):
    plugin.errors.append(PluginError("busy", retry=True, after=90))
    say(conversation, "one")
    say(conversation, "two")
    first, second = Delivery.objects.all()
    assert plugin.sent == [] and first.attempts == 1 and second.attempts == 0
    assert timedelta(seconds=80) < first.due_at - timezone.now() <= timedelta(seconds=90)

    Delivery.objects.update(due_at=timezone.now())
    tasks.deliver(integration.pk, conversation.pk)
    assert plugin.sent == ["one", "two"] and not Delivery.objects.exists()


def test_a_service_cannot_make_us_wait_forever(integration, conversation):
    plugin.errors.append(PluginError("busy", retry=True, after=999999))
    say(conversation)
    assert Delivery.objects.get().due_at - timezone.now() <= timedelta(seconds=deliveries.RETRY_DELAYS[-1])


def test_giving_up_says_why_and_lets_the_next_through(integration, conversation):
    plugin.errors.append(PluginError("The room is gone."))
    say(conversation, "lost")
    integration.refresh_from_db()
    assert integration.last_error == "The room is gone." and Delivery.objects.get().status == "failed"
    say(conversation, "found")
    integration.refresh_from_db()
    assert plugin.sent == ["found"] and integration.last_error == ""


def test_a_crash_is_retried_and_then_given_up(integration, conversation):
    plugin.errors.extend(ValueError("bug") for _ in range(len(deliveries.RETRY_DELAYS) + 1))
    say(conversation)
    for _ in deliveries.RETRY_DELAYS:
        Delivery.objects.update(due_at=timezone.now())
        tasks.deliver(integration.pk, conversation.pk)
    delivery = Delivery.objects.get()
    assert delivery.status == "failed" and "bug" not in delivery.error


def test_one_job_at_a_time_per_conversation(integration, conversation):
    with cache_lock(f"deliver:{integration.pk}:{conversation.pk}", 60):
        say(conversation, "waits")
        assert plugin.sent == []
    tasks.deliver(integration.pk, conversation.pk)
    assert plugin.sent == ["waits"]


def test_the_sweep_sends_what_was_lost_and_forgets_old_failures(integration, conversation):
    long_ago = timezone.now() - timedelta(days=20)
    lost = Delivery.objects.create(
        integration=integration,
        conversation=conversation,
        event="message",
        message=Message.objects.create(conversation=conversation, sender="visitor", body="lost"),
        due_at=timezone.now() - timedelta(minutes=5),
    )
    old = Delivery.objects.create(integration=integration, conversation=conversation, event="message", status="failed")
    Delivery.objects.filter(pk=old.pk).update(created_at=long_ago)
    assert tasks.sweep_deliveries() == 1
    assert plugin.sent == ["lost"] and not Delivery.objects.filter(pk__in=[lost.pk, old.pk]).exists()


def test_deliveries_of_a_removed_plugin_are_dropped(integration, conversation, installed, monkeypatch):
    monkeypatch.setattr(deliveries, "send_later", lambda *args, **kwargs: None)
    say(conversation)
    installed.PLUGINS = []
    deliveries.send_pending(integration.pk, conversation.pk)
    assert not Delivery.objects.exists()
    say(conversation)
    assert not Delivery.objects.exists()


# --- Webhooks coming in ---


def post(client, data, word="sesame"):
    return client.client.post(
        "/api/v1/integrations/example/webhook",
        json.dumps(data),
        content_type="application/json",
        headers={"X-Word": word},
    )


@pytest.fixture
def linked(integration, conversation):
    return Thread.objects.create(integration=integration, conversation=conversation, external_id="t1")


def test_a_webhook_s_work_is_done_once(anon, linked, conversation, membership):
    data = {"id": "e1", "thread": "t1", "email": membership.user.email.upper(), "text": "Hi there"}
    assert post(anon, data).json() == {"got": "e1"}
    assert post(anon, data).status_code == 200
    (message,) = conversation.messages.all()
    assert (message.body, message.author, message.sender) == ("Hi there", membership.user, "agent")
    # And it isn't sent back to where it came from.
    assert plugin.sent == []


def test_a_webhook_that_is_not_genuine_is_refused(anon, linked, conversation):
    assert post(anon, {"id": "e1"}, word="guess").status_code == 401
    assert post(anon, {"id": "e1"}, word="").status_code == 401
    assert not conversation.messages.exists()


def test_webhooks_for_a_plugin_that_is_off_or_missing(anon, installed):
    assert anon.post("/integrations/nope/webhook").status_code == 404
    installed.PLUGIN_OPTIONS = {}
    assert post(anon, {"id": "e1"}, word="").status_code == 404


def test_a_webhook_s_work_is_tried_again(anon, linked, conversation, membership):
    plugin.errors.append(PluginError("down", retry=True))
    post(anon, {"id": "e1", "thread": "t1", "email": membership.user.email, "text": "Hi"})
    assert conversation.messages.count() == 1


def test_a_webhook_that_cannot_be_queued_is_not_forgotten(anon, linked, conversation, membership, monkeypatch):
    data = {"id": "e1", "thread": "t1", "email": membership.user.email, "text": "Hi"}

    def down(*args, **kwargs):
        raise ConnectionError("no redis")

    with monkeypatch.context() as patch:
        patch.setattr(tasks.handle, "delay", down)
        with pytest.raises(ConnectionError):
            post(anon, data)
    post(anon, data)
    assert conversation.messages.count() == 1
