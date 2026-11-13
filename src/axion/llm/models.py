"""Request and response types shared by the LLM client and providers."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

LLMTier = Literal["small", "large"]


@dataclass(frozen=True)
class LLMRequest:
    """A logical LLM call before model and provider selection."""

    prompt: str
    stage: str
    tier: LLMTier = "small"
    model: str | None = None
    system: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    run_id: str | None = None
    paper_id: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderRequest:
    """The request handed to a concrete provider adapter."""

    prompt: str
    model: str
    system: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class ProviderResponse:
    """A successful provider completion, including token usage.

    ``model`` may differ from the requested model when a provider resolves an
    alias; the ledger records the model actually used.
    """

    text: str
    prompt_tokens: int
    completion_tokens: int
    model: str | None = None


@dataclass(frozen=True)
class LLMResult:
    """The outcome of one logical LLM call."""

    text: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    usd: Decimal | None
    latency_ms: float
    cache_hit: bool
    parsed: BaseModel | None = None

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
