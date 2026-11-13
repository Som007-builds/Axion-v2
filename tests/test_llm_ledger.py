"""Tests for the SQLite cost ledger and its report CLI."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from axion.llm.cli import main
from axion.llm.ledger import LedgerEntry, SQLiteLedger


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
    )


def test_report_groups_and_totals(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "ledger.sqlite3")
    ledger.record(_entry())
    ledger.record(_entry(stage="extract"))
    ledger.record(_entry(stage="link", model="large/model", usd=Decimal("0.5")))
    ledger.record(
        _entry(stage="link", model="large/model", cache_hit=True, usd=Decimal("0"), prompt_tokens=0)
    )
    ledger.record(_entry(stage="link", model="large/model", usd=None))
    ledger.record(_entry(stage="link", model="large/model", usd=None, error="boom"))

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


def test_report_to_dict_is_json_ready(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "ledger.sqlite3")
    ledger.record(_entry())

    payload = ledger.report("stage").to_dict()

    assert payload["group_by"] == "stage"
    assert payload["total"]["calls"] == 1
    assert payload["total"]["usd"] == "0.000125"
    assert json.dumps(payload)


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


def test_cli_prints_json(tmp_path: Path, capsys) -> None:
    path = tmp_path / "ledger.sqlite3"
    ledger = SQLiteLedger(path)
    ledger.record(_entry())

    code = main(["--db", str(path), "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["total"]["calls"] == 1


def test_cli_missing_ledger_returns_error(tmp_path: Path, capsys) -> None:
    code = main(["--db", str(tmp_path / "missing.sqlite3")])
    err = capsys.readouterr().err

    assert code == 1
    assert "ledger not found" in err
