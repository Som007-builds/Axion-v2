"""Tests for the stage configuration schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from axion.config.stages import StageConfig, StagesConfig


def test_deterministic_stage_needs_no_model() -> None:
    stage = StageConfig(stage="parse")

    assert stage.tier == "deterministic"
    assert stage.model is None
    assert stage.max_calls is None


def test_llm_stage_carries_configured_model_and_caps() -> None:
    stage = StageConfig(
        stage="extract",
        tier="large",
        model="provider/model-a",
        max_calls=7,
        max_output_tokens=2048,
        timeout_s=30.0,
        temperature=0.0,
    )

    assert stage.model == "provider/model-a"
    assert stage.max_calls == 7

    config = StagesConfig(version=1, stages={"extract": stage})
    assert config.stages["extract"] is stage


def test_enabled_llm_tier_requires_a_model() -> None:
    with pytest.raises(ValidationError, match="has no model"):
        StageConfig(stage="extract", tier="small")


def test_disabled_llm_stage_may_omit_model() -> None:
    stage = StageConfig(stage="extract", tier="small", enabled=False)

    assert stage.model is None


def test_stage_keys_must_match_stage_names() -> None:
    stage = StageConfig(stage="extract", tier="large", model="provider/model-a")

    with pytest.raises(ValidationError, match="do not match"):
        StagesConfig(version=1, stages={"link": stage})


def test_unknown_fields_and_bad_ranges_are_rejected() -> None:
    with pytest.raises(ValidationError):
        StageConfig(stage="parse", mystery=True)

    with pytest.raises(ValidationError):
        StageConfig(stage="parse", temperature=-0.1)

    with pytest.raises(ValidationError):
        StageConfig(stage="parse", max_calls=0)
