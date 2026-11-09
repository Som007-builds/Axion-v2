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

    dry_run: bool = Field(default=False, validation_alias="AXION_DRY_RUN")
    data_dir: Path | None = Field(default=None, validation_alias="AXION_DATA_DIR")
    pricing_path: Path | None = Field(default=None, validation_alias="AXION_PRICING_PATH")

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
        "pricing_path",
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
