"""Google Gemini provider adapter.

The official ``google-genai`` SDK is pinned in ``pyproject.toml`` and isolated
behind :class:`axion.llm.adapters.ProviderAdapter`. The adapter translates SDK
failures into the project's retry taxonomy and attaches a sanitized
:class:`~axion.llm.errors.FailureDetail` so the ledger and run report can show
the root cause instead of a generic "all providers failed".

Gemini's usage metadata reports ``candidates_token_count`` separately from
``thoughts_token_count``. Output price includes both, so the adapter returns
``completion_tokens = candidates + thoughts`` and ``reasoning_tokens =
thoughts``; that keeps thinking-token accounting consistent with the existing
Groq adapter.

Empty responses are classified, never retried blindly:

* ``finish_reason=MAX_TOKENS`` with no text means thinking (or the answer) used
  the whole output budget. That is ``OutputTokenExhaustedError``: permanent
  **with unchanged parameters**, because a retry would spend quota and fail the
  same way.
* A safety/recitation block is permanent.
* Any other empty body is ``EmptyResponseError``, also permanent.
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
    EmptyResponseError,
    FailureDetail,
    OutputTokenExhaustedError,
    PermanentProviderError,
    ProviderError,
    RateLimitError,
    TransientProviderError,
    sanitize_error_text,
)
from axion.llm.models import ProviderRequest, ProviderResponse

_DAILY_MARKERS = ("perday", "per day", "daily", "requestsperday")
_BLOCKING_FINISH_REASONS = {
    "SAFETY",
    "BLOCKLIST",
    "PROHIBITED_CONTENT",
    "RECITATION",
    "SPII",
    "LANGUAGE",
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
            sanitized = sanitize_error_text(f"{type(exc).__name__}: {exc}")
            if any(
                marker in message
                for marker in (
                    "timeout",
                    "timed out",
                    "connection",
                    "503",
                    "ssl",
                    "readerror",
                    "bad record mac",
                    "server disconnected",
                    "remote protocol error",
                )
            ):
                raise TransientProviderError(
                    f"Gemini transport error: {sanitized}",
                    detail=FailureDetail(
                        error_class=type(exc).__name__,
                        message=sanitized,
                        retryable=True,
                    ),
                ) from exc
            raise PermanentProviderError(
                f"Gemini request failed: {sanitized}",
                detail=FailureDetail(
                    error_class=type(exc).__name__,
                    message=sanitized,
                    retryable=False,
                ),
            ) from exc

        return _response_from_sdk(
            response,
            requested_model=request.model,
            max_output_tokens=config.max_output_tokens or 0,
        )

    def _generation_config(self, request: ProviderRequest) -> types.GenerateContentConfig:
        max_output_tokens = request.max_output_tokens or self._config.max_output_tokens
        kwargs: dict[str, Any] = {
            "system_instruction": request.system,
            "temperature": request.temperature,
            "max_output_tokens": max_output_tokens,
        }
        if request.response_schema is not None:
            kwargs["response_mime_type"] = "application/json"
            kwargs["response_json_schema"] = _json_schema_without_additional_properties(
                request.response_schema
            )
        if request.thinking_level is not None:
            level = request.thinking_level.strip().upper()
            # Recording an explicit "default" keeps provenance unambiguous while
            # sending no thinking_config at all, so the model uses its own default.
            if level in {"DEFAULT", "PROVIDER_DEFAULT"}:
                return types.GenerateContentConfig(**kwargs)
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
    still happens locally after the response is parsed. Both spellings are
    stripped because the SDK has been observed to forward snake_case keys.
    """
    schema: dict[str, Any] = deepcopy(response_model.model_json_schema())
    _strip_additional_properties(schema)
    return schema


def _strip_additional_properties(value: Any) -> None:
    if isinstance(value, dict):
        value.pop("additionalProperties", None)
        value.pop("additional_properties", None)
        for child in value.values():
            _strip_additional_properties(child)
    elif isinstance(value, list):
        for child in value:
            _strip_additional_properties(child)


def _response_text(response: Any) -> str | None:
    """Read response text without letting the SDK's empty-body ValueError escape."""
    try:
        text = response.text
    except (ValueError, AttributeError):
        return None
    if text is None:
        return None
    return str(text)


def _usage_tokens(response: Any) -> tuple[int, int, int]:
    usage = getattr(response, "usage_metadata", None)
    if usage is None:
        return (0, 0, 0)
    return (
        int(getattr(usage, "prompt_token_count", 0) or 0),
        int(getattr(usage, "candidates_token_count", 0) or 0),
        int(getattr(usage, "thoughts_token_count", 0) or 0),
    )


def _empty_response_error(
    *,
    finish_reason: str | None,
    max_output_tokens: int,
    prompt_tokens: int,
    candidates_tokens: int,
    thoughts_tokens: int,
) -> ProviderError:
    prompt_or_none = prompt_tokens or None
    completion_or_none = (candidates_tokens + thoughts_tokens) or None
    thinking_or_none = thoughts_tokens or None
    if finish_reason == "MAX_TOKENS":
        message = (
            "Gemini returned no text: the output budget was exhausted "
            f"(finish_reason=MAX_TOKENS, max_output_tokens={max_output_tokens}, "
            f"thoughts_tokens={thoughts_tokens}); non-retryable with unchanged parameters"
        )
        return OutputTokenExhaustedError(
            message,
            detail=FailureDetail(
                error_class="OutputTokenExhaustedError",
                message=message,
                provider_status="MAX_TOKENS",
                finish_reason="MAX_TOKENS",
                prompt_tokens=prompt_or_none,
                completion_tokens=completion_or_none,
                reasoning_tokens=thinking_or_none,
                retryable=False,
            ),
        )
    if finish_reason in _BLOCKING_FINISH_REASONS:
        message = f"Gemini blocked the response (finish_reason={finish_reason})"
        return PermanentProviderError(
            message,
            detail=FailureDetail(
                error_class="PermanentProviderError",
                message=message,
                provider_status=finish_reason,
                finish_reason=finish_reason,
                prompt_tokens=prompt_or_none,
                completion_tokens=completion_or_none,
                reasoning_tokens=thinking_or_none,
                retryable=False,
            ),
        )
    message = f"Gemini returned an empty response (finish_reason={finish_reason})"
    return EmptyResponseError(
        message,
        detail=FailureDetail(
            error_class="EmptyResponseError",
            message=message,
            provider_status=finish_reason,
            finish_reason=finish_reason,
            prompt_tokens=prompt_or_none,
            completion_tokens=completion_or_none,
            reasoning_tokens=thinking_or_none,
            retryable=False,
        ),
    )


def _response_from_sdk(
    response: Any,
    *,
    requested_model: str,
    max_output_tokens: int,
) -> ProviderResponse:
    finish_reason = _finish_reason_name(_finish_reason(response))
    prompt_tokens, candidates_tokens, thoughts_tokens = _usage_tokens(response)
    if prompt_tokens < 0 or candidates_tokens < 0 or thoughts_tokens < 0:
        raise PermanentProviderError(
            "Gemini returned negative token usage",
            detail=FailureDetail(
                error_class="PermanentProviderError",
                message="Gemini returned negative token usage",
            ),
        )

    text = _response_text(response)
    if text is None or not text.strip():
        raise _empty_response_error(
            finish_reason=finish_reason,
            max_output_tokens=max_output_tokens,
            prompt_tokens=prompt_tokens,
            candidates_tokens=candidates_tokens,
            thoughts_tokens=thoughts_tokens,
        )

    if getattr(response, "usage_metadata", None) is None:
        raise TransientProviderError(
            "Gemini response has no usage_metadata",
            detail=FailureDetail(
                error_class="TransientProviderError",
                message="Gemini response has no usage_metadata",
                retryable=True,
            ),
        )

    return ProviderResponse(
        text=text,
        prompt_tokens=prompt_tokens,
        completion_tokens=candidates_tokens + thoughts_tokens,
        reasoning_tokens=thoughts_tokens,
        model=getattr(response, "model_version", None) or requested_model,
    )


def _finish_reason(response: Any) -> Any:
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return None
    return getattr(candidates[0], "finish_reason", None)


def _finish_reason_name(reason: Any) -> str | None:
    if reason is None:
        return None
    return str(getattr(reason, "name", reason))


def _map_api_error(exc: errors.APIError) -> ProviderError:
    code = int(getattr(exc, "code", 0) or 0)
    status = str(getattr(exc, "status", "") or "")
    details = sanitize_error_text(_details_text(exc))
    compact = details.lower().replace("_", "").replace("-", "")
    is_quota = (
        code == 429
        or status.upper() == "RESOURCE_EXHAUSTED"
        or "quota" in details.lower()
        or "resourceexhausted" in compact
    )
    if is_quota:
        if any(marker.replace("_", "") in compact for marker in _DAILY_MARKERS):
            message = f"Gemini daily quota exhausted: {details}"
            return DailyQuotaError(
                message,
                detail=FailureDetail(
                    error_class="DailyQuotaError",
                    message=message,
                    http_status=code,
                    provider_status=status or "RESOURCE_EXHAUSTED",
                    retryable=False,
                ),
            )
        message = f"Gemini rate limit: {details}"
        return RateLimitError(
            message,
            detail=FailureDetail(
                error_class="RateLimitError",
                message=message,
                http_status=code,
                provider_status=status or "RESOURCE_EXHAUSTED",
                retryable=False,
            ),
        )
    if code >= 500:
        message = f"Gemini server error ({code}): {details}"
        return TransientProviderError(
            message,
            detail=FailureDetail(
                error_class="TransientProviderError",
                message=message,
                http_status=code,
                provider_status=status or None,
                retryable=True,
            ),
        )
    message = f"Gemini API error ({code}/{status}): {details}"
    return PermanentProviderError(
        message,
        detail=FailureDetail(
            error_class="PermanentProviderError",
            message=message,
            http_status=code,
            provider_status=status or None,
            retryable=False,
        ),
    )


def _details_text(exc: errors.APIError) -> str:
    details = getattr(exc, "details", None)
    if details is None:
        return str(exc)
    try:
        return json.dumps(details, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(details)


__all__ = ["GeminiAdapter"]
