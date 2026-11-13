"""Tests for provider error classification."""

from __future__ import annotations

import pytest

from axion.llm.errors import (
    PermanentProviderError,
    RateLimitError,
    TransientProviderError,
    classify_error,
)


class ProviderError(Exception):
    pass


@pytest.mark.parametrize(
    "message",
    [
        "429 Too Many Requests",
        "rate_limit_exceeded",
        "Rate limit reached",
        "RESOURCE_EXHAUSTED: quota exceeded",
        "You exceeded your current quota",
    ],
)
def test_rate_limits(message: str) -> None:
    assert isinstance(classify_error(ProviderError(message)), RateLimitError)


@pytest.mark.parametrize(
    "message",
    [
        "503 UNAVAILABLE",
        "502 Bad Gateway",
        "504 Deadline Exceeded",
        "request timed out",
        "Connection reset by peer",
    ],
)
def test_transient_errors(message: str) -> None:
    assert isinstance(classify_error(ProviderError(message)), TransientProviderError)


@pytest.mark.parametrize(
    "message",
    ["invalid api key", "401 Unauthorized", "404 model not found"],
)
def test_permanent_errors(message: str) -> None:
    assert isinstance(classify_error(ProviderError(message)), PermanentProviderError)


def test_typed_errors_pass_through() -> None:
    error = RateLimitError("slow down")
    assert classify_error(error) is error
