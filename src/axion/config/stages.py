"""Schema for stage configuration.

Stage names and model identifiers come from configuration, never from code.
Operational parameters are optional so that each environment can supply its own
caps without the schema embedding business thresholds.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

Tier = Literal["deterministic", "small", "large"]


class StageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: str = Field(min_length=1)
    enabled: bool = True
    tier: Tier = "deterministic"
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_output_tokens: int | None = Field(default=None, gt=0)
    timeout_s: float | None = Field(default=None, gt=0)
    max_calls: int | None = Field(default=None, ge=1)
    cache: bool = True
    params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _model_required_for_llm_tiers(self) -> Self:
        if self.tier != "deterministic" and self.enabled and self.model is None:
            raise ValueError(f"stage {self.stage!r} is tier {self.tier!r} but has no model")
        return self


class StagesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    stages: dict[str, StageConfig] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _keys_match_stage_names(self) -> Self:
        mismatched = [key for key, config in self.stages.items() if key != config.stage]
        if mismatched:
            raise ValueError(f"stage keys do not match their stage field: {mismatched}")
        return self
