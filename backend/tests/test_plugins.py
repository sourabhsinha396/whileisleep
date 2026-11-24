"""The plugin system (apps.integrations), with the plugin in example_plugin.py."""

import ast
import json
import threading
from datetime import timedelta
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone

from apps.conversations.models import Message
from apps.conversations.services import add_message
from apps.conversations.signals import announce
from apps.integrations import apps as integrations_app
from apps.integrations import connections, deliveries, registry, tasks
from apps.integrations.models import Delivery, Integration, Thread
from apps.integrations.plugin import Connection, PluginError
from whileisleep.celery import app as celery_app
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


@pytest.fixture
def one(base, integration):
    return f"{base}/example/{integration.pk}"


def connect(api, base, key="good"):
    return api.job(api.post(f"{base}/example/connect", {"values": {"key": key}}))


def test_the_list_says_what_there_is_and_what_is_connected(api, base, integration):
    (row,) = api.get(base).json()
    (connection,) = row["connections"]
    assert row["plugin"] == "example" and connection["account_name"] == "Acme" and connection["ready"]
    assert connection["settings"] == {"room": "r1", "mode": "all", "prefix": "", "days": ""}
    assert row["icon"] == "<svg></svg>"


def test_connecting_with_typed_fields(api, base, membership):
    assert connect(api, base, "bad")["error"] == "That key doesn't work."
    assert api.post(f"{base}/example/connect", {"values": {}}).status_code == 400
    assert not Integration.objects.exists()
    assert connect(api, base)["done"]
    row = Integration.objects.get()
    assert (row.account_id, row.credentials, row.connected_by) == ("acct_1", {"key": "good"}, membership.user)


def test_credentials_are_encrypted_and_never_returned(api, base):
    connect(api, base)
    raw = Integration.objects.extra(select={"raw": "credentials"}).values_list("raw", flat=True)[0]
    assert "good" not in raw
    assert "good" not in json.dumps(api.get(f"{base}/example").json())


def test_the_detail_says_what_to_ask(api, base, integration):
    body = api.get(f"{base}/example").json()
    fields = {f["name"]: f for f in body["settings_fields"]}
    assert [o["value"] for o in fields["mode"]["options"]] == ["all", "few"]
    assert fields["password"]["kind"] == "secret" and body["connections"][0]["id"] == integration.pk


def test_what_the_service_offers_is_asked_in_a_job(api, one):
    options = api.job(api.post(f"{one}/options"))["result"]["options"]
    assert [o["label"] for o in options["room"]] == ["Room one", "Room two"]
    plugin.errors.append(PluginError("Example is down."))
    assert api.job(api.post(f"{one}/options"))["error"] == "Example is down."


@pytest.mark.parametrize(
    ("values", "problem"),
    [
        ({"room": "r9"}, "Room: pick from the list."),
        ({"room": ""}, "Room: this is needed."),
        ({"room": "r1", "mode": "x"}, "Mode: pick from the list."),
        ({"room": "r1", "days": "mon,sun"}, "Days: pick from the list."),
        ({"room": "r1", "prefix": "bad"}, "Not that prefix."),
    ],
)
def test_settings_are_checked(api, one, integration, values, problem):
    assert api.job(api.put(one, {"values": values}))["error"] == problem
    integration.refresh_from_db()
    assert integration.config == {"room": "r1"}


def test_saving_settings_keeps_only_known_ones(api, one, integration):
    values = {"room": "r2", "mode": "few", "days": "mon,tue", "evil": "1"}
    assert api.job(api.put(one, {"values": values}))["error"] == ""
    integration.refresh_from_db()
    assert integration.config == {"room": "r2", "mode": "few", "prefix": "", "days": "mon,tue"}


def test_a_secret_setting_is_kept_until_replaced_and_never_shown(api, base, one, integration):
    for typed, kept in (("hush", "hush"), ("", "hush"), ("other", "other")):
        api.job(api.put(one, {"values": {"room": "r1", "password": typed}}))
        integration.refresh_from_db()
        assert integration.credentials["password"] == kept and "password" not in integration.config
    body = api.get(f"{base}/example").json()
    assert body["connections"][0]["secrets"] == ["password"] and "other" not in json.dumps(body)


def test_connecting_another_account_starts_over(api, base, integration, conversation):
    Thread.objects.create(integration=integration, conversation=conversation, external_id="t1")
    Integration.objects.update(account_id="acct_old")
    connect(api, base)
    row = Integration.objects.get()
    assert row.account_id == "acct_1" and row.config == {} and not Thread.objects.exists()


def test_connecting_the_same_account_again_keeps_everything(api, base, integration, conversation):
    Thread.objects.create(integration=integration, conversation=conversation, external_id="t1")
    connect(api, base)
    assert Integration.objects.get().config == {"room": "r1"} and Thread.objects.exists()


def test_several_connections_where_the_plugin_allows_them(api, base, monkeypatch):
    monkeypatch.setattr(type(plugin), "many", True)
    ids = iter("abcdefgh")
    monkeypatch.setattr(type(plugin), "connect", lambda self, values: Connection(next(ids), "Acme", {}))
    for _ in range(connections.MAX_CONNECTIONS):
        assert connect(api, base)["done"]
    assert Integration.objects.count() == connections.MAX_CONNECTIONS
    refused = api.post(f"{base}/example/connect", {"values": {"key": "good"}})
    assert refused.status_code == 400 and "Remove one first" in refused.json()["detail"]


def test_disconnecting_works_even_if_the_service_fails(api, one):
    plugin.errors.append(PluginError("down"))
    assert api.delete(one).status_code == 200
    assert plugin.gone == ["acct_1"] and not Integration.objects.exists()


def test_a_plugin_the_server_lacks_the_options_for(api, base, installed):
    installed.PLUGIN_OPTIONS = {}
    (row,) = api.get(base).json()
    assert row["available"] is False and row["missing_options"] == ["PLUGIN_EXAMPLE_WORD"]
    assert api.post(f"{base}/example/connect", {"values": {"key": "good"}}).status_code == 409


def test_members_look_owners_change_and_others_see_nothing(base, one, workspace, api):
    member = Api(AuthTokenFactory(user=MembershipFactory(workspace=workspace, role="agent").user).key)
    stranger = Api(AuthTokenFactory(user=MembershipFactory().user).key)
    assert member.get(base).status_code == 200 and stranger.get(base).status_code == 404
    for someone in (member, stranger):
        assert someone.get(f"{base}/example").status_code == 404
        assert someone.put(one, {"values": {"room": "r2"}}).status_code == 404
        assert someone.post(f"{one}/options").status_code == 404
        assert someone.get(f"{one}/deliveries").status_code == 404
        assert someone.delete(one).status_code == 404
        assert someone.post(f"{base}/example/connect", {"values": {"key": "good"}}).status_code == 404
    assert api.get(f"{base}/nothere").status_code == 404


def test_a_connection_of_another_workspace_is_out_of_reach(api, base):
    theirs = Integration.objects.create(workspace=WorkspaceFactory(), plugin="example", account_id="x")
    for response in (api.put(f"{base}/example/{theirs.pk}", {"values": {}}), api.delete(f"{base}/example/{theirs.pk}")):
        assert response.status_code == 404
    assert Integration.objects.filter(pk=theirs.pk).exists()


# --- Jobs ---


def test_only_who_started_a_job_sees_how_it_went(api, base, workspace):
    job = api.post(f"{base}/example/connect", {"values": {"key": "good"}}).json()["job"]
    other = Api(AuthTokenFactory(user=MembershipFactory(workspace=workspace).user).key)
    assert other.get(f"/integrations/jobs/{job}").status_code == 404
    assert Api().get(f"/integrations/jobs/{job}").status_code == 401
    assert api.get("/integrations/jobs/nope").status_code == 404
    assert api.get(f"/integrations/jobs/{job}").json()["done"]


def test_a_job_that_crashes_says_so_without_details(api, base):
    plugin.errors.append(ValueError("inside"))
    Integration.objects.create(workspace_id=base.split("/")[2], plugin="example", account_id="acct_1")
    body = api.job(api.post(f"{base}/example/{Integration.objects.get().pk}/options"))
    assert body["done"] and "inside" not in body["error"]


def test_what_is_typed_is_not_readable_in_the_queue(api, base, monkeypatch):
    queued = []
    monkeypatch.setattr(tasks.run_job, "delay", lambda *args: queued.append(args))
    job = api.post(f"{base}/example/connect", {"values": {"key": "very-secret"}}).json()["job"]
    assert "very-secret" not in str(queued)
    assert api.get(f"/integrations/jobs/{job}").json()["done"] is False


# --- Slow services hold nobody up ---


def test_no_web_request_calls_the_service(api, anon, base, one, workspace, integration, conversation, monkeypatch):
    """With a queue, all of it happens in a worker."""
    queued = []
    for task in (tasks.deliver, tasks.handle, tasks.run_job, tasks.say_goodbye):
        monkeypatch.setattr(task, "apply_async", lambda *args, **kwargs: queued.append(args))
    for name in ("connect", "disconnect", "options", "check_settings", "deliver", "handle"):
        monkeypatch.setattr(type(plugin), name, lambda *args: pytest.fail("called the service"))
    anon.visitor_token = conversation.visitor.token
    responses = [
        anon.post(f"/widget/{workspace.public_key}/messages", {"body": "Hi"}),
        api.post(f"{base}/example/connect", {"values": {"key": "good"}}),
        api.get(f"{base}/example"),
        api.post(f"{one}/options"),
        api.put(one, {"values": {"room": "r1"}}),
        post(anon, {"id": "e1"}),
        api.delete(one),
    ]
    # Two deliveries: the visitor's message and the answer to it.
    assert [r.status_code for r in responses] == [200] * 7 and len(queued) == 7


def test_integrations_never_use_the_queue_of_ai_replies():
    """Else a slow service takes the threads that write them."""
    route = celery_app.amqp.router.route
    queues = {name: route({}, name)["queue"].name for name in celery_app.tasks if name.startswith("apps.integrations.")}
    assert queues.pop("apps.integrations.tasks.deliver") == "deliveries"
    assert set(queues.values()) == {"integrations"} and len(queues) == 4
    assert route({}, "apps.agent.tasks.answer")["queue"].name == "celery"
    compose = (BACKEND.parent / "deploy/docker-compose.yml").read_text(encoding="utf-8")
    dev = (BACKEND / "apps/agent/management/commands/devworker.py").read_text(encoding="utf-8")
    assert "-Q integrations,deliveries" in compose and "celery,integrations,deliveries" in dev


def test_a_job_without_room_gives_its_thread_back(integration, conversation, monkeypatch):
    """All delivering threads are busy: it neither waits nor gives up."""
    monkeypatch.setattr(tasks, "delivering", threading.BoundedSemaphore(1))
    tasks.delivering.acquire()
    say(conversation, "waits")
    assert plugin.sent == [] and Delivery.objects.get().attempts == 0
    tasks.delivering.release()
    tasks.deliver(integration.pk, conversation.pk)
    assert plugin.sent == ["waits"]
    # And the room was given back.
    assert tasks.delivering.acquire(blocking=False)


def test_one_integration_takes_only_a_few_threads(integration, conversation):
    with tasks.room(integration.pk) as first, tasks.room(integration.pk) as second:
        assert first and second
        with tasks.room(integration.pk) as third:
            assert not third
        with tasks.room(integration.pk + 1) as other:
            assert other
    with tasks.room(integration.pk) as again:
        assert again


def test_a_long_queue_takes_turns(integration, conversation, monkeypatch):
    monkeypatch.setattr(deliveries, "TURN_SECONDS", -1)
    monkeypatch.setattr(deliveries, "send_later", lambda *args, **kwargs: None)
    say(conversation, "one")
    say(conversation, "two")
    assert deliveries.send_pending(integration.pk, conversation.pk) == 0
    assert plugin.sent == ["one"]


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
    assert delivery.status == "failed" and "bug" not in delivery.detail


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


# --- The log ---


def test_what_was_sent_is_kept_if_the_plugin_keeps_a_log(api, one, integration, conversation, monkeypatch):
    monkeypatch.setattr(type(plugin), "keeps_log", True)
    say(conversation, "Hello")
    (row,) = api.get(f"{one}/deliveries").json()
    assert (row["status"], row["event"], row["conversation_id"]) == ("sent", "message", conversation.pk)
    again = api.post(f"{one}/deliveries/{row['id']}/again")
    assert again.json()["status"] == "sent" and plugin.sent == ["Hello", "Hello"]


def test_what_failed_can_be_sent_again(api, one, integration, conversation):
    plugin.errors.append(PluginError("The room is gone."))
    say(conversation, "Hello")
    (row,) = api.get(f"{one}/deliveries").json()
    assert (row["status"], row["detail"]) == ("failed", "The room is gone.")
    assert api.post(f"{one}/deliveries/{row['id']}/again").status_code == 200
    assert plugin.sent == ["Hello"]


def test_what_is_on_its_way_is_not_sent_twice(api, one, integration, conversation):
    plugin.errors.append(PluginError("busy", retry=True))
    say(conversation)
    assert api.post(f"{one}/deliveries/{Delivery.objects.get().pk}/again").status_code == 409


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
