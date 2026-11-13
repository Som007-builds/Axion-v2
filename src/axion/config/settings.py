"""Typed application settings loaded from the environment."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_PRICING_PATH = Path(__file__).with_name("pricing.yaml")


class Settings(BaseSettings):
    """Runtime configuration.

    Environment variable names are case-insensitive and match `.env.example`.
    Optional values accept an empty string and become ``None``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
        populate_by_name=True,
    )

    llm_provider_chain: Annotated[list[str], NoDecode] = Field(default_factory=list)
    groq_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None

    neo4j_uri: str | None = None
    neo4j_username: str | None = None
    neo4j_password: SecretStr | None = None

    crossref_contact_email: str | None = None
    europepmc_contact_email: str | None = None
    axion_api_key: SecretStr | None = None

    llm_small_model: str | None = None
    llm_large_model: str | None = None
    llm_max_attempts: int = Field(default=3, ge=1)
    llm_retry_base_s: float = Field(default=5.0, ge=0.0)
    llm_retry_max_s: float = Field(default=120.0, ge=0.0)
    llm_retry_jitter_s: float = Field(default=1.0, ge=0.0)
    llm_cooldown_s: float = Field(default=300.0, ge=0.0)
    llm_cache_enabled: bool = True

    dry_run: bool = Field(default=False, validation_alias="AXION_DRY_RUN")
    data_dir: Path | None = Field(default=None, validation_alias="AXION_DATA_DIR")
    pricing_path: Path | None = Field(default=None, validation_alias="AXION_PRICING_PATH")
    ledger_path: Path | None = Field(default=None, validation_alias="AXION_LEDGER_PATH")

    @field_validator("llm_provider_chain", mode="before")
    @classmethod
    def _split_provider_chain(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @field_validator(
        "groq_api_key",
        "gemini_api_key",
        "anthropic_api_key",
        "neo4j_password",
        "axion_api_key",
        mode="before",
    )
    @classmethod
    def _blank_secret_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator(
        "neo4j_uri",
        "neo4j_username",
        "crossref_contact_email",
        "europepmc_contact_email",
        "llm_small_model",
        "llm_large_model",
        "pricing_path",
        "ledger_path",
        mode="before",
    )
    @classmethod
    def _blank_string_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def resolved_pricing_path(self) -> Path:
        """Configured pricing file, or the packaged template when unset."""
        return self.pricing_path if self.pricing_path is not None else DEFAULT_PRICING_PATH

    @property
    def resolved_ledger_path(self) -> Path:
        """Configured ledger file, or ``<data_dir>/ledger.sqlite3``.

        There is deliberately no built-in fallback path: the owner must choose
        where local state lives via ``AXION_LEDGER_PATH`` or ``AXION_DATA_DIR``.
        """
        if self.ledger_path is not None:
            return self.ledger_path
        if self.data_dir is None:
            raise ValueError("set AXION_LEDGER_PATH or AXION_DATA_DIR before using the cost ledger")
        return self.data_dir / "ledger.sqlite3"
