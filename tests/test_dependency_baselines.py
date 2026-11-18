"""Tests for the P3-04 baseline scoring: metrics, tuning, freeze discipline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import scripts.dependency_baselines as bl


def _row(row_id: str, label: str, weight: str = "1.0", split: str = "dev") -> dict[str, str]:
    return {
        "row_id": row_id,
        "wave": "wave1",
        "split": split,
        "text_bearing": "true",
        "weight": weight,
        "frame": "text_bearing",
        "section": "Methods" if label == "RELIES_ON" else "Introduction",
        "section_bucket": "methods" if label == "RELIES_ON" else "introduction",
        "label": label,
        "context_text": "we used the assay from [1]."
        if label == "RELIES_ON"
        else "has been reviewed in [1].",
        "paragraph_text": "",
        "source_title": "Source",
        "source_claim_text": "",
        "source_abstract": "",
        "citer_title": "Citer",
    }


def test_section_bucket_collapses_headings() -> None:
    assert bl.section_bucket("4. Methods") == "methods"
    assert bl.section_bucket("MATERIALS AND METHODS") == "methods"
    assert bl.section_bucket("Results") == "results"
    assert bl.section_bucket("Discussion") == "discussion"
    assert bl.section_bucket("Background") == "introduction"
    assert bl.section_bucket("") == "unsectioned"
    assert bl.section_bucket("Subsets of Memory CD4 T Cells in TB") == "other"


def test_binary_metrics_counts_precision_recall_and_false_alarms() -> None:
    rows = [
        _row("a", "RELIES_ON"),
        _row("b", "RELIES_ON"),
        _row("c", "MENTIONS"),
        _row("d", "UNRELATED"),
    ]
    predictions = {"a": 1, "b": 0, "c": 1, "d": 0}

    metrics = bl.binary_metrics(predictions, rows)

    assert (metrics["tp"], metrics["fp"], metrics["fn"], metrics["tn"]) == (1, 1, 1, 1)
    unweighted = metrics["unweighted"]
    assert isinstance(unweighted, dict)
    assert unweighted["precision"] == 0.5
    assert unweighted["recall"] == 0.5
    assert unweighted["false_alarm_rate"] == 0.5
    assert unweighted["recall_ci"] is not None


def test_skip_rows_are_excluded_from_scoring() -> None:
    rows = [_row("a", "insufficient_context"), _row("b", "RELIES_ON")]
    assert [row["row_id"] for row in bl.scored_rows(rows)] == ["b"]


def test_weighted_metrics_follow_the_weights() -> None:
    rows = [
        _row("a", "RELIES_ON", weight="10.0"),
        _row("b", "MENTIONS", weight="1.0"),
    ]
    metrics = bl.binary_metrics({"a": 1, "b": 1}, rows)
    unweighted = metrics["unweighted"]
    weighted = metrics["weighted"]
    assert isinstance(unweighted, dict) and isinstance(weighted, dict)
    assert unweighted["precision"] == 0.5
    assert weighted["precision"] is not None and weighted["precision"] > 0.5


def test_tuning_is_deterministic_and_stays_inside_the_grid() -> None:
    rows = [
        _row("a", "RELIES_ON"),
        _row("b", "RELIES_ON"),
        _row("c", "MENTIONS"),
        _row("d", "UNRELATED"),
    ]
    first = bl.tune_heuristic(rows)
    second = bl.tune_heuristic(rows)
    assert first == second
    params = first["params"]
    assert isinstance(params, dict)
    assert params["section_scale"] in bl.GRID_SECTION_SCALE
    assert params["threshold"] in bl.GRID_THRESHOLD
    grid = first["grid"]
    assert isinstance(grid, list)
    assert len(grid) == len(bl.GRID_SECTION_SCALE) * len(bl.GRID_THRESHOLD)


def test_spec_hash_changes_when_the_heuristic_changes() -> None:
    rows = [_row("a", "RELIES_ON")]
    base = {"section_scale": 1.0, "reliance_weight": 1.0, "mention_weight": 1.0, "threshold": 0.0}
    changed = dict(base, threshold=1.0)
    assert bl.spec_hash(rows, base) == bl.spec_hash(rows, dict(base))
    assert bl.spec_hash(rows, base) != bl.spec_hash(rows, changed)
    assert bl.spec_hash(rows, base) != bl.spec_hash([_row("b", "RELIES_ON")], base)


def test_freeze_refuses_to_let_a_frozen_number_move(tmp_path: Path, monkeypatch) -> None:
    freeze = tmp_path / "frozen.json"
    monkeypatch.setattr(bl, "FREEZE", freeze)
    payload = {
        "spec_hash": "abc",
        "results": {"heuristic/text_bearing/test": {"recall": 0.8}},
    }

    bl.freeze_test(payload, refreeze=False)
    assert json.loads(freeze.read_text(encoding="utf-8"))["spec_hash"] == "abc"

    # Same spec, same numbers: allowed, and the file is not rewritten.
    again = bl.freeze_test(payload, refreeze=False)
    assert again["spec_hash"] == "abc"

    # A new baseline may be added after the freeze without touching the frozen key.
    extended = {
        "spec_hash": "abc",
        "results": {
            "heuristic/text_bearing/test": {"recall": 0.8},
            "llm_only/text_bearing/test": {"recall": 0.2},
        },
    }
    merged = bl.freeze_test(extended, refreeze=False)
    assert set(merged["results"]) == {
        "heuristic/text_bearing/test",
        "llm_only/text_bearing/test",
    }
    assert "llm_only/text_bearing/test" in merged["added_at"]

    # A moved number is an error, not a silent update.
    drifted = {
        "spec_hash": "abc",
        "results": {"heuristic/text_bearing/test": {"recall": 0.9}},
    }
    with pytest.raises(bl.FreezeError):
        bl.freeze_test(drifted, refreeze=False)

    # A changed specification is also an error, because the test set has been seen.
    with pytest.raises(bl.FreezeError):
        bl.freeze_test({"spec_hash": "def", "results": {}}, refreeze=False)


def test_build_prompt_includes_the_claim_only_when_it_exists() -> None:
    with_claim = dict(_row("a", "RELIES_ON"), source_claim_text="A claims X.")
    without_claim = dict(_row("b", "RELIES_ON"), source_claim_text="", source_abstract="")

    assert "A claims X." in bl.build_prompt(with_claim)
    assert "not available for this source" in bl.build_prompt(without_claim)
    for prompt in (bl.build_prompt(with_claim), bl.build_prompt(without_claim)):
        assert "RELIES_ON" in prompt and "MENTIONS" in prompt and "UNRELATED" in prompt
