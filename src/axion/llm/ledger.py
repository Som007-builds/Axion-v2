"""SQLite cost ledger: every LLM attempt, cache hit, and training run is recorded.

The ledger is the single source of truth for cost reporting. It stores:

* ``llm_calls`` — one row per provider attempt, cache hit, or failed attempt,
  including the resolved ``tier`` and, for escalated calls, the ``parent_call_id``
  of the call or stage they escalated from.
* ``training_runs`` — one row per local or external training run, with a
  content hash of its data and an estimated cost (``0`` for local compute).

Schema changes are applied in place and are idempotent: opening an older
database adds the missing columns without touching existing rows.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Literal

GroupBy = Literal["stage", "model", "provider", "tier"]

_GROUP_COLUMNS: dict[GroupBy, str] = {
    "stage": "stage",
    "model": "model",
    "provider": "provider",
    "tier": "tier",
}

_CREATE_LLM_CALLS = """
CREATE TABLE IF NOT EXISTS llm_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    run_id TEXT,
    stage TEXT NOT NULL,
    tier TEXT,
    provider TEXT,
    model TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    reasoning_tokens INTEGER,
    usd TEXT,
    latency_ms REAL,
    cache_hit INTEGER NOT NULL DEFAULT 0 CHECK (cache_hit IN (0, 1)),
    paper_id TEXT,
    parent_call_id INTEGER,
    error TEXT
)
"""

_CREATE_TRAINING_RUNS = """
CREATE TABLE IF NOT EXISTS training_runs (
    run_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    model TEXT NOT NULL,
    data_hash TEXT NOT NULL,
    hardware TEXT NOT NULL,
    duration_s REAL NOT NULL CHECK (duration_s >= 0),
    estimated_usd TEXT NOT NULL
)
"""

# Columns added after the first ledger release. Each entry is (column, DDL type).
_LLM_CALL_MIGRATIONS: tuple[tuple[str, str], ...] = (
    ("tier", "TEXT"),
    ("parent_call_id", "INTEGER"),
    ("reasoning_tokens", "INTEGER"),
)


@dataclass(frozen=True)
class LedgerEntry:
    stage: str
    provider: str | None
    model: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    reasoning_tokens: int | None
    usd: Decimal | None
    latency_ms: float | None
    cache_hit: bool = False
    run_id: str | None = None
    paper_id: str | None = None
    error: str | None = None
    ts: str | None = None
    tier: str | None = None
    parent_call_id: int | None = None


@dataclass(frozen=True)
class TrainingRun:
    """One training run, local or external.

    ``estimated_usd`` is ``0`` for local compute. It is only non-zero when a
    real external cost was incurred, and it is an estimate, not an invoice.
    """

    run_id: str
    model: str
    data_hash: str
    hardware: str
    duration_s: float = 0.0
    estimated_usd: Decimal = Decimal("0")
    ts: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("run_id", "model", "data_hash", "hardware"):
            if not str(getattr(self, field_name)).strip():
                raise ValueError(f"training run {field_name} must not be empty")
        if self.duration_s < 0:
            raise ValueError("training run duration_s must be non-negative")
        if self.estimated_usd < 0:
            raise ValueError("training run estimated_usd must be non-negative")


@dataclass(frozen=True)
class CallRecord:
    """One ledger row, for run-level reporting and budget checks."""

    id: int
    ts: str
    stage: str
    provider: str | None
    model: str | None
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    usd: Decimal | None
    latency_ms: float | None
    cache_hit: bool
    paper_id: str | None
    error: str | None


@dataclass(frozen=True)
class LedgerRow:
    key: str
    calls: int
    cache_hits: int
    errors: int
    missing_price_calls: int
    escalated_calls: int
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int
    usd: Decimal

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "errors": self.errors,
            "missing_price_calls": self.missing_price_calls,
            "escalated_calls": self.escalated_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "reasoning_tokens": self.reasoning_tokens,
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
    total_escalated_calls: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_reasoning_tokens: int
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
                "escalated_calls": self.total_escalated_calls,
                "prompt_tokens": self.total_prompt_tokens,
                "completion_tokens": self.total_completion_tokens,
                "reasoning_tokens": self.total_reasoning_tokens,
                "usd": format(self.total_usd, "f"),
            },
        }


@dataclass
class _Bucket:
    calls: int = 0
    cache_hits: int = 0
    errors: int = 0
    missing_price_calls: int = 0
    escalated_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    reasoning_tokens: int = 0
    usd: Decimal = Decimal("0")


class SQLiteLedger:
    """Append-only ledger of LLM calls and training runs."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(_CREATE_LLM_CALLS)
            self._migrate_llm_calls(connection)
            connection.execute(_CREATE_TRAINING_RUNS)
            connection.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_stage ON llm_calls(stage)")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_llm_calls_model ON llm_calls(model)")
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_llm_calls_parent ON llm_calls(parent_call_id)"
            )

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _migrate_llm_calls(connection: sqlite3.Connection) -> None:
        existing = {str(row["name"]) for row in connection.execute("PRAGMA table_info(llm_calls)")}
        for column, ddl_type in _LLM_CALL_MIGRATIONS:
            if column not in existing:
                connection.execute(f"ALTER TABLE llm_calls ADD COLUMN {column} {ddl_type}")

    def record(self, entry: LedgerEntry) -> int:
        """Append one call attempt and return its ledger row id."""
        timestamp = entry.ts or datetime.now(UTC).isoformat()
        usd_text = None if entry.usd is None else format(entry.usd, "f")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO llm_calls (
                    ts, run_id, stage, tier, provider, model, prompt_tokens,
                    completion_tokens, reasoning_tokens, usd, latency_ms, cache_hit,
                    paper_id, parent_call_id, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    entry.run_id,
                    entry.stage,
                    entry.tier,
                    entry.provider,
                    entry.model,
                    entry.prompt_tokens,
                    entry.completion_tokens,
                    entry.reasoning_tokens,
                    usd_text,
                    entry.latency_ms,
                    int(entry.cache_hit),
                    entry.paper_id,
                    entry.parent_call_id,
                    entry.error,
                ),
            )
            return int(cursor.lastrowid or 0)

    def record_training_run(self, run: TrainingRun) -> None:
        """Insert or update one training run by ``run_id``."""
        timestamp = run.ts or datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO training_runs (
                    run_id, ts, model, data_hash, hardware, duration_s, estimated_usd
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    ts = excluded.ts,
                    model = excluded.model,
                    data_hash = excluded.data_hash,
                    hardware = excluded.hardware,
                    duration_s = excluded.duration_s,
                    estimated_usd = excluded.estimated_usd
                """,
                (
                    run.run_id,
                    timestamp,
                    run.model,
                    run.data_hash,
                    run.hardware,
                    run.duration_s,
                    format(run.estimated_usd, "f"),
                ),
            )

    def training_runs(self) -> tuple[TrainingRun, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT run_id, ts, model, data_hash, hardware, duration_s, estimated_usd
                FROM training_runs
                ORDER BY ts, run_id
                """
            ).fetchall()
        return tuple(
            TrainingRun(
                run_id=str(row["run_id"]),
                ts=str(row["ts"]),
                model=str(row["model"]),
                data_hash=str(row["data_hash"]),
                hardware=str(row["hardware"]),
                duration_s=float(row["duration_s"]),
                estimated_usd=Decimal(str(row["estimated_usd"])),
            )
            for row in rows
        )

    def total_training_usd(self) -> Decimal:
        return sum((run.estimated_usd for run in self.training_runs()), Decimal("0"))

    def calls_for_run(self, run_id: str) -> tuple[CallRecord, ...]:
        """Return every attempt recorded for one run, in insertion order."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, ts, stage, provider, model, prompt_tokens,
                       completion_tokens, reasoning_tokens, usd, latency_ms,
                       cache_hit, paper_id, error
                FROM llm_calls
                WHERE run_id = ?
                ORDER BY id
                """,
                (run_id,),
            ).fetchall()
        return tuple(
            CallRecord(
                id=int(row["id"]),
                ts=str(row["ts"]),
                stage=str(row["stage"]),
                provider=None if row["provider"] is None else str(row["provider"]),
                model=None if row["model"] is None else str(row["model"]),
                prompt_tokens=int(row["prompt_tokens"] or 0),
                completion_tokens=int(row["completion_tokens"] or 0),
                reasoning_tokens=int(row["reasoning_tokens"] or 0),
                usd=None if row["usd"] is None else Decimal(str(row["usd"])),
                latency_ms=None if row["latency_ms"] is None else float(row["latency_ms"]),
                cache_hit=bool(row["cache_hit"]),
                paper_id=None if row["paper_id"] is None else str(row["paper_id"]),
                error=None if row["error"] is None else str(row["error"]),
            )
            for row in rows
        )

    def run_usd(self, run_id: str) -> Decimal:
        """Total list-price cost recorded for one run."""
        return sum(
            (call.usd for call in self.calls_for_run(run_id) if call.usd is not None),
            Decimal("0"),
        )

    def report(self, group_by: GroupBy = "stage") -> LedgerReport:
        try:
            column = _GROUP_COLUMNS[group_by]
        except KeyError as exc:
            raise ValueError(f"cannot group by {group_by!r}") from exc

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT {column} AS group_key, prompt_tokens, completion_tokens,
                       reasoning_tokens, usd, cache_hit, parent_call_id, error
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
            if row["parent_call_id"] is not None:
                bucket.escalated_calls += 1
            bucket.prompt_tokens += int(row["prompt_tokens"] or 0)
            bucket.completion_tokens += int(row["completion_tokens"] or 0)
            bucket.reasoning_tokens += int(row["reasoning_tokens"] or 0)
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
                escalated_calls=bucket.escalated_calls,
                prompt_tokens=bucket.prompt_tokens,
                completion_tokens=bucket.completion_tokens,
                reasoning_tokens=bucket.reasoning_tokens,
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
            total_escalated_calls=sum(row.escalated_calls for row in report_rows),
            total_prompt_tokens=sum(row.prompt_tokens for row in report_rows),
            total_completion_tokens=sum(row.completion_tokens for row in report_rows),
            total_reasoning_tokens=sum(row.reasoning_tokens for row in report_rows),
            total_usd=sum((row.usd for row in report_rows), Decimal("0")),
        )
