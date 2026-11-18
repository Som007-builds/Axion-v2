"""Offline tests for the P3-03 agreement script (ADR-0023 Amendment A)."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from scripts.dependency_agreement import (
    AgreementError,
    cohen_kappa,
    main,
    read_labels,
    weighted_kappa,
)


def _write(path: Path, rows: list[dict[str, str]], fields: list[str]) -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def _labels(path: Path, labeler: str, pairs: list[tuple[str, str]]) -> Path:
    return _write(
        path,
        [{"row_id": row_id, "label": label, "labeler": labeler} for row_id, label in pairs],
        ["row_id", "label", "labeler"],
    )


def test_kappa_is_one_when_labelers_agree() -> None:
    left = ["RELIES_ON", "MENTIONS", "UNRELATED", "RELIES_ON"]
    assert cohen_kappa(left, list(left)) == 1.0


def test_kappa_matches_a_hand_computed_case() -> None:
    # 3/4 agree, marginals R .5/.5, M .5/.25, U 0/.25 -> pe = .375 -> kappa = .6
    left = ["RELIES_ON", "RELIES_ON", "MENTIONS", "MENTIONS"]
    right = ["RELIES_ON", "RELIES_ON", "MENTIONS", "UNRELATED"]
    assert cohen_kappa(left, right) == pytest.approx(0.6)


def test_kappa_is_zero_at_chance() -> None:
    left = ["RELIES_ON", "RELIES_ON", "MENTIONS", "MENTIONS"]
    right = ["RELIES_ON", "MENTIONS", "MENTIONS", "RELIES_ON"]
    assert cohen_kappa(left, right) == pytest.approx(0.0)


def test_weighted_kappa_defaults_to_kappa_when_weights_are_equal() -> None:
    left = ["RELIES_ON", "RELIES_ON", "MENTIONS", "MENTIONS"]
    right = ["RELIES_ON", "RELIES_ON", "MENTIONS", "UNRELATED"]
    assert weighted_kappa(left, right, [1.0] * 4) == pytest.approx(cohen_kappa(left, right))


def test_blank_label_is_read_as_skip_and_labelers_are_single(tmp_path: Path) -> None:
    path = _labels(tmp_path / "l.csv", "Soham", [("A", "RELIES_ON"), ("B", "")])
    labels, labeler = read_labels(path, role="labeler 1")
    assert labels == {"A": "RELIES_ON", "B": "skip"}
    assert labeler == "Soham"


@pytest.mark.parametrize(
    ("pairs", "message"),
    [
        ([("A", "MAYBE")], "is not one of"),
        ([("A", "RELIES_ON"), ("A", "MENTIONS")], "repeats"),
    ],
)
def test_read_labels_rejects_bad_rows(
    tmp_path: Path, pairs: list[tuple[str, str]], message: str
) -> None:
    path = _labels(tmp_path / "l.csv", "Soham", pairs)
    with pytest.raises(AgreementError, match=message):
        read_labels(path, role="labeler 1")


def test_read_labels_rejects_mixed_labelers(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "l.csv",
        [
            {"row_id": "A", "label": "RELIES_ON", "labeler": "Soham"},
            {"row_id": "B", "label": "MENTIONS", "labeler": "friend"},
        ],
        ["row_id", "label", "labeler"],
    )
    with pytest.raises(AgreementError, match="one labeler"):
        read_labels(path, role="labeler 2")


def test_main_flags_degenerate_kappa_and_writes_the_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.dependency_agreement as module

    pairs = [(f"P3W1-{i:03d}", "RELIES_ON") for i in range(1, 7)]
    wave = _labels(tmp_path / "wave.csv", "Soham", pairs)
    overlap = _labels(tmp_path / "overlap.csv", "friend", pairs)
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps({"row_ids": [row_id for row_id, _ in pairs]}), encoding="utf-8")
    manifest = _write(
        tmp_path / "manifest.csv",
        [{"row_id": row_id, "weight": "9.0"} for row_id, _ in pairs],
        ["row_id", "weight"],
    )
    for name, value in (
        ("WAVE_LABELS", wave),
        ("OVERLAP_LABELS", overlap),
        ("SELECTION", selection),
        ("MANIFEST", manifest),
        ("REPORT", tmp_path / "report.md"),
        ("SUMMARY", tmp_path / "summary.json"),
    ):
        monkeypatch.setattr(module, name, value)

    assert main(["--bootstrap", "20"]) == 0
    summary = json.loads((tmp_path / "summary.json").read_text(encoding="utf-8"))
    assert summary["rows"] == 6
    assert summary["cohen_kappa"] == 1.0
    assert summary["degenerate"] is True
    assert summary["negative_side_estimable"] is False
    assert "degenerate" in (tmp_path / "report.md").read_text(encoding="utf-8").lower()


def test_main_rejects_an_export_that_is_not_the_blinded_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import scripts.dependency_agreement as module

    wave = _labels(tmp_path / "wave.csv", "Soham", [("P3W1-001", "RELIES_ON")])
    overlap = _labels(tmp_path / "overlap.csv", "friend", [("P3W1-002", "RELIES_ON")])
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps({"row_ids": ["P3W1-001"]}), encoding="utf-8")
    manifest = _write(
        tmp_path / "manifest.csv", [{"row_id": "P3W1-001", "weight": "9.0"}], ["row_id", "weight"]
    )
    for name, value in (
        ("WAVE_LABELS", wave),
        ("OVERLAP_LABELS", overlap),
        ("SELECTION", selection),
        ("MANIFEST", manifest),
        ("REPORT", tmp_path / "report.md"),
        ("SUMMARY", tmp_path / "summary.json"),
    ):
        monkeypatch.setattr(module, name, value)

    with pytest.raises(AgreementError, match="not the blinded overlap"):
        main([])
