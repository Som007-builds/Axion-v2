"""Provider protocol, registry, and an offline scripted provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from axion.llm.errors import ProviderNotConfiguredError
from axion.llm.models import ProviderRequest, ProviderResponse


class Provider(Protocol):
    """Transport boundary for one LLM provider.

    Adapters translate SDK-specific errors into the taxonomy in
    :mod:`axion.llm.errors`; the client handles retries and fallback.
    """

    name: str

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Run one completion and return text plus token usage."""
        ...


class ProviderRegistry:
    """Named provider instances available to the client."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> Provider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise ProviderNotConfiguredError(f"provider {name!r} is not registered") from exc

    def names(self) -> tuple[str, ...]:
        return tuple(self._providers)


@dataclass
class ScriptedProvider:
    """Provider with a fixed sequence of outcomes, for offline tests.

    Outcomes are consumed in order. An ``Exception`` outcome is raised.
    """

    name: str
    outcomes: list[ProviderResponse | Exception]
    calls: list[ProviderRequest] = field(default_factory=list)

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        self.calls.append(request)
        if not self.outcomes:
            raise RuntimeError(f"scripted provider {self.name!r} has no outcomes left")
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
