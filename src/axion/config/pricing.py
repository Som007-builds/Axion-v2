"""Pricing table parsing and fail-closed cost estimation.

Prices are list prices in USD per million tokens. A model may have a single
flat price (legacy entries) or dated price versions. Dated versions are chosen
by the call date, so a promotional price that ends mid-run is recorded with the
version that actually applied. The ledger always records list-price cost, even
when the provider tier is free.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

_USD_QUANTUM = Decimal("0.000001")
_TOKEN_DIVISOR = Decimal(1_000_000)


class PricingError(Exception):
    """Raised when the pricing file cannot be loaded or validated."""


class MissingPriceError(PricingError):
    """Raised when a model has no complete price entry for the requested date."""


class PriceVersion(BaseModel):
    """One dated list-price version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    effective_from: date
    effective_until: date | None = None
    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    cached_input_usd_per_mtok: Decimal | None = None
    note: str | None = None

    @field_validator(
        "input_usd_per_mtok",
        "output_usd_per_mtok",
        "cached_input_usd_per_mtok",
    )
    @classmethod
    def _non_negative(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value < 0:
            raise ValueError("price must be greater than or equal to zero")
        return value

    @model_validator(mode="after")
    def _valid_window(self) -> PriceVersion:
        if self.effective_until is not None and self.effective_until < self.effective_from:
            raise ValueError("effective_until must not precede effective_from")
        return self

    def applies_on(self, day: date) -> bool:
        return self.effective_from <= day and (
            self.effective_until is None or day <= self.effective_until
        )

    @property
    def label(self) -> str:
        if self.effective_until is None:
            return f"{self.effective_from.isoformat()}.."
        return f"{self.effective_from.isoformat()}..{self.effective_until.isoformat()}"


@dataclass(frozen=True)
class PriceSelection:
    """The concrete prices and version label selected for one call date."""

    input_usd_per_mtok: Decimal
    output_usd_per_mtok: Decimal
    cached_input_usd_per_mtok: Decimal | None
    price_version: str


@dataclass(frozen=True)
class CostEstimate:
    """Call-date list-price cost plus the post-promotion comparison."""

    usd: Decimal | None
    post_promotion_usd: Decimal | None
    input_usd: Decimal | None
    output_usd: Decimal | None
    price_version: str | None
    post_promotion_version: str | None


class ModelPrice(BaseModel):
    """Prices for one model, either flat or as dated versions.

    Blank flat prices are valid and mean "not yet supplied by the owner". A
    model with ``versions`` must have at least one complete version.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1)
    input_usd_per_mtok: Decimal | None = None
    output_usd_per_mtok: Decimal | None = None
    cached_input_usd_per_mtok: Decimal | None = None
    versions: tuple[PriceVersion, ...] = ()

    @field_validator(
        "input_usd_per_mtok",
        "output_usd_per_mtok",
        "cached_input_usd_per_mtok",
    )
    @classmethod
    def _non_negative(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and value < 0:
            raise ValueError("price must be greater than or equal to zero")
        return value

    @model_validator(mode="after")
    def _flat_or_versions(self) -> ModelPrice:
        flat = (
            self.input_usd_per_mtok is not None
            or self.output_usd_per_mtok is not None
            or self.cached_input_usd_per_mtok is not None
        )
        if self.versions and flat:
            raise ValueError("use either flat prices or dated versions, not both")
        if self.versions:
            for version in self.versions:
                if version.input_usd_per_mtok is None or version.output_usd_per_mtok is None:
                    raise ValueError("a dated price version must include input and output prices")
        return self

    @property
    def is_priced(self) -> bool:
        """Whether a complete price is available for at least one date."""
        if self.versions:
            return all(
                version.input_usd_per_mtok is not None and version.output_usd_per_mtok is not None
                for version in self.versions
            )
        return self.input_usd_per_mtok is not None and self.output_usd_per_mtok is not None

    def select(self, day: date | None = None) -> PriceSelection:
        """Select the price version that applies on ``day``."""
        if self.versions:
            on_date = day or datetime.now(UTC).date()
            matches = [version for version in self.versions if version.applies_on(on_date)]
            if not matches:
                labels = ", ".join(version.label for version in self.versions)
                raise MissingPriceError(
                    f"no price version applies on {on_date.isoformat()}; available: {labels}"
                )
            version = max(matches, key=lambda item: item.effective_from)
            return PriceSelection(
                input_usd_per_mtok=version.input_usd_per_mtok,
                output_usd_per_mtok=version.output_usd_per_mtok,
                cached_input_usd_per_mtok=version.cached_input_usd_per_mtok,
                price_version=version.label,
            )
        if not self.is_priced:
            raise MissingPriceError("price entry is incomplete")
        assert self.input_usd_per_mtok is not None
        assert self.output_usd_per_mtok is not None
        return PriceSelection(
            input_usd_per_mtok=self.input_usd_per_mtok,
            output_usd_per_mtok=self.output_usd_per_mtok,
            cached_input_usd_per_mtok=self.cached_input_usd_per_mtok,
            price_version="flat",
        )

    def post_promotion(self) -> PriceSelection:
        """Return the latest known version, for the post-promotion comparison."""
        if not self.versions:
            return self.select()
        version = max(self.versions, key=lambda item: item.effective_from)
        return PriceSelection(
            input_usd_per_mtok=version.input_usd_per_mtok,
            output_usd_per_mtok=version.output_usd_per_mtok,
            cached_input_usd_per_mtok=version.cached_input_usd_per_mtok,
            price_version=version.label,
        )


class PricingTable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    currency: Literal["USD"] = "USD"
    models: dict[str, ModelPrice] = Field(default_factory=dict)

    def price_for(self, model: str) -> ModelPrice:
        try:
            return self.models[model]
        except KeyError as exc:
            raise MissingPriceError(f"no price entry for model {model!r}") from exc

    def require_priced(self, model: str) -> ModelPrice:
        price = self.price_for(model)
        if not price.is_priced:
            raise MissingPriceError(f"price entry for model {model!r} is incomplete")
        return price

    def select(self, model: str, day: date | None = None) -> PriceSelection:
        return self.require_priced(model).select(day)


def load_pricing(path: Path) -> PricingTable:
    """Load and validate a pricing YAML file."""
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PricingError(f"cannot read pricing file {path}") from exc

    if raw is None:
        raise PricingError(f"pricing file is empty: {path}")
    if not isinstance(raw, dict):
        raise PricingError(f"pricing file must contain a mapping: {path}")

    try:
        return PricingTable.model_validate(raw)
    except ValidationError as exc:
        raise PricingError(f"invalid pricing file {path}: {exc}") from exc


def estimate_cost_details(
    pricing: PricingTable,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    dry_run: bool,
    on_date: date | None = None,
) -> CostEstimate:
    """Estimate list-price cost at the call date and at the latest known price.

    With ``dry_run=True`` an unknown or incomplete price raises
    :class:`MissingPriceError` (fail closed). Outside dry-run it warns loudly
    and returns an estimate with ``None`` costs so the caller cannot silently
    book a fabricated cost.
    """
    if prompt_tokens < 0 or completion_tokens < 0:
        raise ValueError("token counts must be non-negative")

    try:
        price = pricing.price_for(model)
        current = price.select(on_date)
        post = price.post_promotion()
    except MissingPriceError:
        if dry_run:
            raise
        _warn_missing_price(model)
        return CostEstimate(
            usd=None,
            post_promotion_usd=None,
            input_usd=None,
            output_usd=None,
            price_version=None,
            post_promotion_version=None,
        )

    total, input_usd, output_usd = _split_cost(current, prompt_tokens, completion_tokens)
    post_total, _, _ = _split_cost(post, prompt_tokens, completion_tokens)
    return CostEstimate(
        usd=total,
        post_promotion_usd=post_total,
        input_usd=input_usd,
        output_usd=output_usd,
        price_version=current.price_version,
        post_promotion_version=post.price_version,
    )


def estimate_cost(
    pricing: PricingTable,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    dry_run: bool,
    on_date: date | None = None,
) -> Decimal | None:
    """Return only the call-date list-price cost, for compatibility."""
    return estimate_cost_details(
        pricing,
        model,
        prompt_tokens,
        completion_tokens,
        dry_run=dry_run,
        on_date=on_date,
    ).usd


def _split_cost(
    price: PriceSelection, prompt_tokens: int, completion_tokens: int
) -> tuple[Decimal, Decimal, Decimal]:
    total = (
        Decimal(prompt_tokens) * price.input_usd_per_mtok
        + Decimal(completion_tokens) * price.output_usd_per_mtok
    ) / _TOKEN_DIVISOR
    total = total.quantize(_USD_QUANTUM)
    input_usd = (Decimal(prompt_tokens) * price.input_usd_per_mtok / _TOKEN_DIVISOR).quantize(
        _USD_QUANTUM
    )
    output_usd = total - input_usd
    return total, input_usd, output_usd


def _warn_missing_price(model: str) -> None:
    warnings.warn(
        f"missing or incomplete price for model {model!r}; cost not recorded",
        RuntimeWarning,
        stacklevel=3,
    )


__all__ = [
    "CostEstimate",
    "MissingPriceError",
    "ModelPrice",
    "PriceSelection",
    "PriceVersion",
    "PricingError",
    "PricingTable",
    "estimate_cost",
    "estimate_cost_details",
    "load_pricing",
]
