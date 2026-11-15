"""Offline tests for the Groq adapter (no network calls)."""

from __future__ import annotations

from types import SimpleNamespace

import groq
import httpx
import pytest

from axion.llm.errors import (
    ConfigurationError,
    RateLimitError,
    TransientProviderError,
)
from axion.llm.groq import GroqAdapter
from axion.llm.models import ProviderRequest


class _FakeCompletions:
    def __init__(self, completion: object | Exception) -> None:
        self.completion = completion
        self.calls: list[dict[str, object]] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if isinstance(self.completion, Exception):
            raise self.completion
        return self.completion


class _FakeGroq:
    def __init__(self, completion: object | Exception) -> None:
        self.chat = SimpleNamespace(completions=_FakeCompletions(completion))


def _completion(text: str = '{"claims": []}') -> object:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
        model="openai/gpt-oss-120b",
        usage=SimpleNamespace(
            prompt_tokens=123,
            completion_tokens=45,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=20),
        ),
    )


def test_groq_adapter_returns_text_and_reasoning_usage() -> None:
    fake = _FakeGroq(_completion())
    adapter = GroqAdapter("test-key", client=fake)
    response = adapter.complete(
        ProviderRequest(
            prompt="Extract claims.",
            model="openai/gpt-oss-120b",
            max_output_tokens=2048,
        )
    )

    assert response.text == '{"claims": []}'
    assert response.prompt_tokens == 123
    assert response.completion_tokens == 45
    assert response.reasoning_tokens == 20
    call = fake.chat.completions.calls[0]
    assert call["model"] == "openai/gpt-oss-120b"
    assert call["max_completion_tokens"] == 2048
    assert call["include_reasoning"] is False
    messages = call["messages"]
    assert isinstance(messages, list)
    assert messages[0]["role"] == "user"


def _status_error(status: int, message: str) -> groq.APIStatusError:
    request = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    response = httpx.Response(status, request=request)
    return groq.APIStatusError(message, response=response, body={"error": message})


def test_groq_adapter_maps_request_too_large_to_rate_limit() -> None:
    error = _status_error(
        413,
        "Request too large on tokens per minute (TPM): Limit 8000, Requested 12111; "
        "code: rate_limit_exceeded",
    )
    adapter = GroqAdapter("test-key", client=_FakeGroq(error))
    with pytest.raises(RateLimitError, match="413"):
        adapter.complete(ProviderRequest(prompt="x", model="openai/gpt-oss-120b"))


def test_groq_adapter_maps_server_error_to_transient() -> None:
    adapter = GroqAdapter("test-key", client=_FakeGroq(_status_error(500, "internal")))
    with pytest.raises(TransientProviderError, match="500"):
        adapter.complete(ProviderRequest(prompt="x", model="openai/gpt-oss-120b"))


def test_groq_adapter_rejects_empty_key() -> None:
    with pytest.raises(ConfigurationError, match="empty"):
        GroqAdapter(" ")


def test_groq_adapter_rejects_empty_response() -> None:
    fake = _FakeGroq(_completion("  "))
    adapter = GroqAdapter("test-key", client=fake)
    with pytest.raises(TransientProviderError, match="empty"):
        adapter.complete(ProviderRequest(prompt="x", model="openai/gpt-oss-120b"))
