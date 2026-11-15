"""Google Gemini provider adapter.

The official ``google-genai`` SDK is pinned in ``pyproject.toml`` and isolated
behind :class:`axion.llm.adapters.ProviderAdapter`. The adapter translates SDK
failures into the project's retry taxonomy; it never writes the ledger, cache,
or cost estimate itself.

Gemini's usage metadata reports ``candidates_token_count`` separately from
``thoughts_token_count``. Output price includes both, so the adapter returns
``completion_tokens = candidates + thoughts`` and ``reasoning_tokens =
thoughts``; that keeps thinking-token accounting consistent with the existing
Groq adapter.
"""

from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import google.genai as genai
from google.genai import errors, types
from pydantic import BaseModel, SecretStr

from axion.llm.adapters import ProviderAdapter, ProviderAdapterConfig
from axion.llm.errors import (
    ConfigurationError,
    DailyQuotaError,
    PermanentProviderError,
    RateLimitError,
    TransientProviderError,
)
from axion.llm.models import ProviderRequest, ProviderResponse

_DAILY_MARKERS = ("perday", "per day", "daily", "requestsperday")
_BLOCKING_FINISH_REASONS = {
    types.FinishReason.SAFETY,
    types.FinishReason.BLOCKLIST,
    types.FinishReason.PROHIBITED_CONTENT,
    types.FinishReason.RECITATION,
    types.FinishReason.SPII,
    types.FinishReason.LANGUAGE,
}


class GeminiAdapter(ProviderAdapter):
    """One Gemini generate-content adapter with no retry logic of its own."""

    name = "gemini"

    def __init__(
        self,
        api_key: SecretStr | str,
        *,
        timeout_s: float = 120.0,
        max_output_tokens: int | None = None,
        client: Any | None = None,
    ) -> None:
        key = api_key.get_secret_value() if isinstance(api_key, SecretStr) else api_key
        if not key.strip():
            raise ConfigurationError("GEMINI_API_KEY is empty")
        if timeout_s <= 0:
            raise ConfigurationError("Gemini timeout must be positive")
        self._config = ProviderAdapterConfig(
            name=self.name,
            base_url="https://generativelanguage.googleapis.com",
            api_key_env="GEMINI_API_KEY",
            timeout_s=timeout_s,
            max_output_tokens=max_output_tokens,
        )
        self._client = client or genai.Client(
            api_key=key,
            http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
        )

    @property
    def config(self) -> ProviderAdapterConfig:
        return self._config

    def complete(self, request: ProviderRequest) -> ProviderResponse:
        config = self._generation_config(request)
        try:
            response = self._client.models.generate_content(
                model=request.model,
                contents=request.prompt,
                config=config,
            )
        except errors.APIError as exc:
            raise _map_api_error(exc) from exc
        except Exception as exc:
            message = str(exc).lower()
            if any(marker in message for marker in ("timeout", "timed out", "connection", "503")):
                raise TransientProviderError(f"Gemini transport error: {exc}") from exc
            raise PermanentProviderError(f"Gemini request failed: {exc}") from exc

        return _response_from_sdk(response, requested_model=request.model)

    def _generation_config(self, request: ProviderRequest) -> types.GenerateContentConfig:
        kwargs: dict[str, Any] = {
            "system_instruction": request.system,
            "temperature": request.temperature,
            "max_output_tokens": request.max_output_tokens or self._config.max_output_tokens,
        }
        if request.response_schema is not None:
            kwargs["response_mime_type"] = "application/json"
            kwargs["response_json_schema"] = _json_schema_without_additional_properties(
                request.response_schema
            )
        if request.thinking_level is not None:
            level = request.thinking_level.strip().upper()
            if level not in {item.value for item in types.ThinkingLevel}:
                raise ConfigurationError(
                    f"unsupported Gemini thinking level {request.thinking_level!r}"
                )
            kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=level)
        return types.GenerateContentConfig(**kwargs)


def _json_schema_without_additional_properties(
    response_model: type[BaseModel],
) -> dict[str, Any]:
    """Return the Pydantic JSON schema without unsupported object policy keys.

    The Gemini Developer API rejects ``additionalProperties`` even when it is
    ``false``. Pydantic emits it for models with ``extra="forbid"``; validation
    still happens locally after the response is parsed.
    """
    schema: dict[str, Any] = deepcopy(response_model.model_json_schema())
    _strip_additional_properties(schema)
    return schema


def _strip_additional_properties(value: Any) -> None:
    if isinstance(value, dict):
        value.pop("additionalProperties", None)
        for child in value.values():
            _strip_additional_properties(child)
    elif isinstance(value, list):
        for child in value:
            _strip_additional_properties(child)


def _response_from_sdk(response: Any, *, requested_model: str) -> ProviderResponse:
    finish_reason = _finish_reason(response)
    text = getattr(response, "text", None)
    if text is None or not str(text).strip():
        if finish_reason in _BLOCKING_FINISH_REASONS:
            raise PermanentProviderError(
                f"Gemini blocked the response (finish_reason={finish_reason})"
            )
        if finish_reason == types.FinishReason.MAX_TOKENS:
            raise PermanentProviderError("Gemini stopped at max_output_tokens with no text")
        raise TransientProviderError(
            f"Gemini returned an empty response (finish_reason={finish_reason})"
        )

    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        raise TransientProviderError("Gemini response has no usage_metadata")
    prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
    candidates_tokens = int(getattr(usage, "candidates_token_count", 0) or 0)
    thoughts_tokens = int(getattr(usage, "thoughts_token_count", 0) or 0)
    if prompt_tokens < 0 or candidates_tokens < 0 or thoughts_tokens < 0:
        raise PermanentProviderError("Gemini returned negative token usage")

    return ProviderResponse(
        text=str(text),
        prompt_tokens=prompt_tokens,
        completion_tokens=candidates_tokens + thoughts_tokens,
        reasoning_tokens=thoughts_tokens,
        model=getattr(response, "model_version", None) or requested_model,
    )


def _finish_reason(response: Any) -> types.FinishReason | None:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None
    return getattr(candidates[0], "finish_reason", None)


def _map_api_error(exc: errors.APIError) -> Exception:
    code = int(getattr(exc, "code", 0) or 0)
    status = str(getattr(exc, "status", "") or "")
    details = _details_text(exc)
    compact = details.lower().replace("_", "").replace("-", "")
    is_quota = (
        code == 429
        or status.upper() == "RESOURCE_EXHAUSTED"
        or "quota" in details.lower()
        or "resourceexhausted" in compact
    )
    if is_quota:
        if any(marker.replace("_", "") in compact for marker in _DAILY_MARKERS):
            return DailyQuotaError(f"Gemini daily quota exhausted: {details[:500]}")
        return RateLimitError(f"Gemini rate limit: {details[:500]}")
    if code >= 500:
        return TransientProviderError(f"Gemini server error ({code}): {details[:500]}")
    return PermanentProviderError(f"Gemini API error ({code}/{status}): {details[:500]}")


def _details_text(exc: errors.APIError) -> str:
    details = getattr(exc, "details", None)
    if details is None:
        return str(exc)
    try:
        return json.dumps(details, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(details)


__all__ = ["GeminiAdapter"]
