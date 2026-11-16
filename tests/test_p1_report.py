"""The P1 baseline report must never invent values when inputs are absent."""

from __future__ import annotations

from pathlib import Path

from scripts.build_p1_report import NOT_MEASURED, build_report

from axion.eval.audit import AUDIT_COLUMNS


def _write_audit(path: Path, labels: list[str], *, paper_ids: list[str] | None = None) -> None:
    import csv

    papers = paper_ids or ["PMC0", "PMC1"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(AUDIT_COLUMNS))
        writer.writeheader()
        for index, label in enumerate(labels):
            paper = papers[index % len(papers)]
            writer.writerow(
                {
                    "claim_id": f"{paper}:{index}",
                    "paper_id": paper,
                    "paper_title": "A paper",
                    "section": "Abstract",
                    "claim_text": "Drug X reduced Y.",
                    "evidence_span": "Drug X reduced Y.",
                    "context_before": "",
                    "context_after": "",
                    "label": label,
                    "note": "" if label == "CORRECT" else "not a claim",
                    "labeler": "owner",
                    "date": "2026-11-15",
                    "rubric_version": "v2",
                    "split": "dev",
                    "relabel_label": "",
                }
            )


def test_report_marks_missing_inputs_as_not_measured(tmp_path: Path) -> None:
    out = tmp_path / "P1-baseline.md"
    text = build_report(
        manifest_path=tmp_path / "missing-manifest.json",
        audit_path=tmp_path / "missing-audit.csv",
        ledger_path=tmp_path / "missing-ledger.sqlite3",
        out_path=out,
        run_report_path=tmp_path / "missing-run.json",
    )
    assert out.read_text(encoding="utf-8") == text
    assert text.count(NOT_MEASURED) >= 5
    assert "Claim extraction precision" in text
    assert "0.0%" not in text
    assert "Total USD: 0" not in text
    assert "**Open**" in text


def test_report_records_the_gate_decision_from_labels(tmp_path: Path) -> None:
    audit = tmp_path / "audit.csv"
    _write_audit(
        audit,
        ["CORRECT"] * 9 + ["NOT_A_CLAIM"],
        paper_ids=["PMC1", "PMC2"],
    )
    out = tmp_path / "P1-baseline.md"

    text = build_report(
        manifest_path=tmp_path / "missing-manifest.json",
        audit_path=audit,
        ledger_path=None,
        out_path=out,
        run_report_path=tmp_path / "missing-run.json",
    )

    assert "**PASS**" in text
    assert "90.0%" in text
    assert "Agreement: **pending**" in text
    assert "0 relabel rows filled" in text


def test_report_uses_independent_overlap_and_flags_degenerate_kappa(tmp_path: Path) -> None:
    import csv

    audit = tmp_path / "audit.csv"
    _write_audit(audit, ["CORRECT"] * 10, paper_ids=["PMC1", "PMC2"])
    with audit.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    overlap = tmp_path / "overlap.csv"
    with overlap.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(AUDIT_COLUMNS))
        writer.writeheader()
        writer.writerows(rows[:2])

    out = tmp_path / "P1-baseline.md"
    text = build_report(
        manifest_path=tmp_path / "missing-manifest.json",
        audit_path=audit,
        ledger_path=None,
        out_path=out,
        run_report_path=tmp_path / "missing-run.json",
        overlap_path=overlap,
    )

    assert "Independent agreement: raw 100.0%" in text
    assert "not estimable (degenerate)" in text
    assert "does not validate the `NOT_A_CLAIM` calls" in text
