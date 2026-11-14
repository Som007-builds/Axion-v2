"""Tests for the P1-11 audit export and metrics (no labels are invented)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from scripts.audit_metrics import main as metrics_main
from scripts.audit_sample import main as sample_main

from axion.eval.audit import (
    AUDIT_COLUMNS,
    LABELS,
    AuditError,
    ClaimRecord,
    assign_paper_splits,
    cohen_kappa,
    compute_metrics,
    corpus_snapshot_id,
    export_rows,
    load_claims,
    read_audit,
    render_markdown,
    sample_claims,
    wilson_interval,
    write_export,
)


def _claim(index: int, paper: str | None = None, text: str | None = None) -> ClaimRecord:
    return ClaimRecord(
        claim_id=f"PMC{index}:1",
        paper_id=paper or f"PMC{index}",
        claim_text=text or f"Drug X reduced Y by {index}%.",
        evidence_span=f"reduced Y by {index}%",
        section="Results",
        paper_title=f"Paper {paper or index}",
        context_before="",
        context_after="",
    )


def _write_jsonl(path: Path, claims: list[ClaimRecord]) -> None:
    path.write_text("\n".join(claim.model_dump_json() for claim in claims) + "\n", encoding="utf-8")


def _labelled_row(claim_id: str, label: str, relabel: str = "") -> dict[str, str]:
    row = {column: "" for column in AUDIT_COLUMNS}
    row.update(
        {
            "claim_id": claim_id,
            "paper_id": claim_id.split(":")[0],
            "section": "Results",
            "claim_text": "text",
            "evidence_span": "span",
            "label": label,
            "relabel_label": relabel,
        }
    )
    return row


def test_load_claims_rejects_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "claims.jsonl"
    claim = _claim(1)
    _write_jsonl(path, [claim, claim])
    with pytest.raises(AuditError, match="duplicate claim_id"):
        load_claims(path)


def test_load_claims_rejects_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "claims.jsonl"
    path.write_text('{"claim_id": "x"}\n', encoding="utf-8")
    with pytest.raises(AuditError, match="invalid claim"):
        load_claims(path)


def test_load_claims_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "claims.jsonl"
    path.write_text("\n\n", encoding="utf-8")
    with pytest.raises(AuditError, match="no claims found"):
        load_claims(path)


def test_sample_is_deterministic_sorted_and_subset() -> None:
    claims = [_claim(index) for index in range(1, 51)]
    first = sample_claims(claims, 10, seed=7)
    second = sample_claims(list(reversed(claims)), 10, seed=7)
    assert [claim.claim_id for claim in first] == [claim.claim_id for claim in second]
    assert [claim.claim_id for claim in first] == sorted(claim.claim_id for claim in first)
    assert len(first) == 10
    assert set(claim.claim_id for claim in first) <= {claim.claim_id for claim in claims}


def test_sample_size_guards() -> None:
    claims = [_claim(index) for index in range(1, 4)]
    with pytest.raises(AuditError, match="must be positive"):
        sample_claims(claims, 0)
    with pytest.raises(AuditError, match="exceeds"):
        sample_claims(claims, 4)


def test_snapshot_is_order_independent_and_content_sensitive() -> None:
    claims = [_claim(index) for index in range(1, 6)]
    assert corpus_snapshot_id(claims) == corpus_snapshot_id(list(reversed(claims)))
    changed = [_claim(1, text="A different claim."), *claims[1:]]
    assert corpus_snapshot_id(changed) != corpus_snapshot_id(claims)


def test_splits_are_by_paper_and_balanced() -> None:
    paper_ids = [f"PMC{index}" for index in range(1, 11)]
    splits = assign_paper_splits(paper_ids, seed=3)
    assert set(splits.values()) == {"dev", "test"}
    assert list(splits.values()).count("dev") == 5
    assert assign_paper_splits(paper_ids, seed=3) == splits


def test_export_keeps_paper_rows_together_with_blank_labels() -> None:
    claims = [_claim(index, paper=f"PMC{index % 5}") for index in range(1, 21)]
    rows = export_rows(claims, seed=11)
    assert all(row["label"] == "" and row["relabel_label"] == "" for row in rows)
    assert all(row["rubric_version"] == "v2" for row in rows)
    by_paper: dict[str, set[str]] = {}
    for row in rows:
        by_paper.setdefault(row["paper_id"], set()).add(row["split"])
    assert all(len(values) == 1 for values in by_paper.values())


def test_export_roundtrip_and_column_order(tmp_path: Path) -> None:
    path = tmp_path / "audit.csv"
    write_export(path, export_rows([_claim(1)]))
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert tuple(rows[0]) == AUDIT_COLUMNS
    assert len(rows) == 2
    assert read_audit(path)[0]["claim_id"] == "PMC1:1"


def test_load_claims_accepts_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "claims.jsonl"
    path.write_text("\ufeff" + _claim(1).model_dump_json() + "\n", encoding="utf-8")
    assert load_claims(path)[0].claim_id == "PMC1:1"


def test_read_audit_accepts_utf8_bom(tmp_path: Path) -> None:
    path = tmp_path / "audit.csv"
    write_export(path, export_rows([_claim(1)]))
    content = path.read_text(encoding="utf-8")
    path.write_bytes(b"\xef\xbb\xbf" + content.encode("utf-8"))
    assert read_audit(path)[0]["claim_id"] == "PMC1:1"


def test_read_audit_rejects_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "audit.csv"
    path.write_text("claim_id,label\nx,CORRECT\n", encoding="utf-8")
    with pytest.raises(AuditError, match="missing columns"):
        read_audit(path)


def test_wilson_interval_known_value() -> None:
    low, high = wilson_interval(90, 100)
    assert low == pytest.approx(0.8256, abs=1e-3)
    assert high == pytest.approx(0.9448, abs=1e-3)
    assert wilson_interval(0, 10)[0] == 0.0
    assert wilson_interval(10, 10)[1] == pytest.approx(1.0)


def test_wilson_interval_rejects_bad_input() -> None:
    with pytest.raises(AuditError, match="at least one"):
        wilson_interval(0, 0)
    with pytest.raises(AuditError, match="between"):
        wilson_interval(11, 10)


def test_cohen_kappa_perfect_and_chance() -> None:
    assert cohen_kappa(["A", "A", "B"], ["A", "A", "B"]) == pytest.approx(1.0)
    assert cohen_kappa(["A", "A", "B", "B"], ["A", "B", "A", "B"]) == pytest.approx(0.0)


def test_metrics_precision_breakdown_and_unlabelled() -> None:
    rows = [
        _labelled_row("p1:1", "CORRECT"),
        _labelled_row("p1:2", "CORRECT"),
        _labelled_row("p2:1", "CORRECT"),
        _labelled_row("p2:2", "NOT_A_CLAIM"),
    ]
    rows.append(_labelled_row("p3:1", ""))
    metrics = compute_metrics(rows)
    overall = metrics["overall"]
    assert isinstance(overall, dict)
    assert overall["n"] == 4
    assert overall["correct"] == 3
    assert overall["precision"] == pytest.approx(0.75)
    assert metrics["unlabelled"] == 1
    breakdown = metrics["breakdown"]
    assert isinstance(breakdown, dict)
    assert breakdown["CORRECT"] == 3
    assert breakdown["NOT_A_CLAIM"] == 1
    assert set(breakdown) == set(LABELS)
    by_section = metrics["by_section"]
    assert isinstance(by_section, dict)
    assert by_section["Results"]["n"] == 4


def test_metrics_agreement_uses_relabels() -> None:
    rows = [
        _labelled_row("p1:1", "CORRECT", "CORRECT"),
        _labelled_row("p1:2", "CORRECT", "DISTORTED"),
        _labelled_row("p2:1", "NOT_A_CLAIM", "NOT_A_CLAIM"),
    ]
    agreement = compute_metrics(rows)["agreement"]
    assert isinstance(agreement, dict)
    assert agreement["n"] == 3
    assert agreement["raw_agreement"] == pytest.approx(2 / 3)


def test_metrics_ignore_blank_relabel_and_flag_unknown_labels() -> None:
    rows = [_labelled_row("p1:1", "CORRECT", ""), _labelled_row("p1:2", "CORRECT", "MAYBE")]
    assert compute_metrics(rows)["agreement"] is None
    rows.append(_labelled_row("p1:3", "GREAT"))
    with pytest.raises(AuditError, match="unknown labels"):
        compute_metrics(rows)


def test_metrics_reject_all_unlabelled() -> None:
    with pytest.raises(AuditError, match="no labelled rows"):
        compute_metrics([_labelled_row("p1:1", "")])


def test_render_markdown_contains_numbers() -> None:
    metrics = compute_metrics([_labelled_row("p1:1", "CORRECT")])
    report = render_markdown(metrics, source="--audit x.csv")
    assert "Precision: **100.0%**" in report
    assert "Wilson 95% CI" in report
    assert "Not available" in report


def test_sample_cli_writes_export_and_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    claims_path = tmp_path / "claims.jsonl"
    _write_jsonl(claims_path, [_claim(index) for index in range(1, 251)])
    out_path = tmp_path / "audit.csv"
    assert sample_main(["--claims", str(claims_path), "--out", str(out_path)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["sampled_claims"] == 200
    assert summary["available_claims"] == 250
    assert len(summary["corpus_snapshot_id"]) == 64
    with out_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 200
    assert all(row["label"] == "" for row in rows)


def test_sample_cli_refuses_small_sample(tmp_path: Path) -> None:
    claims_path = tmp_path / "claims.jsonl"
    _write_jsonl(claims_path, [_claim(index) for index in range(1, 11)])
    out_path = tmp_path / "audit.csv"
    assert sample_main(["--claims", str(claims_path), "--out", str(out_path)]) == 2
    assert not out_path.exists()


def test_metrics_cli_writes_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    audit_path = tmp_path / "audit.csv"
    write_export(audit_path, [_labelled_row("p1:1", "CORRECT")])
    report_path = tmp_path / "report.md"
    assert metrics_main(["--audit", str(audit_path), "--out", str(report_path), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["overall"]["n"] == 1
    assert "Precision" in report_path.read_text(encoding="utf-8")
