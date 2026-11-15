"""Offline tests for the Gemini adapter (no network calls)."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors, types

from axion.extract.claims import ClaimExtraction
from axion.llm.errors import (
    ConfigurationError,
    DailyQuotaError,
    OutputTokenExhaustedError,
    PermanentProviderError,
    RateLimitError,
    TransientProviderError,
)
from axion.llm.gemini import GeminiAdapter
from axion.llm.models import ProviderRequest


class _FakeModels:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def generate_content(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


def _fake_client(response: Any = None, error: Exception | None = None) -> Any:
    return SimpleNamespace(models=_FakeModels(response, error))


def _response(
    *,
    text: str = '{"claims": []}',
    candidates: int = 10,
    thoughts: int = 4,
    finish_reason: types.FinishReason = types.FinishReason.STOP,
) -> Any:
    return SimpleNamespace(
        text=text,
        candidates=[SimpleNamespace(finish_reason=finish_reason)],
        usage_metadata=SimpleNamespace(
            prompt_token_count=100,
            candidates_token_count=candidates,
            thoughts_token_count=thoughts,
        ),
        model_version="gemini-3.8-flash",
    )


def _request(**kwargs: Any) -> ProviderRequest:
    values: dict[str, Any] = {
        "prompt": "Extract claims.",
        "model": "gemini-3.8-flash",
        "temperature": 0.0,
        "max_output_tokens": 8192,
        "response_schema": ClaimExtraction,
        "thinking_level": "medium",
    }
    values.update(kwargs)
    return ProviderRequest(**values)


def test_adapter_returns_text_and_thinking_usage() -> None:
    client = _fake_client(_response())
    adapter = GeminiAdapter("key", client=client)

    response = adapter.complete(_request())

    assert response.text == '{"claims": []}'
    assert response.prompt_tokens == 100
    assert response.completion_tokens == 14
    assert response.reasoning_tokens == 4
    assert response.model == "gemini-3.8-flash"

    call = client.models.calls[0]
    config = call["config"]
    assert config.response_mime_type == "application/json"
    assert config.response_json_schema["title"] == "ClaimExtraction"
    assert "additionalProperties" not in config.response_json_schema
    assert "additionalProperties" not in config.response_json_schema["$defs"]["Claim"]
    assert config.thinking_config.thinking_level == "MEDIUM"
    assert config.temperature == 0.0
    assert config.max_output_tokens == 8192


def test_daily_quota_is_not_a_retryable_rate_limit() -> None:
    error = errors.APIError(
        429,
        {
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "message": "Quota exceeded",
                "details": [
                    {
                        "violations": [
                            {"quotaId": ("GenerateRequestsPerDayPerProjectPerModel-FreeTier")}
                        ]
                    }
                ],
            }
        },
    )
    adapter = GeminiAdapter("key", client=_fake_client(error=error))

    with pytest.raises(DailyQuotaError):
        adapter.complete(_request())


def test_per_minute_quota_is_a_rate_limit() -> None:
    error = errors.APIError(
        429,
        {
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "message": "Quota exceeded",
                "details": [
                    {
                        "violations": [
                            {"quotaId": ("GenerateRequestsPerMinutePerProjectPerModel-FreeTier")}
                        ]
                    }
                ],
            }
        },
    )
    adapter = GeminiAdapter("key", client=_fake_client(error=error))

    with pytest.raises(RateLimitError):
        adapter.complete(_request())


def test_server_error_is_transient() -> None:
    adapter = GeminiAdapter("key", client=_fake_client(error=errors.APIError(503, {"error": {}})))

    with pytest.raises(TransientProviderError):
        adapter.complete(_request())


def test_blocked_response_is_permanent() -> None:
    adapter = GeminiAdapter(
        "key",
        client=_fake_client(_response(text="", finish_reason=types.FinishReason.SAFETY)),
    )

    with pytest.raises(PermanentProviderError, match="blocked"):
        adapter.complete(_request())


def test_empty_key_is_rejected() -> None:
    with pytest.raises(ConfigurationError):
        GeminiAdapter("  ")


def test_missing_usage_is_transient() -> None:
    response = _response()
    response.usage_metadata = None
    adapter = GeminiAdapter("key", client=_fake_client(response))

    with pytest.raises(TransientProviderError):
        adapter.complete(_request())


def test_max_tokens_empty_is_permanent_and_keeps_usage() -> None:
    response = _response(
        text="",
        candidates=0,
        thoughts=8192,
        finish_reason=types.FinishReason.MAX_TOKENS,
    )
    adapter = GeminiAdapter("key", client=_fake_client(response))

    with pytest.raises(OutputTokenExhaustedError, match="budget was exhausted") as info:
        adapter.complete(_request(max_output_tokens=8192))

    detail = info.value.detail
    assert detail is not None
    assert detail.error_class == "OutputTokenExhaustedError"
    assert detail.provider_status == "MAX_TOKENS"
    assert detail.finish_reason == "MAX_TOKENS"
    assert detail.reasoning_tokens == 8192
    assert detail.completion_tokens == 8192
    assert detail.retryable is False


def test_default_thinking_sends_no_thinking_config() -> None:
    client = _fake_client(_response())
    adapter = GeminiAdapter("key", client=client)

    adapter.complete(_request(thinking_level="default"))

    config = client.models.calls[0]["config"]
    assert config.thinking_config is None
    assert config.max_output_tokens == 8192


def test_api_error_detail_is_sanitized() -> None:
    error = errors.APIError(
        400,
        {
            "error": {
                "code": 400,
                "status": "INVALID_ARGUMENT",
                "message": "bad request with header Authorization: Bearer fixture-token",
            }
        },
    )
    adapter = GeminiAdapter("key", client=_fake_client(error=error))

    with pytest.raises(PermanentProviderError) as info:
        adapter.complete(_request())

    assert "fixture-token" not in str(info.value)
    assert "[redacted]" in str(info.value)
    assert info.value.detail is not None
    assert info.value.detail.http_status == 400
    assert info.value.detail.provider_status == "INVALID_ARGUMENT"


def test_prompt_is_sent_verbatim() -> None:
    client = _fake_client(_response(text=json.dumps({"claims": []})))
    adapter = GeminiAdapter("key", client=client)

    adapter.complete(_request(prompt="a paper"))

    assert client.models.calls[0]["contents"] == "a paper"
