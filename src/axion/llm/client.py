"""Provider-agnostic LLM client with retries, cooldown, cache, and ledger."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Self, TypeVar

from pydantic import BaseModel

from axion.config.pricing import (
    MissingPriceError,
    PricingTable,
    estimate_cost,
    load_pricing,
)
from axion.config.settings import Settings
from axion.llm.cache import CachedResponse, SQLiteCache, make_cache_key
from axion.llm.cooldown import CooldownTracker
from axion.llm.errors import (
    AllProvidersFailedError,
    ConfigurationError,
    PermanentProviderError,
    ProviderNotConfiguredError,
    RateLimitError,
    StructuredOutputError,
    TransientProviderError,
    classify_error,
)
from axion.llm.ledger import LedgerEntry, SQLiteLedger
from axion.llm.models import LLMRequest, LLMResult, ProviderRequest, ProviderResponse
from axion.llm.providers import Provider, ProviderRegistry
from axion.llm.structured import parse_structured

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class RetryPolicy:
    """Retry schedule for one provider.

    ``max_attempts`` counts the first call plus retries. Jitter is symmetric
    around the exponential backoff and can be set to zero in tests.
    """

    max_attempts: int
    base_delay_s: float
    max_delay_s: float
    jitter_s: float = 0.0
    sleep: Callable[[float], None] = time.sleep
    random_source: Callable[[], float] = random.random

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")

    def delay(self, attempt: int) -> float:
        base: float = min(self.max_delay_s, self.base_delay_s * (2 ** (attempt - 1)))
        jitter: float = (self.random_source() * 2.0 - 1.0) * self.jitter_s
        return max(0.0, base + jitter)


class LLMClient:
    """Single entry point for every LLM call.

    The client resolves a tier to a configured model, checks the cache, walks
    the provider chain with retries and cooldowns, validates optional
    structured output, and writes every attempt to the cost ledger.
    """

    def __init__(
        self,
        settings: Settings,
        registry: ProviderRegistry,
        ledger: SQLiteLedger,
        pricing: PricingTable,
        *,
        cache: SQLiteCache | None = None,
        cooldown: CooldownTracker | None = None,
        retry: RetryPolicy | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> None:
        self._settings = settings
        self._registry = registry
        self._ledger = ledger
        self._pricing = pricing
        self._cache = cache
        self._clock = clock
        self._retry = retry or RetryPolicy(
            max_attempts=settings.llm_max_attempts,
            base_delay_s=settings.llm_retry_base_s,
            max_delay_s=settings.llm_retry_max_s,
            jitter_s=settings.llm_retry_jitter_s,
        )
        self._cooldown = cooldown or CooldownTracker(settings.llm_cooldown_s, clock=clock)

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        registry: ProviderRegistry,
        *,
        pricing: PricingTable | None = None,
        ledger: SQLiteLedger | None = None,
        cache: SQLiteCache | None = None,
        cooldown: CooldownTracker | None = None,
        retry: RetryPolicy | None = None,
        clock: Callable[[], float] = time.perf_counter,
    ) -> Self:
        """Wire a client from settings, creating the default ledger/cache."""
        ledger_path = settings.resolved_ledger_path
        ledger_obj = ledger or SQLiteLedger(ledger_path)
        cache_obj = cache
        if cache_obj is None and settings.llm_cache_enabled:
            cache_obj = SQLiteCache(ledger_path)
        pricing_obj = pricing or load_pricing(settings.resolved_pricing_path)
        return cls(
            settings,
            registry,
            ledger_obj,
            pricing_obj,
            cache=cache_obj,
            cooldown=cooldown,
            retry=retry,
            clock=clock,
        )

    def complete(
        self,
        request: LLMRequest,
        *,
        response_model: type[T] | None = None,
    ) -> LLMResult:
        """Run one logical LLM call and record it in the ledger."""
        try:
            model = self._resolve_model(request)
        except ConfigurationError as exc:
            self._record_error(
                request,
                provider=None,
                model=request.model,
                error=f"configuration: {exc}",
            )
            raise

        cache_key = make_cache_key(request, model)
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return self._complete_from_cache(request, cached, response_model)

        if self._settings.dry_run:
            try:
                self._pricing.require_priced(model)
            except MissingPriceError as exc:
                self._record_error(
                    request,
                    provider=None,
                    model=model,
                    error=f"pricing: {exc}",
                )
                raise

        chain = list(self._settings.llm_provider_chain)
        if not chain:
            chain_error = ConfigurationError("LLM_PROVIDER_CHAIN is empty")
            self._record_error(
                request,
                provider=None,
                model=model,
                error=f"configuration: {chain_error}",
            )
            raise chain_error

        active_chain = [name for name in chain if not self._cooldown.is_cooling(name)]
        if not active_chain:
            active_chain = chain

        last_error: Exception | None = None
        for provider_name in active_chain:
            try:
                provider = self._registry.get(provider_name)
            except ProviderNotConfiguredError as exc:
                self._record_error(
                    request,
                    provider=provider_name,
                    model=model,
                    error=f"provider: {exc}",
                )
                last_error = exc
                continue

            for attempt in range(1, self._retry.max_attempts + 1):
                started = self._clock()
                try:
                    response = self._call_provider(provider, request, model)
                except Exception as exc:
                    latency_ms = self._elapsed_ms(started)
                    classified = classify_error(exc)
                    self._record_error(
                        request,
                        provider=provider_name,
                        model=model,
                        error=f"{type(classified).__name__}: {classified}",
                        latency_ms=latency_ms,
                    )
                    last_error = exc
                    retryable = isinstance(classified, RateLimitError | TransientProviderError)
                    if retryable and attempt < self._retry.max_attempts:
                        self._retry.sleep(self._retry.delay(attempt))
                        continue
                    self._cooldown.mark_failed(provider_name)
                    break

                return self._complete_success(
                    request,
                    response,
                    provider_name=provider_name,
                    requested_model=model,
                    cache_key=cache_key,
                    latency_ms=self._elapsed_ms(started),
                    response_model=response_model,
                )

        raise AllProvidersFailedError(
            f"all LLM providers failed; chain={active_chain}"
        ) from last_error

    def _complete_success(
        self,
        request: LLMRequest,
        response: ProviderResponse,
        *,
        provider_name: str,
        requested_model: str,
        cache_key: str,
        latency_ms: float,
        response_model: type[T] | None,
    ) -> LLMResult:
        actual_model = response.model or requested_model
        usd = estimate_cost(
            self._pricing,
            actual_model,
            response.prompt_tokens,
            response.completion_tokens,
            dry_run=self._settings.dry_run,
        )

        parsed: BaseModel | None = None
        if response_model is not None:
            try:
                parsed = parse_structured(response.text, response_model)
            except StructuredOutputError as exc:
                self._record_error(
                    request,
                    provider=provider_name,
                    model=actual_model,
                    error=f"structured_output: {exc}",
                    prompt_tokens=response.prompt_tokens,
                    completion_tokens=response.completion_tokens,
                    usd=usd,
                    latency_ms=latency_ms,
                )
                raise

        call_id = self._ledger.record(
            LedgerEntry(
                stage=request.stage,
                tier=request.tier,
                provider=provider_name,
                model=actual_model,
                prompt_tokens=response.prompt_tokens,
                completion_tokens=response.completion_tokens,
                usd=usd,
                latency_ms=latency_ms,
                cache_hit=False,
                run_id=request.run_id,
                paper_id=request.paper_id,
                parent_call_id=request.parent_call_id,
            )
        )
        if self._cache is not None:
            self._cache.put(
                cache_key,
                provider=provider_name,
                model=actual_model,
                text=response.text,
            )
        return LLMResult(
            text=response.text,
            provider=provider_name,
            model=actual_model,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            usd=usd,
            latency_ms=latency_ms,
            cache_hit=False,
            parsed=parsed,
            call_id=call_id,
            parent_call_id=request.parent_call_id,
        )

    def _complete_from_cache(
        self,
        request: LLMRequest,
        cached: CachedResponse,
        response_model: type[T] | None,
    ) -> LLMResult:
        started = self._clock()
        parsed: BaseModel | None = None
        if response_model is not None:
            try:
                parsed = parse_structured(cached.text, response_model)
            except StructuredOutputError as exc:
                self._record_error(
                    request,
                    provider=cached.provider,
                    model=cached.model,
                    error=f"structured_output: {exc}",
                    prompt_tokens=0,
                    completion_tokens=0,
                    usd=Decimal("0"),
                    latency_ms=self._elapsed_ms(started),
                    cache_hit=True,
                )
                raise

        latency_ms = self._elapsed_ms(started)
        call_id = self._ledger.record(
            LedgerEntry(
                stage=request.stage,
                tier=request.tier,
                provider=cached.provider,
                model=cached.model,
                prompt_tokens=0,
                completion_tokens=0,
                usd=Decimal("0"),
                latency_ms=latency_ms,
                cache_hit=True,
                run_id=request.run_id,
                paper_id=request.paper_id,
                parent_call_id=request.parent_call_id,
            )
        )
        return LLMResult(
            text=cached.text,
            provider=cached.provider,
            model=cached.model,
            prompt_tokens=0,
            completion_tokens=0,
            usd=Decimal("0"),
            latency_ms=latency_ms,
            cache_hit=True,
            parsed=parsed,
            call_id=call_id,
            parent_call_id=request.parent_call_id,
        )

    def _call_provider(
        self,
        provider: Provider,
        request: LLMRequest,
        model: str,
    ) -> ProviderResponse:
        response = provider.complete(
            ProviderRequest(
                prompt=request.prompt,
                model=model,
                system=request.system,
                temperature=request.temperature,
                max_output_tokens=request.max_output_tokens,
            )
        )
        if not response.text.strip():
            raise TransientProviderError(f"[{provider.name}] returned an empty response")
        if response.prompt_tokens < 0 or response.completion_tokens < 0:
            raise PermanentProviderError(f"[{provider.name}] returned negative token usage")
        return response

    def _resolve_model(self, request: LLMRequest) -> str:
        if request.model:
            return request.model
        model = (
            self._settings.llm_small_model
            if request.tier == "small"
            else self._settings.llm_large_model
        )
        if not model:
            raise ConfigurationError(f"no model configured for tier {request.tier!r}")
        return model

    def _elapsed_ms(self, started: float) -> float:
        return (self._clock() - started) * 1000.0

    def _record_error(
        self,
        request: LLMRequest,
        *,
        provider: str | None,
        model: str | None,
        error: str,
        prompt_tokens: int | None = None,
        completion_tokens: int | None = None,
        usd: Decimal | None = None,
        latency_ms: float | None = None,
        cache_hit: bool = False,
    ) -> None:
        self._ledger.record(
            LedgerEntry(
                stage=request.stage,
                tier=request.tier,
                provider=provider,
                model=model,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                usd=usd,
                latency_ms=latency_ms,
                cache_hit=cache_hit,
                run_id=request.run_id,
                paper_id=request.paper_id,
                parent_call_id=request.parent_call_id,
                error=error[:500],
            )
        )
