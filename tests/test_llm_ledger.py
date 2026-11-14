"""Tests for the SQLite cost ledger and its report CLI."""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest

from axion.llm.cli import main
from axion.llm.ledger import LedgerEntry, SQLiteLedger, TrainingRun


def _entry(
    *,
    stage: str = "extract",
    provider: str | None = "primary",
    model: str | None = "small/model",
    prompt_tokens: int | None = 100,
    completion_tokens: int | None = 50,
    usd: Decimal | None = Decimal("0.000125"),
    cache_hit: bool = False,
    error: str | None = None,
    tier: str | None = "small",
    parent_call_id: int | None = None,
) -> LedgerEntry:
    return LedgerEntry(
        stage=stage,
        provider=provider,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        usd=usd,
        latency_ms=12.5,
        cache_hit=cache_hit,
        run_id="run-1",
        paper_id="PMC1",
        error=error,
        tier=tier,
        parent_call_id=parent_call_id,
    )


def _raw_rows(path: Path) -> list[sqlite3.Row]:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        return connection.execute("SELECT * FROM llm_calls ORDER BY id").fetchall()
    finally:
        connection.close()


def _columns(path: Path, table: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def test_report_groups_and_totals(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "ledger.sqlite3")
    ledger.record(_entry())
    ledger.record(_entry(stage="extract"))
    ledger.record(_entry(stage="link", model="large/model", usd=Decimal("0.5")))
    ledger.record(
        _entry(stage="link", model="large/model", cache_hit=True, usd=Decimal("0"), prompt_tokens=0)
    )
    ledger.record(_entry(stage="link", model="large/model", usd=None))
    ledger.record(_entry(stage="link", model="large/model", usd=None, error="boom", tier=None))

    by_stage = ledger.report("stage")
    assert [row.key for row in by_stage.rows] == ["extract", "link"]
    assert by_stage.total_calls == 6
    assert by_stage.total_cache_hits == 1
    assert by_stage.total_errors == 1
    assert by_stage.total_missing_price_calls == 1
    assert by_stage.total_usd == Decimal("0.500250")

    by_model = ledger.report("model")
    assert [row.key for row in by_model.rows] == ["large/model", "small/model"]

    by_provider = ledger.report("provider")
    assert by_provider.rows[0].key == "primary"

    by_tier = ledger.report("tier")
    assert [row.key for row in by_tier.rows] == ["small", "unknown"]


def test_report_to_dict_is_json_ready(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "ledger.sqlite3")
    ledger.record(_entry())

    payload = ledger.report("stage").to_dict()

    assert payload["group_by"] == "stage"
    assert payload["total"]["calls"] == 1
    assert payload["total"]["usd"] == "0.000125"
    assert payload["total"]["escalated_calls"] == 0
    assert json.dumps(payload)


def test_tier_and_escalation_link_are_recorded(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = SQLiteLedger(path)

    parent_id = ledger.record(_entry(stage="teacher_label", tier="small"))
    child_id = ledger.record(
        _entry(stage="large_llm", tier="large", parent_call_id=parent_id, usd=Decimal("0.25"))
    )

    rows = _raw_rows(path)
    assert [row["id"] for row in rows] == [parent_id, child_id]
    assert rows[0]["tier"] == "small"
    assert rows[0]["parent_call_id"] is None
    assert rows[1]["tier"] == "large"
    assert rows[1]["parent_call_id"] == parent_id

    report = ledger.report("tier")
    assert report.total_escalated_calls == 1
    assert report.total_calls == 2
    assert [row.key for row in report.rows] == ["large", "small"]


def test_legacy_schema_is_migrated_idempotently(tmp_path: Path) -> None:
    path = tmp_path / "legacy.sqlite3"
    connection = sqlite3.connect(path)
    connection.execute(
        """
        CREATE TABLE llm_calls (
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
            cache_hit INTEGER NOT NULL DEFAULT 0,
            paper_id TEXT,
            error TEXT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO llm_calls (
            ts, run_id, stage, provider, model, prompt_tokens, completion_tokens,
            usd, latency_ms, cache_hit, paper_id
        ) VALUES ('2026-01-01T00:00:00+00:00', 'old-run', 'extract', 'p', 'm',
                  10, 5, '0.000010', 12.0, 0, 'PMC1')
        """
    )
    connection.commit()
    connection.close()

    ledger = SQLiteLedger(path)
    ledger = SQLiteLedger(path)  # second open must not raise

    assert {"tier", "parent_call_id"} <= _columns(path, "llm_calls")
    assert {"run_id", "model", "data_hash", "hardware", "duration_s"} <= _columns(
        path, "training_runs"
    )

    rows = _raw_rows(path)
    assert len(rows) == 1
    assert rows[0]["stage"] == "extract"
    assert rows[0]["usd"] == "0.000010"
    assert rows[0]["tier"] is None
    assert rows[0]["parent_call_id"] is None

    # Migrated rows remain reportable.
    assert ledger.report("stage").total_usd == Decimal("0.000010")


def test_training_runs_default_to_zero_local_cost(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "ledger.sqlite3")

    ledger.record_training_run(
        TrainingRun(
            run_id="train-local-1",
            model="mini-encoder",
            data_hash="sha256:abc123",
            hardware="local-cpu",
            duration_s=42.5,
        )
    )
    ledger.record_training_run(
        TrainingRun(
            run_id="train-external-1",
            model="hosted-trainer",
            data_hash="sha256:def456",
            hardware="vendor-gpu",
            duration_s=3_600.0,
            estimated_usd=Decimal("1.250000"),
        )
    )

    runs = ledger.training_runs()
    assert [run.run_id for run in runs] == ["train-local-1", "train-external-1"]
    assert runs[0].estimated_usd == Decimal("0")
    assert ledger.total_training_usd() == Decimal("1.250000")


def test_training_run_upsert_is_idempotent(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "ledger.sqlite3")

    for duration in (10.0, 20.0):
        ledger.record_training_run(
            TrainingRun(
                run_id="train-1",
                model="mini-encoder",
                data_hash="sha256:abc123",
                hardware="local-cpu",
                duration_s=duration,
            )
        )

    runs = ledger.training_runs()
    assert len(runs) == 1
    assert runs[0].duration_s == 20.0


def test_training_run_rejects_invalid_values() -> None:
    with pytest.raises(ValueError):
        TrainingRun(run_id="", model="m", data_hash="h", hardware="local")
    with pytest.raises(ValueError):
        TrainingRun(run_id="r", model="m", data_hash="h", hardware="local", duration_s=-1.0)


def test_cli_prints_table(tmp_path: Path, capsys) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = SQLiteLedger(path)
    ledger.record(_entry())

    code = main(["--db", str(path), "--group-by", "model"])
    output = capsys.readouterr().out

    assert code == 0
    assert "small/model" in output
    assert "TOTAL" in output
    assert "0.000125" in output


def test_cli_prints_escalations(tmp_path: Path, capsys) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = SQLiteLedger(path)
    parent_id = ledger.record(_entry(stage="student", tier="small"))
    ledger.record(_entry(stage="small_llm", tier="large", parent_call_id=parent_id))

    code = main(["--db", str(path), "--group-by", "tier"])
    output = capsys.readouterr().out

    assert code == 0
    assert "escal" in output


def test_cli_prints_training_runs(tmp_path: Path, capsys) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = SQLiteLedger(path)
    ledger.record_training_run(
        TrainingRun(
            run_id="train-1",
            model="mini-encoder",
            data_hash="sha256:abc123",
            hardware="local-cpu",
            duration_s=12.0,
        )
    )

    code = main(["--db", str(path), "--training-runs"])
    output = capsys.readouterr().out

    assert code == 0
    assert "train-1" in output
    assert "TOTAL" in output
    assert "0.000000" in output


def test_cli_prints_json(tmp_path: Path, capsys) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = SQLiteLedger(path)
    ledger.record(_entry())

    code = main(["--db", str(path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["total"]["calls"] == 1


def test_cli_training_runs_json(tmp_path: Path, capsys) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = SQLiteLedger(path)
    ledger.record_training_run(
        TrainingRun(
            run_id="train-1",
            model="mini-encoder",
            data_hash="sha256:abc123",
            hardware="local-cpu",
        )
    )

    code = main(["--db", str(path), "--training-runs", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["training_runs"][0]["run_id"] == "train-1"
    assert payload["total_estimated_usd"] == "0"


def test_cli_missing_ledger_returns_error(tmp_path: Path, capsys) -> None:
    code = main(["--db", str(tmp_path / "missing.sqlite3")])
    err = capsys.readouterr().err

    assert code == 1
    assert "ledger not found" in err
