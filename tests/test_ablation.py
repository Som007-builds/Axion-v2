"""Offline tests for the P2 ablation harness."""

from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path

import pytest

from axion.eval.ablation import (
    AblationConfig,
    AblationError,
    ConfigClaim,
    DocumentIndex,
    GoldClaim,
    baseline_check,
    evaluate_config,
    ledger_cost,
    load_config_claims,
    load_gold,
    render_report,
    score,
    sentence_key,
)
from axion.eval.audit import AUDIT_COLUMNS
from axion.extract.claims import BaselineDocument, BaselineSection
from axion.llm.ledger import LedgerEntry, SQLiteLedger

ROOT = Path(__file__).resolve().parents[1]
GOLD_COLUMNS = tuple(AUDIT_COLUMNS)


def _write_gold(path: Path, rows: list[dict[str, str]]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(GOLD_COLUMNS))
        writer.writeheader()
        for row in rows:
            full = {column: "" for column in GOLD_COLUMNS}
            full.update(row)
            writer.writerow(full)
    return path


def _gold_row(
    claim_id: str,
    paper_id: str,
    split: str,
    label: str,
    span: str,
    section: str = "Results",
) -> dict[str, str]:
    return {
        "claim_id": claim_id,
        "paper_id": paper_id,
        "paper_title": "T",
        "section": section,
        "claim_text": span,
        "evidence_span": span,
        "label": label,
        "labeler": "owner",
        "split": split,
    }


def _documents() -> list[BaselineDocument]:
    return [
        BaselineDocument(
            paper_id="P1",
            paper_title="Paper one",
            sections=(
                BaselineSection(
                    label="Results",
                    path=("Results",),
                    text=(
                        "We enrolled 120 patients. Treatment reduced mortality by 8% (p=0.01). "
                        "The study was funded by a grant."
                    ),
                ),
            ),
        )
    ]


def _index(tmp_path: Path) -> DocumentIndex:
    index = DocumentIndex.load(tmp_path / "missing")
    index._documents["P1"] = _documents()[0]
    return index


def test_sentence_key_returns_containing_sentence() -> None:
    document = _documents()[0]
    key = sentence_key(document, section_label="Results", evidence_span="reduced mortality by 8%")
    assert key is not None
    assert key.startswith("treatment reduced mortality by 8%")
    assert "funded" not in key


def test_score_is_exact_for_a_replay(tmp_path: Path) -> None:
    gold = [
        GoldClaim(
            claim_id="P1:0",
            paper_id="P1",
            split="dev",
            label="CORRECT",
            section="Results",
            evidence_span="Treatment reduced mortality by 8% (p=0.01).",
        ),
        GoldClaim(
            claim_id="P1:1",
            paper_id="P1",
            split="dev",
            label="CORRECT",
            section="Results",
            evidence_span="We enrolled 120 patients.",
        ),
    ]
    claims = [
        ConfigClaim(
            paper_id="P1",
            section="Results",
            evidence_span="We enrolled 120 patients.",
        ),
        ConfigClaim(
            paper_id="P1",
            section="Results",
            evidence_span="Treatment reduced mortality by 8% (p=0.01).",
        ),
    ]
    by_split, overall = score(gold, claims, matching="sentence", index=_index(tmp_path))
    assert overall.retained == 2
    assert overall.precision == 1.0
    assert overall.emitted == 2
    assert overall.claim_aligned == 2
    assert by_split["dev"].retention == 1.0
    assert by_split["test"].gold == 0


def test_unverifiable_claims_are_counted_not_corrected(tmp_path: Path) -> None:
    gold = [
        GoldClaim(
            claim_id="P1:0",
            paper_id="P1",
            split="dev",
            label="CORRECT",
            section="Results",
            evidence_span="We enrolled 120 patients.",
        )
    ]
    claims = [
        ConfigClaim(paper_id="P1", section="Results", evidence_span="We enrolled 120 patients."),
        ConfigClaim(
            paper_id="P1", section="Results", evidence_span="The study was funded by a grant."
        ),
    ]
    _, overall = score(gold, claims, matching="sentence", index=_index(tmp_path))
    assert overall.emitted == 2
    assert overall.claim_aligned == 1
    assert overall.claim_correct == 1
    assert overall.retention == 1.0


def test_missing_gold_label_is_rejected(tmp_path: Path) -> None:
    path = _write_gold(
        tmp_path / "gold.csv",
        [_gold_row("P1:0", "P1", "dev", "", "We enrolled 120 patients.")],
    )
    with pytest.raises(AblationError):
        load_gold(path)


def test_paper_cannot_straddle_splits(tmp_path: Path) -> None:
    path = _write_gold(
        tmp_path / "gold.csv",
        [
            _gold_row("P1:0", "P1", "dev", "CORRECT", "We enrolled 120 patients."),
            _gold_row("P1:1", "P1", "test", "CORRECT", "Treatment reduced mortality."),
        ],
    )
    with pytest.raises(AblationError, match="both splits"):
        load_gold(path)


def test_load_config_claims_reads_teacher_rows(tmp_path: Path) -> None:
    path = tmp_path / "silver.jsonl"
    row = {
        "paper_id": "P1",
        "claim_index": 0,
        "claim": {
            "claim_text": "x",
            "section": "Results",
            "evidence_span": "We enrolled 120 patients.",
        },
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    claims = load_config_claims(path)
    assert claims[0].paper_id == "P1"
    assert claims[0].evidence_span == "We enrolled 120 patients."


def test_ledger_cost_counts_successes_and_hits(tmp_path: Path) -> None:
    ledger = SQLiteLedger(tmp_path / "ledger.sqlite3")
    ledger.record(
        LedgerEntry(
            stage="teacher_label",
            provider="gemini",
            model="m",
            prompt_tokens=10,
            completion_tokens=5,
            reasoning_tokens=0,
            usd=Decimal("0.10"),
            latency_ms=1.0,
            run_id="r1",
        )
    )
    ledger.record(
        LedgerEntry(
            stage="teacher_label",
            provider="gemini",
            model="m",
            prompt_tokens=10,
            completion_tokens=5,
            reasoning_tokens=0,
            usd=Decimal("0"),
            latency_ms=0.0,
            cache_hit=True,
            run_id="r1",
        )
    )
    ledger.record(
        LedgerEntry(
            stage="teacher_label",
            provider="gemini",
            model="m",
            prompt_tokens=0,
            completion_tokens=0,
            reasoning_tokens=0,
            usd=None,
            latency_ms=2.0,
            error="boom",
            run_id="r1",
        )
    )
    summary = ledger_cost([tmp_path / "ledger.sqlite3"], ["r1"])
    assert summary.measured
    assert summary.usd == Decimal("0.10")
    assert summary.calls == 1
    assert summary.cache_hits == 1


def test_evaluate_config_end_to_end(tmp_path: Path) -> None:
    gold_path = _write_gold(
        tmp_path / "gold.csv",
        [
            _gold_row("P1:0", "P1", "dev", "CORRECT", "We enrolled 120 patients."),
            _gold_row("P2:0", "P2", "test", "NOT_A_CLAIM", "The study was funded by a grant."),
        ],
    )
    claims_path = tmp_path / "claims.jsonl"
    claims_path.write_text(
        json.dumps(
            {
                "paper_id": "P1",
                "section": "Results",
                "evidence_span": "We enrolled 120 patients.",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    config = AblationConfig(
        name="test",
        description="unit",
        kind="replay",
        claims_path=str(claims_path),
        matching="sentence",
        paper_count=1,
        run_ids=("r1",),
        ledgers=(str(tmp_path / "ledger.sqlite3"),),
    )
    score_row = evaluate_config(config, gold_path=gold_path, source_dir=tmp_path / "missing")
    # Without source documents the sentence key is unavailable, so nothing
    # aligns: the harness must say so rather than claim a score.
    assert score_row.overall.precision is None
    assert score_row.overall.retention == 0.0
    assert score_row.cost_per_paper_usd is None
    config_span = config.model_copy(update={"matching": "span"})
    score_row = evaluate_config(config_span, gold_path=gold_path, source_dir=tmp_path / "missing")
    assert score_row.overall.retention == 0.5
    assert score_row.by_split["dev"].retention == 1.0
    assert score_row.overall.precision == 1.0


def test_baseline_check_requires_exact_193_of_200(tmp_path: Path) -> None:
    gold_rows = [
        _gold_row(f"P1:{index}", "P1", "dev", "CORRECT", "We enrolled 120 patients.")
        for index in range(193)
    ] + [
        _gold_row(f"P1:{index}", "P1", "dev", "NOT_A_CLAIM", "The study was funded by a grant.")
        for index in range(193, 200)
    ]
    gold_path = _write_gold(tmp_path / "gold.csv", gold_rows)
    claims_path = tmp_path / "claims.jsonl"
    claims_path.write_text(
        "\n".join(
            json.dumps({"paper_id": "P1", "section": "Results", "evidence_span": span})
            for span in (
                ["We enrolled 120 patients."] * 193 + ["The study was funded by a grant."] * 7
            )
        )
        + "\n",
        encoding="utf-8",
    )
    config = AblationConfig(
        name="baseline",
        description="unit",
        kind="replay",
        claims_path=str(claims_path),
        matching="span",
        paper_count=1,
    )
    score_row = evaluate_config(config, gold_path=gold_path, source_dir=tmp_path / "missing")
    check = baseline_check(score_row)
    assert check["precision_matches"] is True
    assert check["retention_complete"] is True
    assert score_row.overall.precision == 0.965


def test_report_states_the_precision_only_limit(tmp_path: Path) -> None:
    gold_path = _write_gold(
        tmp_path / "gold.csv",
        [_gold_row("P1:0", "P1", "dev", "CORRECT", "We enrolled 120 patients.")],
    )
    claims_path = tmp_path / "claims.jsonl"
    claims_path.write_text(
        json.dumps(
            {"paper_id": "P1", "section": "Results", "evidence_span": "We enrolled 120 patients."}
        )
        + "\n",
        encoding="utf-8",
    )
    config = AblationConfig(
        name="baseline",
        description="unit",
        kind="replay",
        claims_path=str(claims_path),
        matching="span",
        paper_count=1,
    )
    score_row = evaluate_config(config, gold_path=gold_path, source_dir=tmp_path / "missing")
    report = render_report([score_row])
    assert "absolute recall" in report
    assert "unverifiable" in report.lower()
    assert "not recall" in report
