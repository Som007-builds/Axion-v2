"""SQLite cost ledger: every LLM attempt and every cache hit is recorded."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

GroupBy = Literal["stage", "model", "provider"]

_GROUP_COLUMNS: dict[GroupBy, str] = {
    "stage": "stage",
    "model": "model",
    "provider": "provider",
}

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    run_id TEXT,
    stage TEXT NOT NULL,
    provider TEXT,
    model TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    usd TEXT,
    latency_ms REAL,
    cache_hit INTEGER NOT NULL DEFAULT 0 CHECK (cache_hit IN (0, 1)),
    paper_id TEXT,
    error TEXT
)
"""


@dataclass(frozen=True)
class LedgerEntry:
    stage: str
    provider: str | None
    model: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    usd: Decimal | None
    latency_ms: float | None
    cache_hit: bool = False
    run_id: str | None = None
    paper_id: str | None = None
    error: str | None = None
    ts: str | None = None


@dataclass(frozen=True)
class LedgerRow:
    key: str
    calls: int
    cache_hits: int
    errors: int
    missing_price_calls: int
    prompt_tokens: int
    completion_tokens: int
    usd: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "errors": self.errors,
            "missing_price_calls": self.missing_price_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "usd": format(self.usd, "f"),
        }


@dataclass(frozen=True)
class LedgerReport:
    group_by: GroupBy
    rows: tuple[LedgerRow, ...]
    total_calls: int
    total_cache_hits: int
    total_errors: int
    total_missing_price_calls: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_usd: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "group_by": self.group_by,
            "rows": [row.to_dict() for row in self.rows],
            "total": {
                "calls": self.total_calls,
                "cache_hits": self.total_cache_hits,
                "errors": self.total_errors,
                "missing_price_calls": self.total_missing_price_calls,
                "prompt_tokens": self.total_prompt_tokens,
                "completion_tokens": self.total_completion_tokens,
                "usd": format(self.total_usd, "f"),
            },
        }


@dataclass
class _Bucket:
    calls: int = 0
    cache_hits: int = 0
    errors: int = 0
    missing_price_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usd: Decimal = Decimal("0")


class SQLiteLedger:
    """Append-only ledger of LLM calls."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(_CREATE_TABLE)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_stage ON llm_calls(stage)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_model ON llm_calls(model)")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def record(self, entry: LedgerEntry) -> int:
        timestamp = entry.ts or datetime.now(UTC).isoformat()
        usd_text = None if entry.usd is None else format(entry.usd, "f")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO llm_calls (
                    ts, run_id, stage, provider, model, prompt_tokens,
                    completion_tokens, usd, latency_ms, cache_hit, paper_id, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    entry.run_id,
                    entry.stage,
                    entry.provider,
                    entry.model,
                    entry.prompt_tokens,
                    entry.completion_tokens,
                    usd_text,
                    entry.latency_ms,
                    int(entry.cache_hit),
                    entry.paper_id,
                    entry.error,
                ),
            )
            return int(cursor.lastrowid or 0)

    def report(self, group_by: GroupBy = "stage") -> LedgerReport:
        try:
            column = _GROUP_COLUMNS[group_by]
        except KeyError as exc:
            raise ValueError(f"cannot group by {group_by!r}") from exc

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {column} AS group_key, prompt_tokens, completion_tokens,
                       usd, cache_hit, error
                FROM llm_calls
                """
            ).fetchall()

        buckets: dict[str, _Bucket] = {}
        for row in rows:
            raw_key = row["group_key"]
            key = "unknown" if raw_key is None else str(raw_key)
            bucket = buckets.setdefault(key, _Bucket())
            bucket.calls += 1
            if bool(row["cache_hit"]):
                bucket.cache_hits += 1
            if row["error"] is not None:
                bucket.errors += 1
            bucket.prompt_tokens += int(row["prompt_tokens"] or 0)
            bucket.completion_tokens += int(row["completion_tokens"] or 0)
            usd_raw = row["usd"]
            if usd_raw is None:
                # Failed attempts have no cost by definition; only a successful
                # call with no price is a "missing price" data gap.
                if row["error"] is None:
                    bucket.missing_price_calls += 1
            else:
                bucket.usd += Decimal(str(usd_raw))

        report_rows = tuple(
            LedgerRow(
                key=key,
                calls=bucket.calls,
                cache_hits=bucket.cache_hits,
                errors=bucket.errors,
                missing_price_calls=bucket.missing_price_calls,
                prompt_tokens=bucket.prompt_tokens,
                completion_tokens=bucket.completion_tokens,
                usd=bucket.usd,
            )
            for key, bucket in sorted(buckets.items())
        )
        return LedgerReport(
            group_by=group_by,
            rows=report_rows,
            total_calls=sum(row.calls for row in report_rows),
            total_cache_hits=sum(row.cache_hits for row in report_rows),
            total_errors=sum(row.errors for row in report_rows),
            total_missing_price_calls=sum(row.missing_price_calls for row in report_rows),
            total_prompt_tokens=sum(row.prompt_tokens for row in report_rows),
            total_completion_tokens=sum(row.completion_tokens for row in report_rows),
            total_usd=sum((row.usd for row in report_rows), Decimal("0")),
        )
