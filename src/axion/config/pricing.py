"""Pricing table parsing and fail-closed cost estimation."""

from __future__ import annotations

import warnings
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

_USD_QUANTUM = Decimal("0.000001")
_TOKEN_DIVISOR = Decimal(1_000_000)


class PricingError(Exception):
    """Raised when the pricing file cannot be loaded or validated."""


class MissingPriceError(PricingError):
    """Raised when a model has no complete price entry."""


class ModelPrice(BaseModel):
    """Prices for one model, expressed in USD per million tokens.

    Blank prices are valid and mean "not yet supplied by the owner".
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: str = Field(min_length=1)
    input_usd_per_mtok: Decimal | None = None
    output_usd_per_mtok: Decimal | None = None
    cached_input_usd_per_mtok: Decimal | None = None

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

    @property
    def is_priced(self) -> bool:
        """Whether the two prices required for a cost estimate are present."""
        return self.input_usd_per_mtok is not None and self.output_usd_per_mtok is not None


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


def estimate_cost(
    pricing: PricingTable,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    dry_run: bool,
) -> Decimal | None:
    """Estimate USD cost for one call.

    With ``dry_run=True`` an unknown or incomplete price raises
    :class:`MissingPriceError` (fail closed). Outside dry-run it warns loudly
    and returns ``None`` so the caller cannot silently book a fabricated cost.
    """
    if prompt_tokens < 0 or completion_tokens < 0:
        raise ValueError("token counts must be non-negative")

    try:
        price = pricing.require_priced(model)
    except MissingPriceError:
        if dry_run:
            raise
        _warn_missing_price(model)
        return None

    input_price = price.input_usd_per_mtok
    output_price = price.output_usd_per_mtok
    if input_price is None or output_price is None:  # pragma: no cover - guarded above
        raise MissingPriceError(f"price entry for model {model!r} is incomplete")

    cost = (
        Decimal(prompt_tokens) * input_price + Decimal(completion_tokens) * output_price
    ) / _TOKEN_DIVISOR
    return cost.quantize(_USD_QUANTUM)


def _warn_missing_price(model: str) -> None:
    warnings.warn(
        f"missing or incomplete price for model {model!r}; cost not recorded",
        RuntimeWarning,
        stacklevel=3,
    )
