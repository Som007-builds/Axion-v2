"""Offline tests for the P3-03 second-labeler overlap (ADR-0023 Amendment A).

The overlap is built from labeler 1's returned wave-1 labels, not chosen in
advance, so these tests pin the selection rule, the blindness guarantees and the
rejection paths. No corpus, no network, no labels.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from scripts.dependency_sample import (
    BLIND_COLUMNS,
    OverlapError,
    build_overlap_from_labels,
    read_wave_labels,
    select_overlap_from_labels,
)

WAVE = 150


def _row_id(number: int) -> str:
    return f"P3W1-{number:03d}"


def _write_labels(path: Path, labels: dict[str, str], labeler: str = "Soham") -> Path:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["row_id", "label", "note", "labeler", "date"])
        for row_id, label in labels.items():
            writer.writerow([row_id, label, "", labeler, "2026-11-18"])
    return path


def _write_wave(out_dir: Path, row_ids: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "p3-03-wave1-manifest.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["row_id"], lineterminator="\n")
        writer.writeheader()
        for row_id in row_ids:
            writer.writerow({"row_id": row_id})
    with (out_dir / "p3-03-wave1-blind.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(BLIND_COLUMNS), lineterminator="\n")
        writer.writeheader()
        for row_id in row_ids:
            row = dict.fromkeys(BLIND_COLUMNS, "")
            row["row_id"] = row_id
            row["context_text"] = f"context for {row_id}"
            row["guideline_version"] = "P3-v1.1"
            writer.writerow(row)


def _labels(*, positives: int, negative_splits: tuple[int, int, int]) -> dict[str, str]:
    """Build a full 150-row label map with the requested class counts."""
    counts = [("RELIES_ON", positives)]
    counts += list(
        zip(("MENTIONS", "UNRELATED", "insufficient_context"), negative_splits, strict=True)
    )
    labels: dict[str, str] = {}
    number = 1
    for label, count in counts:
        for _ in range(count):
            labels[_row_id(number)] = label
            number += 1
    while number <= WAVE:  # pad with MENTIONS so the export always covers the wave
        labels[_row_id(number)] = "MENTIONS"
        number += 1
    assert len(labels) == WAVE
    return labels


def test_selection_takes_every_positive_and_the_floors() -> None:
    labels = _labels(positives=5, negative_splits=(40, 30, 20))
    selection = select_overlap_from_labels(labels, wave_size=WAVE)

    positives = {row for row, label in labels.items() if label == "RELIES_ON"}
    assert set(selection.positives) == positives
    assert positives <= set(selection.row_ids)
    assert len(selection.row_ids) >= 30
    assert len(selection.row_ids) >= 0.20 * WAVE
    assert selection.negative_count >= 6
    assert selection.target_rows == 30


def test_round_robin_puts_every_negative_class_in_the_overlap() -> None:
    labels = _labels(positives=2, negative_splits=(40, 30, 20))
    selection = select_overlap_from_labels(labels, wave_size=WAVE)

    assert set(selection.negatives) == {"MENTIONS", "UNRELATED", "insufficient_context"}
    for drawn in selection.negatives.values():
        assert drawn, "every negative class must be represented"
    assert selection.negative_count == len(set(selection.row_ids)) - len(selection.positives)


def test_selection_is_deterministic_and_hash_ordered() -> None:
    labels = _labels(positives=4, negative_splits=(40, 30, 20))
    first = select_overlap_from_labels(labels, wave_size=WAVE)
    second = select_overlap_from_labels(labels, wave_size=WAVE)

    assert first.row_ids == second.row_ids
    assert list(first.row_ids) != sorted(first.row_ids), "order must not be row-id order"


def test_blind_file_is_blank_and_carries_no_internal_columns(tmp_path: Path) -> None:
    labels = _labels(positives=3, negative_splits=(40, 30, 20))
    _write_wave(tmp_path, sorted(labels))
    summary = build_overlap_from_labels(_write_labels(tmp_path / "labels.csv", labels), tmp_path)

    with (tmp_path / "p3-03-wave1-overlap2-blind.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert "text_bearing" not in (reader.fieldnames or [])
    assert "overlap" not in (reader.fieldnames or [])
    assert "split" not in (reader.fieldnames or [])
    assert [row["row_id"] for row in rows] == list(summary["row_ids"])
    for row in rows:
        assert row["label"] == ""
        assert row["note"] == ""
        assert row["labeler"] == ""
        assert row["date"] == ""


def test_selection_json_reports_counts_but_no_labels(tmp_path: Path) -> None:
    labels = _labels(positives=3, negative_splits=(40, 30, 20))
    _write_wave(tmp_path, sorted(labels))
    build_overlap_from_labels(_write_labels(tmp_path / "labels.csv", labels), tmp_path)

    text = (tmp_path / "p3-03-wave1-overlap2-selection.json").read_text(encoding="utf-8")
    summary = json.loads(text)
    assert summary["positives"] == 3
    assert summary["rows"] == len(summary["row_ids"])
    assert summary["rule"] == "ADR-0023 Amendment A"
    assert summary["labeler"] == "Soham"
    # class names may appear only as counts, never mapped to a row id
    assert "row_labels" not in summary
    assert "label" not in summary
    assert set(summary["negatives_by_class"]) == {
        "MENTIONS",
        "UNRELATED",
        "insufficient_context",
    }
    assert all(isinstance(count, int) for count in summary["negatives_by_class"].values())
    assert all(isinstance(row, str) for row in summary["row_ids"])
    assert "Soham" not in json.dumps(summary["row_ids"])


def test_positive_heavy_wave_keeps_every_positive(tmp_path: Path) -> None:
    labels = _labels(positives=40, negative_splits=(40, 30, 40))
    _write_wave(tmp_path, sorted(labels))
    summary = build_overlap_from_labels(_write_labels(tmp_path / "labels.csv", labels), tmp_path)

    assert summary["positives"] == 40
    assert summary["rows"] > 30


def test_missing_negative_class_is_noted_not_silently_dropped() -> None:
    labels = _labels(positives=2, negative_splits=(40, 0, 20))
    selection = select_overlap_from_labels(labels, wave_size=WAVE)

    assert any("UNRELATED" in note for note in selection.notes)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"label": ""}, "is not one of"),
        ({"label": "MAYBE"}, "is not one of"),
        ({"row_id": "P3W1-999"}, "not a row in this wave"),
        ({"labeler": ""}, "blank labeler id"),
    ],
)
def test_rejects_bad_exports(tmp_path: Path, mutation: dict[str, str], message: str) -> None:
    labels = _labels(positives=3, negative_splits=(40, 30, 20))
    _write_wave(tmp_path, sorted(labels))
    path = _write_labels(tmp_path / "labels.csv", labels)
    rows = list(csv.DictReader(path.open(encoding="utf-8", newline="")))
    rows[0].update(mutation)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    with pytest.raises(OverlapError, match=message):
        build_overlap_from_labels(path, tmp_path)


def test_rejects_mixed_labelers(tmp_path: Path) -> None:
    labels = _labels(positives=3, negative_splits=(40, 30, 20))
    path = _write_labels(tmp_path / "labels.csv", labels)
    with path.open("a", encoding="utf-8", newline="") as handle:
        handle.write(f"{_row_id(1)},MENTIONS,,friend,2026-11-18\n")

    with pytest.raises(OverlapError, match="mixes labelers"):
        read_wave_labels(path)


def test_rejects_partial_wave(tmp_path: Path) -> None:
    labels = _labels(positives=3, negative_splits=(40, 30, 20))
    _write_wave(tmp_path, sorted(labels))
    partial = dict(list(labels.items())[:149])
    path = _write_labels(tmp_path / "labels.csv", partial)

    with pytest.raises(OverlapError, match="label the whole wave"):
        build_overlap_from_labels(path, tmp_path)
