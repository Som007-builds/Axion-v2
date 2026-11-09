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
    "AXION_DRY_RUN",
    "AXION_DATA_DIR",
    "AXION_PRICING_PATH",
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
    assert settings.dry_run is False
    assert settings.data_dir is None
    assert settings.pricing_path is None
    assert settings.resolved_pricing_path == DEFAULT_PRICING_PATH
    assert DEFAULT_PRICING_PATH.is_file()


def test_loads_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "groq, gemini")
    monkeypatch.setenv("GROQ_API_KEY", "s3cr3t-value")
    monkeypatch.setenv("NEO4J_URI", "bolt://example:7687")
    monkeypatch.setenv("NEO4J_USERNAME", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "db-password")
    monkeypatch.setenv("CROSSREF_CONTACT_EMAIL", "owner@example.org")
    monkeypatch.setenv("AXION_DRY_RUN", "true")
    monkeypatch.setenv("AXION_DATA_DIR", "var/data")
    monkeypatch.setenv("AXION_PRICING_PATH", "config/custom-pricing.yaml")

    settings = Settings(_env_file=None)

    assert settings.llm_provider_chain == ["groq", "gemini"]
    assert settings.groq_api_key is not None
    assert settings.groq_api_key.get_secret_value() == "s3cr3t-value"
    assert settings.neo4j_uri == "bolt://example:7687"
    assert settings.neo4j_username == "neo4j"
    assert settings.neo4j_password is not None
    assert settings.neo4j_password.get_secret_value() == "db-password"
    assert settings.crossref_contact_email == "owner@example.org"
    assert settings.dry_run is True
    assert settings.data_dir == Path("var/data")
    assert settings.resolved_pricing_path == Path("config/custom-pricing.yaml")
    assert "s3cr3t-value" not in repr(settings)
    assert "db-password" not in repr(settings)


def test_provider_chain_splits_and_trims(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", " groq , , gemini ,")

    settings = Settings(_env_file=None)

    assert settings.llm_provider_chain == ["groq", "gemini"]


def test_blank_values_become_none(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VARS:
        if name != "LLM_PROVIDER_CHAIN":
            monkeypatch.setenv(name, "")
    monkeypatch.setenv("LLM_PROVIDER_CHAIN", "")

    settings = Settings(_env_file=None)

    assert settings.llm_provider_chain == []
    assert settings.groq_api_key is None
    assert settings.neo4j_uri is None
    assert settings.pricing_path is None
    assert settings.resolved_pricing_path == DEFAULT_PRICING_PATH


def test_dotenv_file_is_loaded(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("GROQ_API_KEY=from-dotenv\nAXION_DRY_RUN=true\n", encoding="utf-8")

    settings = Settings(_env_file=env_file)

    assert settings.groq_api_key is not None
    assert settings.groq_api_key.get_secret_value() == "from-dotenv"
    assert settings.dry_run is True
