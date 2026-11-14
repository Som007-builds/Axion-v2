"""Provider-adapter interface only.

No provider SDK is imported or declared here. A future adapter implements
:class:`ProviderAdapter` and registers itself in a
:class:`axion.llm.providers.ProviderRegistry`; the client remains the only
entry point for calls, retries, caching, and the ledger.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field

from axion.llm.models import ProviderRequest, ProviderResponse


class ProviderAdapterConfig(BaseModel):
    """Configuration shared by future HTTP adapters.

    The API key is referenced by environment-variable **name**, never stored
    in config files or logs.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    base_url: str | None = None
    api_key_env: str | None = None
    timeout_s: float = Field(default=60.0, gt=0)
    max_output_tokens: int | None = Field(default=None, gt=0)


class ProviderAdapter(ABC):
    """Transport boundary for one provider.

    Concrete adapters must translate SDK/HTTP failures into the taxonomy in
    :mod:`axion.llm.errors`; they must not write the ledger or cache directly.
    """

    name: str

    @abstractmethod
    def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Return text plus token usage for one completion."""
        raise NotImplementedError


__all__ = ["ProviderAdapter", "ProviderAdapterConfig"]
