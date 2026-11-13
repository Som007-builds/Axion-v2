"""Tests for structured-output parsing."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from axion.llm.errors import StructuredOutputError
from axion.llm.structured import parse_structured


class Claim(BaseModel):
    text: str


def test_plain_json() -> None:
    parsed = parse_structured('{"text": "a finding"}', Claim)
    assert parsed.text == "a finding"


def test_fenced_json() -> None:
    parsed = parse_structured('```json\n{"text": "a finding"}\n```', Claim)
    assert parsed.text == "a finding"


def test_json_embedded_in_prose() -> None:
    parsed = parse_structured('Here is the answer: {"text": "a finding"} done.', Claim)
    assert parsed.text == "a finding"


def test_invalid_output_raises() -> None:
    with pytest.raises(StructuredOutputError, match="could not parse Claim"):
        parse_structured("not json at all", Claim)


def test_schema_mismatch_raises() -> None:
    with pytest.raises(StructuredOutputError):
        parse_structured('{"wrong": "field"}', Claim)
