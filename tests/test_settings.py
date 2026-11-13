"""Tests for environment-backed settings."""

from __future__ import annotations

from pathlib import Path

import pytest

from axion.config.settings import DEFAULT_PRICING_PATH, Settings

ENV_VARS = (
    "LLM_PROVIDER_CHAIN",
    "GROQ_API_KEY",
    "GEMINI_API_KEY",
    "ANTHROPIC_API_KEY",
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "CROSSREF_CONTACT_EMAIL",
    "EUROPEPMC_CONTACT_EMAIL",
    "AXION_API_KEY",
    "LLM_SMALL_MODEL",
    "LLM_LARGE_MODEL",
    "LLM_MAX_ATTEMPTS",
    "LLM_RETRY_BASE_S",
    "LLM_RETRY_MAX_S",
    "LLM_RETRY_JITTER_S",
    "LLM_COOLDOWN_S",
    "LLM_CACHE_ENABLED",
    "AXION_DRY_RUN",
    "AXION_DATA_DIR",
    "AXION_PRICING_PATH",
    "AXION_LEDGER_PATH",
)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_empty_and_safe() -> None:
    settings = Settings(_env_file=None)

    assert settings.llm_provider_chain == []
    assert settings.groq_api_key is None
    assert settings.gemini_api_key is None
    assert settings.anthropic_api_key is None
    assert settings.neo4j_uri is None
    assert settings.neo4j_username is None
    assert settings.neo4j_password is None
    assert settings.crossref_contact_email is None
    assert settings.europepmc_contact_email is None
    assert settings.axion_api_key is None
    assert settings.llm_small_model is None
    assert settings.llm_large_model is None
    assert settings.llm_max_attempts == 3
    assert settings.llm_retry_base_s == 5.0
    assert settings.llm_retry_max_s == 120.0
    assert settings.llm_retry_jitter_s == 1.0
    assert settings.llm_cooldown_s == 300.0
    assert settings.llm_cache_enabled is True
    assert settings.dry_run is False
    assert settings.data_dir is None
    assert settings.pricing_path is None
    assert settings.ledger_path is None
    assert settings.resolved_pricing_path == DEFAULT_PRICING_PATH
    assert DEFAULT_PRICING_PATH.is_file()


def test_loads_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "groq, gemini")
    monkeypatch.setenv("GROQ_API_KEY", "s3cr3t-value")
    monkeypatch.setenv("NEO4J_URI", "bolt://example:7687")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "db-password")
    monkeypatch.setenv("CROSSREF_CONTACT_EMAIL", "owner@example.org")
    monkeypatch.setenv("LLM_SMALL_MODEL", "small/model")
    monkeypatch.setenv("LLM_LARGE_MODEL", "large/model")
    monkeypatch.setenv("LLM_MAX_ATTEMPTS", "4")
    monkeypatch.setenv("LLM_RETRY_BASE_S", "1.5")
    monkeypatch.setenv("LLM_RETRY_MAX_S", "30")
    monkeypatch.setenv("LLM_RETRY_JITTER_S", "0.5")
    monkeypatch.setenv("LLM_COOLDOWN_S", "60")
    monkeypatch.setenv("LLM_CACHE_ENABLED", "false")
    monkeypatch.setenv("AXION_DRY_RUN", "true")
    monkeypatch.setenv("AXION_DATA_DIR", "var/data")
    monkeypatch.setenv("AXION_PRICING_PATH", "config/custom-pricing.yaml")
    monkeypatch.setenv("AXION_LEDGER_PATH", "var/ledger.sqlite3")

    settings = Settings(_env_file=None)

    assert settings.llm_provider_chain == ["groq", "gemini"]
    assert settings.groq_api_key is not None
    assert settings.groq_api_key.get_secret_value() == "s3cr3t-value"
    assert settings.neo4j_uri == "bolt://example:7687"
    assert settings.neo4j_username == "neo4j"
    assert settings.neo4j_password is not None
    assert settings.neo4j_password.get_secret_value() == "db-password"
    assert settings.crossref_contact_email == "owner@example.org"
    assert settings.llm_small_model == "small/model"
    assert settings.llm_large_model == "large/model"
    assert settings.llm_max_attempts == 4
    assert settings.llm_retry_base_s == 1.5
    assert settings.llm_retry_max_s == 30.0
    assert settings.llm_retry_jitter_s == 0.5
    assert settings.llm_cooldown_s == 60.0
    assert settings.llm_cache_enabled is False
    assert settings.dry_run is True
    assert settings.data_dir == Path("var/data")
    assert settings.resolved_pricing_path == Path("config/custom-pricing.yaml")
    assert settings.resolved_ledger_path == Path("var/ledger.sqlite3")
    assert "s3cr3t-value" not in repr(settings)
    assert "db-password" not in repr(settings)


def test_provider_chain_splits_and_trims(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", " groq , , gemini ,")

    settings = Settings(_env_file=None)

    assert settings.llm_provider_chain == ["groq", "gemini"]


def test_blank_values_become_none(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        monkeypatch.setenv(name, "")

    settings = Settings(_env_file=None)

    assert settings.llm_provider_chain == []
    assert settings.groq_api_key is None
    assert settings.neo4j_uri is None
    assert settings.pricing_path is None
    assert settings.ledger_path is None
    assert settings.resolved_pricing_path == DEFAULT_PRICING_PATH
    with pytest.raises(ValueError, match="AXION_LEDGER_PATH"):
        _ = settings.resolved_ledger_path


def test_ledger_path_derives_from_data_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AXION_DATA_DIR", "var/data")

    settings = Settings(_env_file=None)

    assert settings.resolved_ledger_path == Path("var/data/ledger.sqlite3")


def test_dotenv_file_is_loaded(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=from-dotenv\nAXION_DRY_RUN=true\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.groq_api_key is not None
    assert settings.groq_api_key.get_secret_value() == "from-dotenv"
    assert settings.dry_run is True


def test_env_example_lists_every_setting() -> None:
    example = Path(__file__).resolve().parents[1] / ".env.example"
    text = example.read_text(encoding="utf-8")
    names = set()
    for field_name, field in Settings.model_fields.items():
        alias = field.validation_alias
        names.add(alias if isinstance(alias, str) else field_name.upper())

    missing = sorted(name for name in names if f"{name}=" not in text)
    assert missing == []
