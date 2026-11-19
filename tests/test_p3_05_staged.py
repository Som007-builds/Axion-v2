"""Tests for the P3-05 staged cascade and P3-05b scheduler (dev-only logic)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import scripts.p3_05_staged as staged
from scripts.dependency_baselines import POSITIVE


def _row(
    row_id: str,
    label: str,
    *,
    context: str = "we used the assay [1].",
    claim: str = "A claims X.",
    section: str = "Methods",
) -> dict[str, str]:
    return {
        "row_id": row_id,
        "wave": "wave1",
        "split": "dev",
        "text_bearing": "true" if claim else "false",
        "weight": "1.0",
        "frame": "text_bearing" if claim else "stub",
        "section": section,
        "section_bucket": "methods" if section == "Methods" else "introduction",
        "label": label,
        "context_text": context,
        "paragraph_text": "",
        "source_title": "Source",
        "source_claim_text": claim,
        "source_abstract": "",
        "citer_title": "Citer",
    }


HEURISTIC = {
    "section_scale": 1.0,
    "reliance_weight": 1.0,
    "mention_weight": 1.0,
    "threshold": 0.0,
}


def test_candidate_is_the_recall_stage() -> None:
    stage1 = staged.Stage1(candidate_threshold=0.0, heuristic=HEURISTIC)
    reliance = _row("a", POSITIVE, context="we used the assay [1].")
    background = _row("b", "MENTIONS", context="has been reviewed in [1].", section="Introduction")

    assert stage1.candidate(reliance) is True
    assert stage1.candidate(background) is False


def test_cascade_keeps_nominations_when_stage_two_is_absent() -> None:
    stage1 = staged.Stage1(candidate_threshold=0.0, heuristic=HEURISTIC)
    rows = [
        _row("a", POSITIVE, context="we used the assay [1]."),
        _row("b", "MENTIONS", context="has been reviewed in [1].", section="Introduction"),
    ]

    predictions, tally = staged.cascade_predictions(
        rows, stage1, stage2_scores=None, stage2_threshold=60.0
    )

    assert predictions == {"a": 1, "b": 0}
    assert tally["candidate"] == 1
    assert tally["rejected_by_stage1"] == 1
    assert tally["verified_positive"] == 0


def test_cascade_verifies_candidates_with_stage_two() -> None:
    stage1 = staged.Stage1(candidate_threshold=0.0, heuristic=HEURISTIC)
    rows = [_row("a", POSITIVE), _row("b", "MENTIONS", context="we used the assay [1].")]

    predictions, tally = staged.cascade_predictions(
        rows, stage1, stage2_scores={"a": 85.0, "b": 20.0}, stage2_threshold=60.0
    )

    assert predictions == {"a": 1, "b": 0}
    assert tally["verified_positive"] == 1
    assert tally["verified_negative"] == 1


def test_tune_stage1_rejects_a_threshold_that_loses_positives() -> None:
    rows = [
        _row("p1", POSITIVE, context="we used the assay [1]."),
        _row("p2", POSITIVE, context="adapted from [1]."),
        _row("n1", "MENTIONS", context="has been reviewed in [1].", section="Introduction"),
    ]

    tuning = staged.tune_stage1(rows, target_recall=0.9)

    stage1 = tuning["stage1"]
    assert isinstance(stage1, dict)
    assert stage1["candidate_threshold"] in staged.GRID_CANDIDATE
    grid = tuning["grid"]
    assert isinstance(grid, list)
    assert len(grid) == len(staged.GRID_CANDIDATE)


def test_tune_stage2_picks_the_threshold_that_holds_recall() -> None:
    stage1 = staged.Stage1(candidate_threshold=0.0, heuristic=HEURISTIC)
    rows = [
        _row("p1", POSITIVE),
        _row("p2", POSITIVE),
        _row("n1", "MENTIONS", context="we used the assay [1]."),
    ]
    scores = {"p1": 90.0, "p2": 70.0, "n1": 45.0}

    tuning = staged.tune_stage2(rows, stage1, scores, target_recall=0.8)

    # Thresholds 40-70 all keep both positives and reject the negative, so the
    # tie-break picks the lowest one that holds the floor.
    assert tuning["stage2_threshold"] == 50.0
    grid = tuning["grid"]
    assert isinstance(grid, list) and len(grid) == len(staged.GRID_STAGE2)


def test_tune_stage2_raises_when_no_threshold_holds_recall() -> None:
    stage1 = staged.Stage1(candidate_threshold=0.0, heuristic=HEURISTIC)
    rows = [_row("p1", POSITIVE)]
    with pytest.raises(staged.DetectorError):
        staged.tune_stage2(rows, stage1, {"p1": 10.0}, target_recall=0.8)


def test_scheduler_finds_positives_earlier_than_random() -> None:
    rows = [
        _row("p1", POSITIVE, context="we used the assay [1]."),
        _row("n1", "MENTIONS", context="has been reviewed in [1].", section="Introduction"),
        _row("n2", "MENTIONS", context="e.g. [1].", section="Introduction"),
        _row("n3", "MENTIONS", context="such as [1].", section="Introduction"),
    ]

    curve = staged.scheduler_curve(rows, HEURISTIC)

    assert curve[-1]["recall"] == 1.0
    assert curve[0]["positives_found"] >= 1


def test_freeze_refuses_a_changed_spec(tmp_path: Path, monkeypatch) -> None:
    freeze = tmp_path / "frozen.json"
    monkeypatch.setattr(staged, "SPEC_FREEZE", freeze)
    payload = {
        "stage1": {"candidate_threshold": 0.0, "heuristic": HEURISTIC},
        "stage2": {"prompt_version": "v", "threshold": 60.0},
        "scheduler": "rule",
    }

    written = staged.verify_or_write_freeze(payload, write=True)
    assert written["frozen"] is True
    assert json.loads(freeze.read_text(encoding="utf-8"))["spec_hash"] == written["spec_hash"]

    # Same spec passes.
    assert staged.verify_or_write_freeze(payload, write=False)["spec_hash"] == written["spec_hash"]

    # A changed threshold is a new spec, refused once the freeze exists.
    changed = json.loads(json.dumps(payload))
    changed["stage2"]["threshold"] = 70.0
    with pytest.raises(staged.DetectorError, match="does not match"):
        staged.verify_or_write_freeze(changed, write=False)
