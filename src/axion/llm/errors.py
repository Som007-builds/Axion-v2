"""Error types and classification for LLM provider calls.

Failures carry a :class:`FailureDetail` so the ledger, the run's
``failures.jsonl``, and the run report can record *why* a call failed instead
of only the wrapping message. Every message passes through
:func:`sanitize_error_text`, which redacts credential-shaped strings; no API
key may reach a log, a ledger row, or a committed report.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

RATE_LIMIT_MARKERS = (
    "rate_limit",
    "rate limit",
    "ratelimit",
    "429",
    "too many requests",
    "quota",
    "resource_exhausted",
)

TRANSIENT_MARKERS = (
    "500",
    "502",
    "503",
    "504",
    "unavailable",
    "overloaded",
    "internal error",
    "internal server",
    "timeout",
    "timed out",
    "connection reset",
    "connection aborted",
    "connection error",
    "server disconnected",
    "remote protocol error",
    "service unavailable",
    "try again later",
    # TLS/socket read failures seen from the Gemini SDK (httpx ReadError).
    "readerror",
    "ssl",
    "bad record mac",
)

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"\bgsk_[A-Za-z0-9_\-]{16,}"),
    re.compile(r"(?i)\bbearer\s+\S+"),
    re.compile(r"(?i)\b(?:api[_-]?key|apikey|access[_-]?token|authorization)\b\s*[=:]?\s*\S+"),
    re.compile(r"(?i)\bkey=\S+"),
)


def sanitize_error_text(text: str, *, limit: int = 500) -> str:
    """Collapse whitespace, redact credential-shaped strings, and truncate."""
    cleaned = " ".join(str(text).split())
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    return cleaned[:limit]


@dataclass(frozen=True)
class FailureDetail:
    """The root cause of one provider failure, safe to persist and report."""

    error_class: str
    message: str
    http_status: int | None = None
    provider_status: str | None = None
    finish_reason: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    reasoning_tokens: int | None = None
    retryable: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "error_class": self.error_class,
            "message": self.message,
            "http_status": self.http_status,
            "provider_status": self.provider_status,
            "finish_reason": self.finish_reason,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "retryable": self.retryable,
        }


class LLMError(Exception):
    """Base class for all LLM-layer errors."""


class ConfigurationError(LLMError):
    """The client is missing required configuration."""


class ProviderNotConfiguredError(ConfigurationError):
    """A provider named in the chain is not registered."""


class ProviderError(LLMError):
    """Base class for errors raised by a provider."""

    def __init__(self, message: str, *, detail: FailureDetail | None = None) -> None:
        super().__init__(message)
        self.detail = detail


class RateLimitError(ProviderError):
    """The provider asked us to slow down.

    Not retried by the client: a 429 or ``RESOURCE_EXHAUSTED`` means the
    request should not be repeated immediately, and every retry spends quota.
    """


class DailyQuotaError(RateLimitError):
    """The provider's daily quota is exhausted; do not retry before reset.

    This is a :class:`RateLimitError` so existing rate-limit handling sees it,
    but the client deliberately does not retry it: a tight retry loop cannot
    succeed before the next quota window.
    """


class TransientProviderError(ProviderError):
    """A temporary provider/server failure worth exactly one retry."""


class PermanentProviderError(ProviderError):
    """A failure that will not fix itself (bad key, dead model, bad request)."""


class EmptyResponseError(PermanentProviderError):
    """The provider returned no text without a known token-exhaustion cause.

    Deterministic enough that retrying the same request would only spend
    quota, so it is not retryable.
    """


class OutputTokenExhaustedError(PermanentProviderError):
    """No text because thinking plus answer used the whole output budget.

    Non-retryable **with unchanged parameters**: the fix is a larger
    ``max_output_tokens`` or a lower thinking level, not another call.
    """


class AllProvidersFailedError(LLMError):
    """Every provider in the chain failed or was unavailable.

    ``detail`` is the last provider failure's root cause and ``attempts`` is
    the number of provider requests actually made, so callers never have to
    guess from the wrapper message.
    """

    def __init__(
        self,
        message: str,
        *,
        attempts: int = 0,
        detail: FailureDetail | None = None,
    ) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.detail = detail


class StructuredOutputError(LLMError):
    """The model response could not be validated against the requested schema."""


def classify_error(exc: Exception) -> ProviderError:
    """Map an arbitrary provider exception onto the retry taxonomy.

    Typed errors pass through unchanged. Untyped SDK exceptions are classified
    by message, mirroring the resilient router in V1.
    """
    if isinstance(
        exc, DailyQuotaError | RateLimitError | TransientProviderError | PermanentProviderError
    ):
        return exc

    message = str(exc).lower()
    if any(marker in message for marker in RATE_LIMIT_MARKERS):
        return RateLimitError(str(exc))
    if any(marker in message for marker in TRANSIENT_MARKERS):
        return TransientProviderError(str(exc))
    return PermanentProviderError(str(exc))


def failure_detail(exc: BaseException) -> FailureDetail:
    """Return the structured root cause for an exception, classifying if needed."""
    if isinstance(exc, ProviderError) and exc.detail is not None:
        return exc.detail
    classified = classify_error(exc if isinstance(exc, Exception) else Exception(str(exc)))
    message = sanitize_error_text(str(classified))
    return FailureDetail(
        error_class=type(classified).__name__,
        message=message,
        retryable=isinstance(classified, TransientProviderError),
    )


__all__ = [
    "AllProvidersFailedError",
    "ConfigurationError",
    "DailyQuotaError",
    "EmptyResponseError",
    "FailureDetail",
    "LLMError",
    "OutputTokenExhaustedError",
    "PermanentProviderError",
    "ProviderError",
    "ProviderNotConfiguredError",
    "RateLimitError",
    "StructuredOutputError",
    "TransientProviderError",
    "classify_error",
    "failure_detail",
    "sanitize_error_text",
]
