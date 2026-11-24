from pathlib import Path

import pytest

from whileisleep.env import EnvError, validate_env_file

BACKEND = Path(__file__).resolve().parent.parent
REQUIRED = """DJANGO_SETTINGS_MODULE=whileisleep.settings.local
POSTGRES_DB=db
POSTGRES_USER=u
POSTGRES_PASSWORD=p
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5448
"""


def write(tmp_path, text: str) -> Path:
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    return path


def test_example_file_is_valid():
    """.env.example must stay in step with the validator."""
    validate_env_file(BACKEND / ".env.example")


def test_required_keys_are_enough(tmp_path):
    env = validate_env_file(write(tmp_path, REQUIRED))
    assert env.POSTGRES_PORT == 5448
    assert env.WEB_PORT == 8004


def test_unknown_key_is_rejected(tmp_path):
    with pytest.raises(EnvError, match="ANTHROPIC_API_KEY: not a known setting"):
        validate_env_file(write(tmp_path, REQUIRED + "ANTHROPIC_API_KEY=sk-ant\n"))


@pytest.mark.parametrize("key", ["POSTGRES_PASSWORD", "DJANGO_SETTINGS_MODULE"])
def test_missing_required_key(tmp_path, key):
    text = "\n".join(line for line in REQUIRED.splitlines() if not line.startswith(key))
    with pytest.raises(EnvError, match=f"{key}: required"):
        validate_env_file(write(tmp_path, text))


def test_empty_required_key_counts_as_missing(tmp_path):
    with pytest.raises(EnvError, match="POSTGRES_DB: required"):
        validate_env_file(write(tmp_path, REQUIRED.replace("POSTGRES_DB=db", "POSTGRES_DB=")))


def test_empty_optional_values_are_unset(tmp_path):
    env = validate_env_file(write(tmp_path, REQUIRED + "DEMO_EMAIL=\nOPENROUTER_API_KEY=  \n"))
    assert env.DEMO_EMAIL is None and env.OPENROUTER_API_KEY is None


def test_bad_values(tmp_path):
    with pytest.raises(EnvError) as error:
        validate_env_file(write(tmp_path, REQUIRED + "WEB_PORT=abc\nDEMO_EMAIL=not-an-email\n"))
    assert "WEB_PORT" in str(error.value) and "DEMO_EMAIL" in str(error.value)


def test_all_problems_listed_at_once(tmp_path):
    with pytest.raises(EnvError) as error:
        validate_env_file(write(tmp_path, "TYPO_KEY=1\n"))
    message = str(error.value)
    assert "TYPO_KEY" in message and "POSTGRES_DB: required" in message and "POSTGRES_PORT: required" in message


def test_payment_settings(tmp_path):
    good = "PAYMENT_PROVIDER=dodo\nDODO_BASE_URL=https://test.dodopayments.com\nDODO_PRODUCT_MONTHLY=pdt_1\n"
    assert validate_env_file(write(tmp_path, REQUIRED + good)).PAYMENT_PROVIDER == "dodo"
    # A provider we don't have, and two values swapped.
    bad = "PAYMENT_PROVIDER=stripe\nDODO_PRODUCT_YEARLY=whsec_1\nDODO_WEBHOOK_KEY=pdt_1\n"
    with pytest.raises(EnvError) as error:
        validate_env_file(write(tmp_path, REQUIRED + bad))
    assert all(key in str(error.value) for key in ("PAYMENT_PROVIDER", "DODO_PRODUCT_YEARLY", "DODO_WEBHOOK_KEY"))
