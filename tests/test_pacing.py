"""Tests for free-tier pacing and Pacific-day accounting."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from axion.config.settings import DEFAULT_RATE_LIMITS_PATH
from axion.llm.errors import DailyQuotaError
from axion.llm.pacing import (
    RateLimit,
    RequestPacer,
    load_rate_limits,
    next_midnight_pacific,
    pacific_date,
    requests_by_pacific_day,
    requests_on_date,
)


def test_packaged_limits_match_owner_free_tier() -> None:
    table = load_rate_limits(DEFAULT_RATE_LIMITS_PATH)

    large = table.require("gemini-3.8-flash")
    assert (large.rpm, large.tpm, large.rpd) == (5, 250_000, 20)
    assert large.daily_cap == 18
    assert large.min_interval_s == 13.0

    small = table.require("gemini-3.5-flash-lite")
    assert (small.rpm, small.tpm, small.rpd) == (15, 250_000, 500)
    # Owner cap for the P1 baseline model: 450/day with a 50-request margin.
    assert small.daily_cap == 450


def test_pacific_date_crosses_utc_boundary() -> None:
    assert pacific_date("2026-11-15T07:59:00+00:00").isoformat() == "2026-11-14"
    assert pacific_date("2026-11-15T08:00:00+00:00").isoformat() == "2026-11-15"


def test_requests_on_date_counts_attempts_and_can_filter_model() -> None:
    calls = [
        SimpleNamespace(ts="2026-11-15T08:00:00+00:00", model="m1"),
        SimpleNamespace(ts="2026-11-15T09:00:00+00:00", model="m2"),
        SimpleNamespace(ts="2026-11-16T08:00:00+00:00", model="m1"),
    ]

    assert requests_on_date(calls, pacific_date("2026-11-15T12:00:00+00:00")) == 2
    assert (
        requests_on_date(
            calls,
            pacific_date("2026-11-15T12:00:00+00:00"),
            model="m1",
        )
        == 1
    )
    assert requests_by_pacific_day(calls) == {"2026-11-15": 2, "2026-11-16": 1}


def test_pacer_stops_at_daily_cap_without_sleeping_until_tomorrow() -> None:
    now = datetime(2026, 11, 15, 18, 0, tzinfo=UTC)
    pacer = RequestPacer(
        RateLimit(rpm=5, tpm=250_000, rpd=2, daily_margin=0),
        requests_today=2,
        now=lambda: now,
        sleep=lambda _: None,
    )

    with pytest.raises(DailyQuotaError, match="daily request cap"):
        pacer.reserve()


def test_pacer_enforces_minimum_interval() -> None:
    moments = [datetime(2026, 11, 15, 18, 0, tzinfo=UTC)]
    slept: list[float] = []

    def now() -> datetime:
        return moments[-1]

    def sleep(seconds: float) -> None:
        slept.append(seconds)
        moments.append(moments[-1] + timedelta(seconds=seconds))

    pacer = RequestPacer(
        RateLimit(rpm=5, tpm=250_000, rpd=20),
        last_request_at=moments[0],
        now=now,
        sleep=sleep,
    )
    pacer.reserve()

    assert slept == [13.0]
    assert pacer.requests_today == 1


def test_from_calls_seeds_today_count_and_last_time() -> None:
    now = datetime(2026, 11, 15, 18, 0, tzinfo=UTC)
    calls = [
        SimpleNamespace(ts="2026-11-15T08:00:00+00:00", model="m"),
        SimpleNamespace(ts="2026-11-15T17:00:00+00:00", model="m"),
        SimpleNamespace(ts="2026-11-14T10:00:00+00:00", model="m"),
    ]

    pacer = RequestPacer.from_calls(
        RateLimit(rpm=5, tpm=250_000, rpd=20),
        calls,
        now=lambda: now,
        sleep=lambda _: None,
    )

    assert pacer.requests_today == 2
    assert pacer.last_request_at == datetime(2026, 11, 15, 17, 0, tzinfo=UTC)


def test_next_midnight_is_pacific() -> None:
    value = next_midnight_pacific(datetime(2026, 11, 15, tzinfo=UTC).date())

    assert value.startswith("2026-11-16T00:00:00-08:00")
