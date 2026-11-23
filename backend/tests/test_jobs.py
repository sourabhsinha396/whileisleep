"""The job queue: how the AI stage is queued, locked per conversation, and run."""

from datetime import timedelta

import httpx
import pytest
from celery.exceptions import Retry
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.agent import openrouter, pipeline, tasks
from apps.agent.models import Turn
from apps.conversations.models import Message
from whileisleep.celery import app as celery_app
from whileisleep.settings import base

from .conftest import assistant, final, tool_call
from .factories import ConversationFactory, MessageFactory, OrganizationFactory, RuleFactory, WorkspaceFactory


def asking(body="Do you ship to Canada?"):
    workspace = WorkspaceFactory(organization=OrganizationFactory(ready=True))
    conversation = ConversationFactory(workspace=workspace)
    return conversation, MessageFactory(conversation=conversation, body=body)


@pytest.fixture
def queued(monkeypatch):
    """Records jobs instead of running them."""
    jobs = []
    monkeypatch.setattr(
        tasks.answer, "apply_async", lambda args=None, **options: jobs.append({"args": args, **options})
    )
    return jobs


# --- Queueing ---


@pytest.mark.django_db
def test_the_ai_stage_is_queued_with_the_debounce_delay(queued, settings):
    settings.REPLY_DEBOUNCE_SECONDS = 1.5
    conversation, message = asking()
    pipeline.handle(conversation, message)
    assert queued == [{"args": (conversation.pk, "", message.pk, None), "countdown": 1.5}]
    # Nothing answered yet: that is the worker's job.
    assert not Turn.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_the_job_is_queued_only_when_the_transaction_commits(queued):
    conversation, message = asking()
    with transaction.atomic():
        pipeline.handle(conversation, message)
        # A worker starting now wouldn't see the uncommitted message.
        assert queued == []
    assert len(queued) == 1


@pytest.mark.django_db(transaction=True)
def test_a_rolled_back_request_queues_nothing(queued):
    conversation, message = asking()
    with pytest.raises(RuntimeError), transaction.atomic():
        pipeline.handle(conversation, message)
        raise RuntimeError("the request failed")
    assert queued == []


@pytest.mark.django_db
def test_rule_replies_never_touch_the_queue(queued):
    conversation, message = asking("opening hours?")
    RuleFactory(workspace=conversation.workspace, keywords=["hours"], reply="9 to 5.")
    pipeline.handle(conversation, message)
    assert queued == [] and Turn.objects.get().stage == Turn.Stage.RULE


# --- The task ---


@pytest.mark.django_db
def test_the_task_answers_and_releases_the_lock(llm):
    conversation, message = asking()
    llm(final("Yes, we do."))
    tasks.answer.apply(args=(conversation.pk, "", message.pk, None)).get()
    assert conversation.messages.filter(sender=Message.Sender.BOT).get().body == "Yes, we do."
    assert cache.get(f"reply-lock:{conversation.pk}") is None


@pytest.mark.django_db
def test_a_second_job_for_the_conversation_waits_its_turn(llm):
    conversation, message = asking()
    fake = llm()
    with tasks.reply_lock(conversation.pk) as held:
        assert held
        # Another reply is in flight: this job asks to be run again shortly, and does nothing.
        with pytest.raises(Retry) as retry:
            tasks.answer.apply(args=(conversation.pk, "", message.pk, None)).get()
        assert retry.value.when == tasks.LOCK_RETRY_SECONDS
    assert fake.requests == [] and not Turn.objects.exists()
    # The first job's lock is still its own to release.
    assert cache.get(f"reply-lock:{conversation.pk}") is None


@pytest.mark.django_db
def test_other_conversations_are_not_held_up(llm):
    busy, _ = asking()
    conversation, message = asking()
    llm(final("Hello!"))
    with tasks.reply_lock(busy.pk):
        tasks.answer.apply(args=(conversation.pk, "", message.pk, None)).get()
    assert Turn.objects.get().conversation == conversation


def test_a_lock_is_released_even_when_the_reply_crashes():
    with pytest.raises(ValueError), tasks.reply_lock(7) as held:
        assert held
        raise ValueError("boom")
    assert cache.get("reply-lock:7") is None


def test_an_expired_lock_taken_by_someone_else_is_left_alone():
    with tasks.reply_lock(7):
        # Our lock expired and a newer job took the conversation.
        cache.set("reply-lock:7", "the-newer-jobs-token", 60)
    assert cache.get("reply-lock:7") == "the-newer-jobs-token"


def test_the_lock_expires_by_itself(settings):
    settings.REPLY_LOCK_SECONDS = 300
    seen = {}
    original = cache.add

    def spy(key, value, timeout=None):
        seen["timeout"] = timeout
        return original(key, value, timeout=timeout)

    cache.add = spy
    try:
        with tasks.reply_lock(7):
            pass
    finally:
        cache.add = original
    assert seen["timeout"] == 300


# --- Model failures that may pass ---


def transient(status=503):
    return openrouter.OpenRouterError("OpenRouter is overloaded.", status)


@pytest.fixture
def delays(monkeypatch):
    """Records how long each new try was asked to wait. (Jobs still run at once here.)"""
    asked = []
    real = tasks.answer.apply_async

    def recording(args=None, kwargs=None, countdown=None, **options):
        asked.append(countdown)
        return real(args=args, kwargs=kwargs, **options)

    monkeypatch.setattr(tasks.answer, "apply_async", recording)
    return asked


@pytest.mark.django_db
def test_a_provider_hiccup_is_retried_and_the_visitor_gets_a_real_answer(llm, delays):
    conversation, message = asking()
    fake = llm(transient(), final("Yes, we do."))

    tasks.answer.apply(args=(conversation.pk, "", message.pk, None)).get()

    assert len(fake.requests) == 2 and delays == [3]
    turn = Turn.objects.get()
    assert turn.stage == Turn.Stage.AI and turn.reply.body == "Yes, we do."
    # The failed try left nothing behind for the team or the visitor to see.
    assert not conversation.messages.filter(is_note=True).exists()
    assert conversation.messages.filter(sender=Message.Sender.BOT).count() == 1


@pytest.mark.django_db
def test_after_the_last_try_the_fallback_answers(llm, delays):
    conversation, message = asking()
    fake = llm(transient(429), transient(), transient(502))

    tasks.answer.apply(args=(conversation.pk, "", message.pk, None)).get()

    assert len(fake.requests) == 3 and delays == [3, 10]
    turn = Turn.objects.get()
    assert turn.stage == Turn.Stage.FALLBACK and "overloaded" in turn.error
    assert conversation.messages.filter(is_note=True, body__contains="overloaded").count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("status", [401, 402, 400, 404])
def test_failures_that_will_not_pass_are_not_retried(llm, delays, status):
    conversation, message = asking()
    fake = llm(openrouter.OpenRouterError("The OpenRouter API key was rejected.", status))
    tasks.answer.apply(args=(conversation.pk, "", message.pk, None)).get()
    assert len(fake.requests) == 1 and delays == []
    assert Turn.objects.get().stage == Turn.Stage.FALLBACK


@pytest.mark.django_db
def test_no_retry_once_a_tool_has_run(llm, delays):
    """Starting over would call the tool again, and a tool may have changed something."""
    conversation, message = asking()
    fake = llm(assistant(tool_call("handoff_to_human", {"reason": "wants a person"})), transient())

    tasks.answer.apply(args=(conversation.pk, "", message.pk, None)).get()

    assert len(fake.requests) == 2 and delays == []
    assert Turn.objects.get().stage == Turn.Stage.FALLBACK
    assert conversation.messages.filter(is_note=True, body__startswith="Visitor asked for a person").count() == 1


@pytest.mark.django_db
def test_the_lock_is_free_between_tries(llm, monkeypatch):
    conversation, message = asking()
    llm(transient(), final("Yes."))
    seen = []
    real = tasks.answer.apply_async

    def check_lock(args=None, kwargs=None, countdown=None, **options):
        seen.append(cache.get(f"reply-lock:{conversation.pk}"))
        return real(args=args, kwargs=kwargs, **options)

    monkeypatch.setattr(tasks.answer, "apply_async", check_lock)
    tasks.answer.apply(args=(conversation.pk, "", message.pk, None)).get()
    assert seen == [None]


def test_which_failures_count_as_passing():
    assert openrouter.OpenRouterError("x", 503).transient
    assert openrouter.OpenRouterError("x", 429).transient
    assert not openrouter.OpenRouterError("x", 401).transient
    assert not openrouter.OpenRouterError("x", 402).transient
    # No status: a malformed response, not worth repeating unless said so.
    assert not openrouter.OpenRouterError("x").transient
    assert openrouter.OpenRouterError("x", transient=True).transient


def test_a_network_failure_counts_as_passing(monkeypatch):
    def unreachable(*args, **kwargs):
        raise httpx.ConnectTimeout("slow")

    monkeypatch.setattr(openrouter.httpx, "request", unreachable)
    with pytest.raises(openrouter.OpenRouterError) as error:
        openrouter.complete("k", "m", [], [])
    assert error.value.transient


# --- The sweep for messages that slipped through ---


def aged(message, minutes):
    Message.objects.filter(pk=message.pk).update(created_at=timezone.now() - timedelta(minutes=minutes))
    return message


@pytest.mark.django_db
def test_the_sweep_answers_a_message_whose_job_was_lost(llm):
    conversation, message = asking()
    aged(message, 8)
    llm(final("Sorry for the wait. Yes, we do."))

    assert tasks.sweep_unanswered.apply().get() == 1

    turn = Turn.objects.get()
    assert turn.trigger == message and turn.reply.body == "Sorry for the wait. Yes, we do."
    # Answered now, so the next sweep leaves it alone.
    assert tasks.sweep_unanswered.apply().get() == 0


@pytest.mark.django_db
def test_the_sweep_runs_rules_too(llm):
    conversation, message = asking("opening hours?")
    aged(message, 8)
    RuleFactory(workspace=conversation.workspace, keywords=["hours"], reply="9 to 5.")
    fake = llm()
    tasks.sweep_unanswered.apply().get()
    assert Turn.objects.get().stage == Turn.Stage.RULE and fake.requests == []


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("minutes", "why"),
    [(1, "may still be in progress"), (45, "too late to be useful")],
)
def test_the_sweep_leaves_fresh_and_stale_messages(llm, minutes, why):
    _, message = asking()
    aged(message, minutes)
    fake = llm()
    assert tasks.sweep_unanswered.apply().get() == 0, why
    assert fake.requests == []


@pytest.mark.django_db
def test_the_sweep_skips_what_was_handled_or_is_not_the_ais(llm):
    fake = llm()
    # Already has a turn.
    conversation, answered = asking()
    aged(answered, 8)
    Turn.objects.create(workspace=conversation.workspace, conversation=conversation, trigger=answered, stage="ai")
    # A teammate replied after it.
    conversation, replied = asking()
    aged(replied, 8)
    MessageFactory(conversation=conversation, sender=Message.Sender.AGENT, body="On it!")
    # A person has the conversation.
    conversation, human = asking()
    aged(human, 8)
    conversation.human_requested = True
    conversation.save()
    # The AI is off for the workspace.
    conversation, off = asking()
    aged(off, 8)
    conversation.workspace.ai_enabled = False
    conversation.workspace.save()

    assert tasks.sweep_unanswered.apply().get() == 0
    assert fake.requests == []


@pytest.mark.django_db
def test_the_sweep_answers_only_the_newest_of_several_messages(llm):
    conversation, first = asking("hi")
    second = MessageFactory(conversation=conversation, body="do you ship to Canada?")
    aged(first, 9)
    aged(second, 8)
    llm(final("Yes."))
    assert tasks.sweep_unanswered.apply().get() == 1
    assert Turn.objects.get().trigger == second


@pytest.mark.django_db
def test_an_internal_note_after_a_message_does_not_count_as_an_answer(llm):
    conversation, message = asking()
    aged(message, 8)
    MessageFactory(conversation=conversation, sender=Message.Sender.SYSTEM, body="Rule matched: x", is_note=True)
    llm(final("Yes."))
    assert tasks.sweep_unanswered.apply().get() == 1


def test_the_sweep_waits_longer_than_any_reply_can_take(settings):
    """So it doesn't re-queue a message whose reply is still being written. The slowest
    reply: every retried try times out on its first model call, the waits between tries,
    then a last try that uses its whole deadline and overruns it by one model call."""
    one_call = openrouter.TIMEOUT_SECONDS
    retried = len(tasks.LLM_RETRY_DELAYS) * one_call + sum(tasks.LLM_RETRY_DELAYS)
    slowest = settings.REPLY_DEBOUNCE_SECONDS + retried + settings.REPLY_DEADLINE_SECONDS + one_call
    assert tasks.SWEEP_AFTER.total_seconds() > slowest
    assert tasks.SWEEP_AFTER < tasks.SWEEP_UNTIL


@pytest.mark.django_db
def test_a_job_that_arrives_twice_answers_once(llm):
    """The queue redelivers after a worker dies; the sweep re-queues what looks lost."""
    conversation, message = asking()
    fake = llm(final("Yes, we do."), final("Yes, we do. (again)"))
    arguments = (conversation.pk, "", message.pk, None)

    tasks.answer.apply(args=arguments).get()
    tasks.answer.apply(args=arguments).get()

    assert len(fake.requests) == 1 and Turn.objects.count() == 1
    assert conversation.messages.filter(sender=Message.Sender.BOT).count() == 1


def test_the_sweep_is_scheduled():
    schedule = celery_app.conf.beat_schedule["sweep-unanswered"]
    assert schedule["task"] == "apps.agent.tasks.sweep_unanswered" and schedule["schedule"] == 60.0
    assert schedule["task"] in celery_app.tasks


# --- Configuration ---


def test_jobs_are_acknowledged_late_and_one_at_a_time():
    """What makes a reply survive a worker dying: it leaves the queue only when done."""
    conf = celery_app.conf
    assert conf.task_acks_late and conf.task_reject_on_worker_lost
    assert conf.worker_prefetch_multiplier == 1
    assert conf.task_ignore_result


def test_a_reply_cannot_outlive_its_lock_or_be_redelivered_while_running(settings):
    assert settings.REPLY_DEADLINE_SECONDS < settings.REPLY_LOCK_SECONDS
    assert settings.REPLY_LOCK_SECONDS < settings.CELERY_BROKER_TRANSPORT_OPTIONS["visibility_timeout"]


def test_the_answer_task_is_registered():
    assert "apps.agent.tasks.answer" in celery_app.tasks


def test_the_queue_uses_a_different_redis_database_than_the_cache():
    assert base.redis_database("redis://redis:6379/0", 1) == "redis://redis:6379/1"
    assert base.redis_database("redis://:secret@cache.internal:6380", 1) == "redis://:secret@cache.internal:6380/1"
    assert base.redis_database("rediss://cache.example.com:6379/0?ssl_cert_reqs=required", 1) == (
        "rediss://cache.example.com:6379/1?ssl_cert_reqs=required"
    )
