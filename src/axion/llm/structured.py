"""Structured-output parsing and Pydantic validation."""

from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from axion.llm.errors import StructuredOutputError

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)


def parse_structured(text: str, model_type: type[T]) -> T:
    """Validate model text against a Pydantic model.

    Accepts plain JSON, fenced JSON, and JSON embedded in surrounding prose.
    Raises :class:`StructuredOutputError` when no candidate validates.
    """
    stripped = text.strip()
    candidates = [stripped]

    fenced = _FENCE.match(stripped)
    if fenced is not None:
        candidates.append(fenced.group(1).strip())

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])

    last_error: ValidationError | None = None
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return model_type.model_validate_json(candidate)
        except ValidationError as exc:
            last_error = exc

    raise StructuredOutputError(
        f"could not parse {model_type.__name__} from structured model output"
    ) from last_error
