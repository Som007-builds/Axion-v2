"""End-to-end offline tests for the LLM client."""

from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel

from axion.config.pricing import MissingPriceError, ModelPrice, PricingTable
from axion.config.settings import Settings
from axion.llm.cache import SQLiteCache
from axion.llm.client import LLMClient, RetryPolicy
from axion.llm.cooldown import CooldownTracker
from axion.llm.errors import (
    AllProvidersFailedError,
    ConfigurationError,
    PermanentProviderError,
    RateLimitError,
    StructuredOutputError,
    TransientProviderError,
)
from axion.llm.ledger import SQLiteLedger
from axion.llm.models import LLMRequest, ProviderResponse
from axion.llm.providers import ProviderRegistry, ScriptedProvider


class Claim(BaseModel):
    text: str


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "llm_small_model": "small/model",
        "llm_large_model": "large/model",
        "llm_provider_chain": ["primary", "secondary"],
        "llm_max_attempts": 3,
        "llm_retry_base_s": 0.0,
        "llm_retry_max_s": 0.0,
        "llm_retry_jitter_s": 0.0,
        "llm_cooldown_s": 60.0,
        "llm_cache_enabled": False,
        "dry_run": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _pricing(model: str = "small/model") -> PricingTable:
    return PricingTable(
        version=1,
        models={
            model: ModelPrice(
                provider="test",
                input_usd_per_mtok=Decimal("0.50"),
                output_usd_per_mtok=Decimal("1.50"),
            )
        },
    )


def _response(
    text: str = "ok",
    prompt_tokens: int = 100,
    completion_tokens: int = 50,
    model: str | None = None,
) -> ProviderResponse:
    return ProviderResponse(
        text=text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        model=model,
    )


def _request(**overrides: object) -> LLMRequest:
    values: dict[str, object] = {"prompt": "hello", "stage": "extract", "tier": "small"}
    values.update(overrides)
    return LLMRequest(**values)  # type: ignore[arg-type]


def _client(
    tmp_path: Path,
    settings: Settings,
    providers: list[ScriptedProvider],
    *,
    pricing: PricingTable | None = None,
    cache: SQLiteCache | None = None,
    cooldown: CooldownTracker | None = None,
    sleep: Callable[[float], None] | None = None,
    clock: Callable[[], float] | None = None,
) -> tuple[LLMClient, SQLiteLedger]:
    ledger = SQLiteLedger(tmp_path / "ledger.sqlite3")
    registry = ProviderRegistry()
    for provider in providers:
        registry.register(provider)
    retry = RetryPolicy(
        max_attempts=settings.llm_max_attempts,
        base_delay_s=settings.llm_retry_base_s,
        max_delay_s=settings.llm_retry_max_s,
        jitter_s=0.0,
        sleep=sleep or (lambda _delay: None),
    )
    client = LLMClient(
        settings,
        registry,
        ledger,
        pricing or _pricing(),
        cache=cache,
        cooldown=cooldown,
        retry=retry,
        clock=clock or (lambda: 0.0),
    )
    return client, ledger


def test_success_writes_ledger(tmp_path: Path) -> None:
    provider = ScriptedProvider(
        "primary", [_response(prompt_tokens=1_000_000, completion_tokens=1_000_000)]
    )
    client, ledger = _client(tmp_path, _settings(), [provider])

    result = client.complete(_request())

    assert result.text == "ok"
    assert result.provider == "primary"
    assert result.model == "small/model"
    assert result.usd == Decimal("2.000000")
    assert result.cache_hit is False
    report = ledger.report("stage")
    assert report.total_calls == 1
    assert report.total_usd == Decimal("2.000000")
    assert report.rows[0].key == "extract"


def test_large_tier_uses_large_model(tmp_path: Path) -> None:
    provider = ScriptedProvider("primary", [_response()])
    client, _ = _client(tmp_path, _settings(), [provider], pricing=_pricing("large/model"))

    result = client.complete(_request(tier="large"))

    assert result.model == "large/model"
    assert provider.calls[0].model == "large/model"


def test_explicit_model_override(tmp_path: Path) -> None:
    provider = ScriptedProvider("primary", [_response()])
    client, _ = _client(tmp_path, _settings(), [provider], pricing=_pricing("custom/model"))

    result = client.complete(_request(model="custom/model"))

    assert result.model == "custom/model"


def test_cache_hit_is_logged_at_zero_cost(tmp_path: Path) -> None:
    settings = _settings(llm_cache_enabled=True)
    cache = SQLiteCache(tmp_path / "ledger.sqlite3")
    provider = ScriptedProvider("primary", [_response(prompt_tokens=1_000_000)])
    client, ledger = _client(tmp_path, settings, [provider], cache=cache)

    first = client.complete(_request())
    second = client.complete(_request())

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.usd == Decimal("0")
    assert len(provider.calls) == 1
    report = ledger.report("stage")
    assert report.total_calls == 2
    assert report.total_cache_hits == 1
    assert report.total_usd == first.usd


def test_tier_and_parent_call_id_are_ledgered(tmp_path: Path) -> None:
    provider = ScriptedProvider("primary", [_response(), _response()])
    client, ledger = _client(tmp_path, _settings(), [provider])

    parent = client.complete(_request(stage="student"))
    assert parent.call_id is not None

    child = client.complete(_request(stage="large_llm", parent_call_id=parent.call_id))

    assert child.parent_call_id == parent.call_id
    report = ledger.report("tier")
    assert report.total_calls == 2
    assert report.total_escalated_calls == 1
    assert [row.key for row in report.rows] == ["small"]


def test_cache_hit_has_a_call_id(tmp_path: Path) -> None:
    settings = _settings(llm_cache_enabled=True)
    cache = SQLiteCache(tmp_path / "ledger.sqlite3")
    provider = ScriptedProvider("primary", [_response()])
    client, _ledger = _client(tmp_path, settings, [provider], cache=cache)

    first = client.complete(_request())
    second = client.complete(_request())

    assert first.call_id is not None
    assert second.call_id is not None
    assert second.call_id != first.call_id


def test_transient_retries_then_succeeds(tmp_path: Path) -> None:
    sleeps: list[float] = []
    provider = ScriptedProvider(
        "primary",
        [
            TransientProviderError("503 unavailable"),
            TransientProviderError("503 unavailable"),
            _response(),
        ],
    )
    settings = _settings(llm_max_attempts=3, llm_retry_base_s=1.0, llm_retry_max_s=10.0)
    client, ledger = _client(tmp_path, settings, [provider], sleep=sleeps.append)

    result = client.complete(_request())

    assert result.text == "ok"
    assert len(provider.calls) == 3
    assert sleeps == [1.0, 2.0]
    report = ledger.report("stage")
    assert report.total_calls == 3
    assert report.total_errors == 2


def test_rate_limit_exhaustion_cools_down_and_falls_back(tmp_path: Path) -> None:
    clock = lambda: 0.0  # noqa: E731
    cooldown = CooldownTracker(60.0, clock=clock)
    primary = ScriptedProvider("primary", [RateLimitError("429"), RateLimitError("429")])
    secondary = ScriptedProvider("secondary", [_response("fallback"), _response("fallback")])
    settings = _settings(llm_max_attempts=2)
    client, ledger = _client(
        tmp_path, settings, [primary, secondary], cooldown=cooldown, clock=clock
    )

    first = client.complete(_request())
    second = client.complete(_request())

    assert first.provider == "secondary"
    assert second.provider == "secondary"
    assert len(primary.calls) == 2
    assert len(secondary.calls) == 2
    report = ledger.report("provider")
    assert report.total_errors == 2


def test_permanent_error_skips_retries(tmp_path: Path) -> None:
    sleeps: list[float] = []
    primary = ScriptedProvider("primary", [PermanentProviderError("bad key")])
    secondary = ScriptedProvider("secondary", [_response("fallback")])
    client, _ = _client(tmp_path, _settings(), [primary, secondary], sleep=sleeps.append)

    result = client.complete(_request())

    assert result.provider == "secondary"
    assert len(primary.calls) == 1
    assert sleeps == []


def test_all_providers_fail_raises(tmp_path: Path) -> None:
    primary = ScriptedProvider("primary", [PermanentProviderError("bad key")])
    secondary = ScriptedProvider("secondary", [PermanentProviderError("bad key")])
    client, ledger = _client(tmp_path, _settings(), [primary, secondary])

    with pytest.raises(AllProvidersFailedError, match="all LLM providers failed"):
        client.complete(_request())

    assert ledger.report("stage").total_errors == 2


def test_cooldown_expiry_puts_provider_back(tmp_path: Path) -> None:
    now = [0.0]
    clock = lambda: now[0]  # noqa: E731
    cooldown = CooldownTracker(60.0, clock=clock)
    primary = ScriptedProvider(
        "primary", [PermanentProviderError("bad key"), _response("primary again")]
    )
    secondary = ScriptedProvider("secondary", [_response("fallback"), _response("fallback")])
    client, _ = _client(tmp_path, _settings(), [primary, secondary], cooldown=cooldown, clock=clock)

    first = client.complete(_request())
    now[0] = 61.0
    second = client.complete(_request())

    assert first.provider == "secondary"
    assert second.provider == "primary"
    assert len(primary.calls) == 2


def test_structured_output_validates(tmp_path: Path) -> None:
    provider = ScriptedProvider("primary", [_response('{"text": "a finding"}')])
    client, _ = _client(tmp_path, _settings(), [provider])

    result = client.complete(_request(), response_model=Claim)

    assert isinstance(result.parsed, Claim)
    assert result.parsed.text == "a finding"


def test_structured_output_failure_is_ledgered(tmp_path: Path) -> None:
    provider = ScriptedProvider("primary", [_response("not json")])
    client, ledger = _client(tmp_path, _settings(), [provider])

    with pytest.raises(StructuredOutputError):
        client.complete(_request(), response_model=Claim)

    report = ledger.report("stage")
    assert report.total_calls == 1
    assert report.total_errors == 1
    assert report.total_usd == Decimal("0.000125")


def test_dry_run_missing_price_fails_closed(tmp_path: Path) -> None:
    provider = ScriptedProvider("primary", [_response()])
    client, ledger = _client(
        tmp_path, _settings(dry_run=True), [provider], pricing=PricingTable(version=1)
    )

    with pytest.raises(MissingPriceError):
        client.complete(_request())

    assert provider.calls == []
    assert ledger.report("stage").total_errors == 1


def test_missing_price_warns_outside_dry_run(tmp_path: Path) -> None:
    provider = ScriptedProvider("primary", [_response()])
    client, ledger = _client(
        tmp_path, _settings(dry_run=False), [provider], pricing=PricingTable(version=1)
    )

    with pytest.warns(RuntimeWarning, match="cost not recorded"):
        result = client.complete(_request())

    assert result.usd is None
    report = ledger.report("stage")
    assert report.total_missing_price_calls == 1
    assert report.total_errors == 0


def test_missing_model_is_a_configuration_error(tmp_path: Path) -> None:
    provider = ScriptedProvider("primary", [_response()])
    client, ledger = _client(tmp_path, _settings(llm_small_model=None), [provider])

    with pytest.raises(ConfigurationError, match="no model configured"):
        client.complete(_request())

    assert provider.calls == []
    assert ledger.report("stage").total_errors == 1


def test_empty_provider_chain_is_a_configuration_error(tmp_path: Path) -> None:
    provider = ScriptedProvider("primary", [_response()])
    client, ledger = _client(tmp_path, _settings(llm_provider_chain=[]), [provider])

    with pytest.raises(ConfigurationError, match="LLM_PROVIDER_CHAIN is empty"):
        client.complete(_request())

    assert provider.calls == []
    assert ledger.report("stage").total_errors == 1


def test_empty_response_is_retried(tmp_path: Path) -> None:
    provider = ScriptedProvider("primary", [_response("   "), _response("ok")])
    settings = _settings(llm_max_attempts=2)
    sleeps: list[float] = []
    client, _ = _client(tmp_path, settings, [provider], sleep=sleeps.append)

    result = client.complete(_request())

    assert result.text == "ok"
    assert len(provider.calls) == 2
    assert len(sleeps) == 1


def test_unknown_provider_is_skipped(tmp_path: Path) -> None:
    provider = ScriptedProvider("primary", [_response("ok")])
    settings = _settings(llm_provider_chain=["missing", "primary"])
    client, ledger = _client(tmp_path, settings, [provider])

    result = client.complete(_request())

    assert result.provider == "primary"
    assert ledger.report("provider").total_errors == 1


def test_retry_delay_is_capped() -> None:
    policy = RetryPolicy(
        max_attempts=5,
        base_delay_s=4.0,
        max_delay_s=5.0,
        jitter_s=0.0,
        sleep=lambda _delay: None,
    )

    assert policy.delay(1) == 4.0
    assert policy.delay(2) == 5.0
    assert policy.delay(3) == 5.0
