"""The P1 baseline report must never invent values when inputs are absent."""

from __future__ import annotations

from pathlib import Path

from scripts.build_p1_report import NOT_MEASURED, build_report


def test_report_marks_missing_inputs_as_not_measured(tmp_path: Path) -> None:
    out = tmp_path / "P1-baseline.md"
    text = build_report(
        manifest_path=tmp_path / "missing-manifest.json",
        audit_path=tmp_path / "missing-audit.csv",
        ledger_path=tmp_path / "missing-ledger.sqlite3",
        out_path=out,
    )
    assert out.read_text(encoding="utf-8") == text
    assert text.count(NOT_MEASURED) >= 5
    assert "Claim extraction precision" in text
    assert "0.0%" not in text
    assert "Total USD: 0" not in text
