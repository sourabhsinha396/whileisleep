import pytest
from django.core.management import call_command
from django.db import connection

from apps.agent.models import Tool
from apps.workspaces.models import Organization
from whileisleep import encryption

from .factories import OrganizationFactory, ToolFactory


def raw(table: str, column: str, pk: int) -> str:
    """What the database really holds."""
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {column} FROM {table} WHERE id = %s", [pk])  # noqa: S608
        return cursor.fetchone()[0]


def test_round_trip():
    stored = encryption.encrypt("sk-or-secret")
    assert stored.startswith(encryption.PREFIX) and "sk-or-secret" not in stored
    assert encryption.decrypt(stored) == "sk-or-secret"


def test_empty_stays_empty():
    assert encryption.encrypt("") == ""
    assert encryption.decrypt("") == ""


def test_same_secret_encrypts_differently_each_time():
    assert encryption.encrypt("same") != encryption.encrypt("same")


def test_values_saved_before_encryption_still_read():
    assert encryption.decrypt("sk-or-plain-from-before") == "sk-or-plain-from-before"


def test_configured_key_is_used(settings):
    settings.ENCRYPTION_KEYS = [encryption.new_key()]
    stored = encryption.encrypt("secret")
    settings.ENCRYPTION_KEYS = []
    # The key derived from SECRET_KEY can't open it.
    assert encryption.decrypt(stored) == ""


def test_old_key_still_decrypts_after_rotation(settings):
    old, new = encryption.new_key(), encryption.new_key()
    settings.ENCRYPTION_KEYS = [old]
    stored = encryption.encrypt("secret")
    settings.ENCRYPTION_KEYS = [new, old]
    assert encryption.decrypt(stored) == "secret"
    # New writes use the new key: readable without the old one.
    restored = encryption.encrypt("secret")
    settings.ENCRYPTION_KEYS = [new]
    assert encryption.decrypt(restored) == "secret"
    assert encryption.decrypt(stored) == ""


def test_wrong_key_reads_as_empty_and_is_logged(settings, caplog):
    settings.ENCRYPTION_KEYS = [encryption.new_key()]
    stored = encryption.encrypt("secret")
    settings.ENCRYPTION_KEYS = [encryption.new_key()]
    assert encryption.decrypt(stored) == ""
    assert "could not be decrypted" in caplog.text


def test_generate_encryption_key_command_prints_a_usable_key(settings, capsys):
    call_command("generate_encryption_key")
    settings.ENCRYPTION_KEYS = [capsys.readouterr().out.strip()]
    assert encryption.decrypt(encryption.encrypt("secret")) == "secret"


# --- Model fields ---


@pytest.mark.django_db
def test_llm_key_is_ciphertext_in_the_database():
    organization = OrganizationFactory(openrouter_api_key="sk-or-live-1234")
    stored = raw("workspaces_organization", "openrouter_api_key", organization.pk)
    assert stored.startswith(encryption.PREFIX) and "sk-or-live" not in stored
    assert Organization.objects.get(pk=organization.pk).openrouter_api_key == "sk-or-live-1234"


@pytest.mark.django_db
def test_empty_llm_key_is_stored_empty():
    organization = OrganizationFactory()
    assert raw("workspaces_organization", "openrouter_api_key", organization.pk) == ""
    assert not Organization.objects.get(pk=organization.pk).llm_ready


@pytest.mark.django_db
def test_saving_again_does_not_encrypt_twice():
    organization = OrganizationFactory(openrouter_api_key="sk-or-live-1234")
    fresh = Organization.objects.get(pk=organization.pk)
    fresh.name = "Renamed"
    fresh.save()
    assert Organization.objects.get(pk=organization.pk).openrouter_api_key == "sk-or-live-1234"


@pytest.mark.django_db
def test_tool_headers_are_ciphertext_in_the_database():
    tool = ToolFactory(headers={"Authorization": "Bearer s3cret"})
    stored = raw("agent_tool", "headers", tool.pk)
    assert stored.startswith(encryption.PREFIX) and "s3cret" not in stored
    assert Tool.objects.get(pk=tool.pk).headers == {"Authorization": "Bearer s3cret"}


@pytest.mark.django_db
def test_tool_without_headers_reads_as_an_empty_dict():
    tool = ToolFactory()
    assert raw("agent_tool", "headers", tool.pk) == ""
    assert Tool.objects.get(pk=tool.pk).headers == {}


@pytest.mark.django_db
def test_headers_saved_as_plain_json_before_encryption_still_read():
    tool = ToolFactory()
    with connection.cursor() as cursor:
        cursor.execute("UPDATE agent_tool SET headers = %s WHERE id = %s", ['{"X-Api-Key": "old"}', tool.pk])
    assert Tool.objects.get(pk=tool.pk).headers == {"X-Api-Key": "old"}
