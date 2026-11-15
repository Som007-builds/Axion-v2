"""Tests for pricing parsing and fail-closed cost estimation."""

from __future__ import annotations

import textwrap
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from axion.config.pricing import (
    MissingPriceError,
    PricingError,
    estimate_cost,
    estimate_cost_details,
    load_pricing,
)
from axion.config.settings import DEFAULT_PRICING_PATH


def _write_pricing(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "pricing.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


COMPLETE_PRICING = """
version: 1
currency: USD
models:
  provider/model-a:
    provider: provider
    input_usd_per_mtok: "0.50"
    output_usd_per_mtok: "1.50"
"""

INCOMPLETE_PRICING = """
version: 1
currency: USD
models:
  provider/model-a:
    provider: provider
    input_usd_per_mtok:
    output_usd_per_mtok: "1.50"
"""


DATED_PRICING = """
version: 2
currency: USD
models:
  provider/model-b:
    provider: provider
    versions:
      - effective_from: "2026-01-01"
        effective_until: "2026-12-31"
        input_usd_per_mtok: "1.00"
        output_usd_per_mtok: "2.00"
      - effective_from: "2027-01-01"
        input_usd_per_mtok: "3.00"
        output_usd_per_mtok: "4.00"
"""


def test_packaged_pricing_has_verified_list_prices() -> None:
    pricing = load_pricing(DEFAULT_PRICING_PATH)

    assert pricing.version == 2
    assert pricing.currency == "USD"
    assert set(pricing.models) == {
        "openai/gpt-oss-120b",
        "openai/gpt-oss-20b",
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
    }
    large = pricing.require_priced("openai/gpt-oss-120b")
    assert large.input_usd_per_mtok == Decimal("0.15")
    assert large.output_usd_per_mtok == Decimal("0.60")
    assert large.cached_input_usd_per_mtok == Decimal("0.075")


def test_gemini_intro_and_post_promotion_prices_are_dated() -> None:
    pricing = load_pricing(DEFAULT_PRICING_PATH)
    intro = estimate_cost_details(
        pricing,
        "gemini-3.8-flash",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        dry_run=True,
        on_date=date(2026, 11, 15),
    )
    assert intro.usd == Decimal("4.500000")
    assert intro.input_usd == Decimal("0.750000")
    assert intro.output_usd == Decimal("3.750000")
    assert intro.price_version == "2026-11-15..2026-12-31"
    assert intro.post_promotion_usd == Decimal("9.000000")
    assert intro.post_promotion_version == "2027-01-01.."

    later = estimate_cost_details(
        pricing,
        "gemini-3.8-flash",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        dry_run=True,
        on_date=date(2027, 1, 1),
    )
    assert later.usd == Decimal("9.000000")
    assert later.price_version == "2027-01-01.."


def test_dated_price_fails_before_first_version(tmp_path: Path) -> None:
    pricing = load_pricing(_write_pricing(tmp_path, DATED_PRICING))

    with pytest.raises(MissingPriceError, match="no price version applies"):
        estimate_cost(
            pricing,
            "provider/model-b",
            prompt_tokens=1,
            completion_tokens=1,
            dry_run=True,
            on_date=date(2025, 12, 31),
        )


def test_cost_is_computed_from_per_million_prices(tmp_path: Path) -> None:
    pricing = load_pricing(_write_pricing(tmp_path, COMPLETE_PRICING))

    cost = estimate_cost(
        pricing,
        "provider/model-a",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        dry_run=True,
    )

    assert cost == Decimal("2.000000")


def test_small_token_counts_keep_six_decimals(tmp_path: Path) -> None:
    pricing = load_pricing(_write_pricing(tmp_path, COMPLETE_PRICING))

    cost = estimate_cost(
        pricing,
        "provider/model-a",
        prompt_tokens=1_000,
        completion_tokens=500,
        dry_run=True,
    )

    assert cost == Decimal("0.001250")


def test_missing_price_fails_closed_in_dry_run(tmp_path: Path) -> None:
    pricing = load_pricing(_write_pricing(tmp_path, INCOMPLETE_PRICING))

    with pytest.raises(MissingPriceError, match="incomplete"):
        estimate_cost(
            pricing,
            "provider/model-a",
            prompt_tokens=1,
            completion_tokens=1,
            dry_run=True,
        )


def test_unknown_model_fails_closed_in_dry_run(tmp_path: Path) -> None:
    pricing = load_pricing(_write_pricing(tmp_path, COMPLETE_PRICING))

    with pytest.raises(MissingPriceError, match="no price entry"):
        estimate_cost(
            pricing,
            "provider/unknown",
            prompt_tokens=1,
            completion_tokens=1,
            dry_run=True,
        )


def test_missing_price_warns_loudly_outside_dry_run(tmp_path: Path) -> None:
    pricing = load_pricing(_write_pricing(tmp_path, INCOMPLETE_PRICING))

    with pytest.warns(RuntimeWarning, match="cost not recorded"):
        cost = estimate_cost(
            pricing,
            "provider/model-a",
            prompt_tokens=1,
            completion_tokens=1,
            dry_run=False,
        )

    assert cost is None


def test_negative_price_is_rejected(tmp_path: Path) -> None:
    body = """
    version: 1
    currency: USD
    models:
      provider/model-a:
        provider: provider
        input_usd_per_mtok: "-0.01"
        output_usd_per_mtok: "1.50"
    """

    with pytest.raises(PricingError, match="greater than or equal to zero"):
        load_pricing(_write_pricing(tmp_path, body))


def test_unknown_field_is_rejected(tmp_path: Path) -> None:
    body = """
    version: 1
    currency: USD
    models:
      provider/model-a:
        provider: provider
        input_usd_per_mtok: "0.50"
        output_usd_per_mtok: "1.50"
        mystery: true
    """

    with pytest.raises(PricingError):
        load_pricing(_write_pricing(tmp_path, body))


def test_negative_token_count_is_rejected(tmp_path: Path) -> None:
    pricing = load_pricing(_write_pricing(tmp_path, COMPLETE_PRICING))

    with pytest.raises(ValueError, match="non-negative"):
        estimate_cost(
            pricing,
            "provider/model-a",
            prompt_tokens=-1,
            completion_tokens=1,
            dry_run=True,
        )
