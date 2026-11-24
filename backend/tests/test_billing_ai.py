"""The AI pauses when the trial is over and nobody pays."""

import pytest

from apps.agent import pipeline
from apps.agent.models import Turn
from apps.billing import services
from apps.conversations.models import Message

from .conftest import final
from .factories import ConversationFactory, MessageFactory, OrganizationFactory, RuleFactory
from .fake_dodo import end_trial, state

pytestmark = pytest.mark.django_db


def visitor_asks(workspace):
    conversation = ConversationFactory(workspace=workspace)
    message = MessageFactory(conversation=conversation, body="Do you ship to Canada?")
    pipeline.handle(conversation, message)
    conversation.refresh_from_db()
    return conversation


@pytest.fixture
def ready(account):
    # With a fallback model too: it mustn't answer either when the AI is paused.
    organization = account.organization
    organization.provider_keys = {"openrouter": "sk-or-test-key-1234", "anthropic": "sk-ant-test-key-5678"}
    organization.llm_model = "test/model"
    organization.fallback_provider, organization.fallback_model = "anthropic", "claude-test"
    organization.save()
    return account


def test_the_ai_answers_during_the_trial(ready, workspace, llm):
    llm(final("Yes, we do."))
    conversation = visitor_asks(workspace)
    assert conversation.messages.filter(sender=Message.Sender.BOT).get().body == "Yes, we do."


def test_after_the_trial_a_person_gets_the_chat(ready, workspace, llm):
    end_trial(ready)
    fake = llm(final("Yes, we do."))
    conversation = visitor_asks(workspace)
    assert fake.requests == [] and conversation.human_requested
    assert (
        conversation.messages.filter(sender=Message.Sender.BOT).get().body == "Thanks! A teammate will reply here soon."
    )
    assert Turn.objects.get().stage == Turn.Stage.GUARD
    note = conversation.messages.get(is_note=True)
    assert "paused" in note.body


def test_help_center_answers_pause_too(account, workspace):
    """Without an AI key the bot answers by search; that's the bot as well."""
    end_trial(account)
    assert visitor_asks(workspace).human_requested


def test_paying_brings_the_ai_back(ready, workspace, llm, billing):
    end_trial(ready)
    billing.subscribe(ready)
    services.sync("sub_1")
    llm(final("Yes, we do."))
    assert not visitor_asks(workspace).human_requested


def test_rules_still_run_when_the_ai_is_paused(account, workspace):
    end_trial(account)
    RuleFactory(workspace=workspace, keywords=["canada"], reply="We ship everywhere.")
    conversation = visitor_asks(workspace)
    assert conversation.messages.get(sender=Message.Sender.BOT).body == "We ship everywhere."


def test_paying_in_one_organization_does_not_help_another(account, billing):
    end_trial(account)
    billing.subscribe(account)
    services.sync("sub_1")
    other = services.account_for(OrganizationFactory())
    end_trial(other)
    assert (state(account), state(other)) == ("active", "paused")


def test_the_workspace_says_where_it_stands(api, account, workspace):
    assert api.get("/workspaces").json()[0]["trial_days_left"] == 14
    end_trial(account)
    row = api.get("/workspaces").json()[0]
    assert (row["billing_state"], row["trial_days_left"]) == ("paused", None)
