"""Tests for pricing parsing and fail-closed cost estimation."""

from __future__ import annotations

import textwrap
from decimal import Decimal
from pathlib import Path

import pytest

from axion.config.pricing import (
    MissingPriceError,
    PricingError,
    estimate_cost,
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


def test_packaged_template_loads_with_blank_prices() -> None:
    pricing = load_pricing(DEFAULT_PRICING_PATH)

    assert pricing.version == 1
    assert pricing.currency == "USD"
    assert pricing.models == {}


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
