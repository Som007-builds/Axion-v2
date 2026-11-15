"""Groq provider adapter.

The official ``groq`` package is the only provider SDK in this repository. It
is pinned in ``pyproject.toml`` and isolated behind the existing
:class:`axion.llm.adapters.ProviderAdapter` interface. The adapter translates
SDK failures into the project's retry taxonomy; it never writes the ledger,
cache, or cost estimate itself.
"""

from __future__ import annotations

from typing import Any

import groq
from pydantic import SecretStr

from axion.llm.adapters import ProviderAdapter, ProviderAdapterConfig
from axion.llm.errors import (
    ConfigurationError,
    PermanentProviderError,
    RateLimitError,
    TransientProviderError,
)
from axion.llm.models import ProviderRequest, ProviderResponse


class GroqAdapter(ProviderAdapter):
    """One Groq chat-completions adapter with no retry logic of its own."""

    name = "groq"

    def __init__(
        self,
        api_key: SecretStr | str,
        *,
        timeout_s: float = 60.0,
        max_output_tokens: int | None = None,
        client: Any | None = None,
    ) -> None:
        key = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        if not key.strip():
            raise ConfigurationError("GROQ_API_KEY is empty")
        if timeout_s <= 0:
            raise ConfigurationError("Groq timeout must be positive")
        self._config = ProviderAdapterConfig(
            name=self.name,
            base_url="https://api.groq.com/openai/v1",
            api_key_env="GROQ_API_KEY",
            timeout_s=timeout_s,
            max_output_tokens=max_output_tokens,
        )
        self._client = client or groq.Groq(api_key=key, timeout=timeout_s)

    @property
    def config(self) -> ProviderAdapterConfig:
        return self._config

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        messages: list[dict[str, str]] = []
        if request.system:
            messages.append({"role": "system", "content": request.system})
        messages.append({"role": "user", "content": request.prompt})

        kwargs: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            # Keep the reasoning text out of the cached response; usage still
            # reports the reasoning token count.
            "include_reasoning": False,
        }
        max_tokens = request.max_output_tokens or self._config.max_output_tokens
        if max_tokens is not None:
            kwargs["max_completion_tokens"] = max_tokens
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature

        try:
            completion = self._client.chat.completions.create(**kwargs)
        except groq.RateLimitError as exc:
            raise RateLimitError(f"Groq rate limit: {exc}") from exc
        except (groq.APIConnectionError, groq.APITimeoutError, groq.InternalServerError) as exc:
            raise TransientProviderError(f"Groq transient failure: {exc}") from exc
        except groq.APIStatusError as exc:
            status = getattr(exc, "status_code", None)
            message = str(exc).lower()
            rate_limit = (
                status == 429
                or "rate_limit_exceeded" in message
                or "tokens per minute" in message
                or "tpm" in message
            )
            if rate_limit:
                raise RateLimitError(f"Groq rate limit ({status}): {exc}") from exc
            if isinstance(status, int) and status >= 500:
                raise TransientProviderError(f"Groq server failure ({status}): {exc}") from exc
            raise PermanentProviderError(f"Groq request failed ({status}): {exc}") from exc
        except groq.GroqError as exc:
            raise PermanentProviderError(f"Groq SDK failure: {exc}") from exc

        choices = getattr(completion, "choices", None) or []
        if not choices:
            raise TransientProviderError("Groq returned no choices")
        choice_message = getattr(choices[0], "message", None)
        text = getattr(choice_message, "content", None)
        if not isinstance(text, str) or not text.strip():
            raise TransientProviderError("Groq returned an empty response")

        usage = getattr(completion, "usage", None)
        if usage is None:
            raise PermanentProviderError("Groq response has no token usage")
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        details = getattr(usage, "completion_tokens_details", None)
        reasoning_tokens = (
            int(getattr(details, "reasoning_tokens", 0) or 0) if details is not None else 0
        )
        if prompt_tokens < 0 or completion_tokens < 0 or reasoning_tokens < 0:
            raise PermanentProviderError("Groq returned negative token usage")

        return ProviderResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=getattr(completion, "model", None) or request.model,
            reasoning_tokens=reasoning_tokens,
        )


__all__ = ["GroqAdapter"]
