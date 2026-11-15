"""Free-tier request pacing and Pacific-day quota accounting."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, date, datetime, timedelta
from datetime import time as datetime_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from axion.llm.errors import ConfigurationError, DailyQuotaError

PACIFIC = ZoneInfo("America/Los_Angeles")


class PacingConfigError(ConfigurationError):
    """The rate-limit file is missing or invalid."""


class RateLimit(BaseModel):
    """One model's free-tier limits."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rpm: int = Field(ge=1)
    tpm: int = Field(ge=1)
    rpd: int = Field(ge=1)
    daily_margin: int = Field(default=0, ge=0)

    @property
    def daily_cap(self) -> int:
        return max(1, self.rpd - self.daily_margin)

    @property
    def min_interval_s(self) -> float:
        """Conservative gap between request starts, plus one second of slack."""
        return max(1.0, 60.0 / self.rpm + 1.0)


class RateLimitTable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    checked: str
    source: str
    models: dict[str, RateLimit] = Field(default_factory=dict)

    def require(self, model: str) -> RateLimit:
        try:
            return self.models[model]
        except KeyError as exc:
            raise PacingConfigError(
                f"no free-tier pacing entry for model {model!r}; refusing to call it"
            ) from exc


def load_rate_limits(path: Path) -> RateLimitTable:
    try:
        raw: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PacingConfigError(f"cannot read rate-limit file {path}") from exc
    if not isinstance(raw, dict):
        raise PacingConfigError(f"rate-limit file must contain a mapping: {path}")
    try:
        return RateLimitTable.model_validate(raw)
    except ValidationError as exc:
        raise PacingConfigError(f"invalid rate-limit file {path}: {exc}") from exc


def pacific_date(timestamp: str | datetime) -> date:
    """Convert an ISO timestamp or aware datetime to its Pacific calendar day."""
    moment = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(PACIFIC).date()


def requests_on_date(
    calls: Iterable[Any],
    day: date,
    *,
    model: str | None = None,
) -> int:
    """Count attempts recorded on one Pacific day, including failed attempts."""
    count = 0
    for call in calls:
        if model is not None and getattr(call, "model", None) != model:
            continue
        try:
            if pacific_date(str(call.ts)) == day:
                count += 1
        except (TypeError, ValueError):
            continue
    return count


def last_request_at(calls: Iterable[Any]) -> datetime | None:
    latest: datetime | None = None
    for call in calls:
        try:
            moment = datetime.fromisoformat(str(call.ts))
        except (TypeError, ValueError):
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=UTC)
        if latest is None or moment > latest:
            latest = moment
    return latest


def requests_by_pacific_day(calls: Iterable[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for call in calls:
        try:
            day = pacific_date(str(call.ts)).isoformat()
        except (TypeError, ValueError):
            continue
        counts[day] = counts.get(day, 0) + 1
    return dict(sorted(counts.items()))


def next_midnight_pacific(day: date) -> str:
    """ISO timestamp of the next Pacific midnight, for the resume message."""
    moment = datetime.combine(day + timedelta(days=1), datetime_time.min, tzinfo=PACIFIC)
    return moment.isoformat()


def midnight_pacific_utc(day: date) -> str:
    moment = datetime.combine(day + timedelta(days=1), datetime_time.min, tzinfo=PACIFIC)
    return moment.astimezone(UTC).isoformat()


class RequestPacer:
    """Persist-aware free-tier gate for one run and model.

    The pacer checks the day's recorded attempts before every call and waits
    ``min_interval_s`` between request starts. It deliberately stops (raises
    :class:`DailyQuotaError`) instead of sleeping until the next Pacific day.
    """

    def __init__(
        self,
        rate: RateLimit,
        *,
        requests_today: int = 0,
        last_request_at: datetime | None = None,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.rate = rate
        self.requests_today = requests_today
        self.last_request_at = last_request_at
        self._now = now or (lambda: datetime.now(UTC))
        self._sleep = sleep

    def reserve(self) -> None:
        """Reserve one request, waiting for RPM spacing; stop on daily cap."""
        if self.requests_today >= self.rate.daily_cap:
            raise DailyQuotaError(
                f"daily request cap reached for this model "
                f"({self.requests_today}/{self.rate.daily_cap}); "
                f"resume after {next_midnight_pacific(self._now().astimezone(PACIFIC).date())}"
            )
        if self.last_request_at is not None:
            elapsed = (self._now() - self.last_request_at).total_seconds()
            remaining = self.rate.min_interval_s - elapsed
            if remaining > 0:
                self._sleep(remaining)
        self.requests_today += 1
        self.last_request_at = self._now()

    @classmethod
    def from_calls(
        cls,
        rate: RateLimit,
        calls: Iterable[Any],
        *,
        now: Callable[[], datetime] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> RequestPacer:
        today = (now or (lambda: datetime.now(UTC)))().astimezone(PACIFIC).date()
        return cls(
            rate,
            requests_today=requests_on_date(calls, today),
            last_request_at=last_request_at(calls),
            now=now,
            sleep=sleep,
        )


def rate_limits_summary(table: RateLimitTable) -> Mapping[str, Any]:
    return {
        "version": table.version,
        "checked": table.checked,
        "source": table.source,
        "models": {name: model.model_dump() for name, model in table.models.items()},
    }


__all__ = [
    "PACIFIC",
    "PacingConfigError",
    "RateLimit",
    "RateLimitTable",
    "RequestPacer",
    "last_request_at",
    "load_rate_limits",
    "midnight_pacific_utc",
    "next_midnight_pacific",
    "pacific_date",
    "rate_limits_summary",
    "requests_by_pacific_day",
    "requests_on_date",
]
