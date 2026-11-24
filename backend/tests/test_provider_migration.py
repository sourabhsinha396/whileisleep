"""Keys saved when OpenRouter was the only provider survive becoming one of several."""

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from whileisleep import encryption

BEFORE, AFTER = [("workspaces", "0008_storage_bucket")], [("workspaces", "0009_providers")]


def migrate(target):
    executor = MigrationExecutor(connection)
    executor.migrate(target)
    return MigrationExecutor(connection).loader.project_state(target).apps.get_model("workspaces", "Organization")


@pytest.fixture
def at_0008(transactional_db):
    """Organization as it was. Whatever the test does, the newest schema is back after it."""
    newest = MigrationExecutor(connection).loader.graph.leaf_nodes()
    yield migrate(BEFORE)
    with connection.cursor() as cursor:
        # Not through the models: they know tables of other apps that went with the rollback.
        cursor.execute(f"TRUNCATE {get_user_model()._meta.db_table} CASCADE")
    MigrationExecutor(connection).migrate(newest)


def test_the_openrouter_key_and_model_are_kept(at_0008):
    users = [get_user_model().objects.create(username=name, email=name) for name in ("a@x.com", "b@x.com")]
    with_key = at_0008.objects.create(
        name="A", owner_id=users[0].pk, openrouter_api_key="sk-or-old-1234", llm_model="x/y"
    )
    without = at_0008.objects.create(name="B", owner_id=users[1].pk)

    organization = migrate(AFTER)

    moved = organization.objects.get(pk=with_key.pk)
    assert moved.provider_keys == {"openrouter": "sk-or-old-1234"}
    assert (moved.llm_provider, moved.llm_model) == ("openrouter", "x/y")
    assert (moved.fallback_provider, moved.fallback_model) == ("", "")
    assert organization.objects.get(pk=without.pk).provider_keys == {}
    with connection.cursor() as cursor:
        cursor.execute("SELECT provider_keys FROM workspaces_organization WHERE id = %s", [with_key.pk])
        assert cursor.fetchone()[0].startswith(encryption.PREFIX)

    # And back again.
    assert migrate(BEFORE).objects.get(pk=with_key.pk).openrouter_api_key == "sk-or-old-1234"
