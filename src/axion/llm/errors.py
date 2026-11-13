"""Error types and classification for LLM provider calls."""

from __future__ import annotations

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
    "service unavailable",
    "try again later",
)


class LLMError(Exception):
    """Base class for all LLM-layer errors."""


class ConfigurationError(LLMError):
    """The client is missing required configuration."""


class ProviderNotConfiguredError(ConfigurationError):
    """A provider named in the chain is not registered."""


class ProviderError(LLMError):
    """Base class for errors raised by a provider."""


class RateLimitError(ProviderError):
    """The provider asked us to slow down."""


class TransientProviderError(ProviderError):
    """A temporary provider/server failure worth retrying."""


class PermanentProviderError(ProviderError):
    """A failure that will not fix itself (bad key, dead model, bad request)."""


class AllProvidersFailedError(LLMError):
    """Every provider in the chain failed or was unavailable."""


class StructuredOutputError(LLMError):
    """The model response could not be validated against the requested schema."""


def classify_error(exc: Exception) -> ProviderError:
    """Map an arbitrary provider exception onto the retry taxonomy.

    Typed errors pass through unchanged. Untyped SDK exceptions are classified
    by message, mirroring the resilient router in V1.
    """
    if isinstance(exc, RateLimitError | TransientProviderError | PermanentProviderError):
        return exc

    message = str(exc).lower()
    if any(marker in message for marker in RATE_LIMIT_MARKERS):
        return RateLimitError(str(exc))
    if any(marker in message for marker in TRANSIENT_MARKERS):
        return TransientProviderError(str(exc))
    return PermanentProviderError(str(exc))
