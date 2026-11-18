"""Offline tests for the P3-03 wave-1 metrics script."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from scripts.dependency_metrics import (
    MetricsError,
    counts,
    main,
    positives_needed,
    rate_with_interval,
    read_metrics_inputs,
    rows_for,
    weighted_rate,
)

CLASSES = ("RELIES_ON", "MENTIONS", "UNRELATED", "insufficient_context")


def _row(row_id: str, label: str, *, frame: str = "uniform", weight: str = "203.9") -> dict:
    return {"row_id": row_id, "label": label, "frame": frame, "weight": weight}


def _write_pair(
    manifest: Path, label_file: Path, labels: list[str], frames: list[str], prefix: str = "P3W1"
) -> tuple[Path, Path]:
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["row_id", "frame", "weight", "split", "text_bearing", "linked"],
            lineterminator="\n",
        )
        writer.writeheader()
        for index, (label, frame) in enumerate(zip(labels, frames, strict=True), start=1):
            writer.writerow(
                {
                    "row_id": f"{prefix}-{index:03d}",
                    "frame": frame,
                    "weight": "203.9" if frame == "uniform" else "9.0",
                    "split": "dev" if index % 2 else "test",
                    "text_bearing": "true" if label != "insufficient_context" else "false",
                    "linked": "false",
                }
            )
    with label_file.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["row_id", "label", "labeler"], lineterminator="\n"
        )
        writer.writeheader()
        for index, label in enumerate(labels, start=1):
            writer.writerow({"row_id": f"{prefix}-{index:03d}", "label": label, "labeler": "Soham"})
    return manifest, label_file


def _write_inputs(tmp_path: Path, labels: list[str], frames: list[str]) -> tuple[Path, Path]:
    return _write_pair(tmp_path / "manifest.csv", tmp_path / "labels.csv", labels, frames)


def test_counts_treats_the_skip_action_as_insufficient_context() -> None:
    rows = [_row("A", "RELIES_ON"), _row("B", "insufficient_context")]
    assert counts(rows) == {
        "RELIES_ON": 1,
        "MENTIONS": 0,
        "UNRELATED": 0,
        "insufficient_context": 1,
    }


def test_blank_label_is_read_as_the_skip_class(tmp_path: Path) -> None:
    manifest, labels = _write_inputs(tmp_path, ["", "MENTIONS"], ["uniform", "enriched"])
    rows = read_metrics_inputs(manifest, labels)
    assert [row["label"] for row in rows] == ["insufficient_context", "MENTIONS"]


def test_weighted_rate_matches_the_unweighted_rate_with_equal_weights() -> None:
    rows = [_row("A", "RELIES_ON"), _row("B", "MENTIONS"), _row("C", "MENTIONS")]
    rate, effective = weighted_rate(rows)
    assert rate == pytest.approx(1 / 3)
    assert effective == pytest.approx(3.0)
    interval = rate_with_interval(rows)
    assert interval["positives"] == 1
    assert interval["wilson_low"] < rate < interval["wilson_high"]


def test_positives_needed_matches_the_adr_table() -> None:
    # ADR-0023 section 6: ~30 positives at observed recall 0.85 clears a 0.70 lower bound.
    assert positives_needed(0.85) == 30
    assert positives_needed(0.80) == 77
    assert positives_needed(0.85) < positives_needed(0.80)


def test_rows_for_rounds_up() -> None:
    assert rows_for(5, 0.2333) == 22
    assert rows_for(0, 0.5) == 0
    assert rows_for(3, 0.0) == 0


def test_main_writes_report_and_summary(tmp_path: Path) -> None:
    labels = ["RELIES_ON", "MENTIONS", "UNRELATED", "RELIES_ON"]
    frames = ["uniform", "uniform", "uniform", "enriched"]
    manifest, label_file = _write_inputs(tmp_path, labels, frames)
    report = tmp_path / "report.md"
    summary = tmp_path / "summary.json"

    assert (
        main(
            [
                "--manifest",
                str(manifest),
                "--labels",
                str(label_file),
                "--report",
                str(report),
                "--summary",
                str(summary),
            ]
        )
        == 0
    )
    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["rows"] == 4
    assert data["overall"]["RELIES_ON"] == 2
    assert data["by_frame"]["uniform"]["RELIES_ON"] == 1
    text = report.read_text(encoding="utf-8")
    assert "RELIES_ON" in text and "Wave-2 recommendation" in text


def test_combined_report_covers_both_waves(tmp_path: Path) -> None:
    wave1_manifest, wave1_labels = _write_pair(
        tmp_path / "w1-manifest.csv",
        tmp_path / "w1-labels.csv",
        ["RELIES_ON", "MENTIONS", "UNRELATED"],
        ["uniform", "uniform", "uniform"],
    )
    wave2_manifest, wave2_labels = _write_pair(
        tmp_path / "w2-manifest.csv",
        tmp_path / "w2-labels.csv",
        ["RELIES_ON", "RELIES_ON", "UNRELATED", "MENTIONS"],
        ["uniform"] * 4,
        prefix="P3W2",
    )
    combined = tmp_path / "combined.md"
    summary = tmp_path / "combined.json"
    assert (
        main(
            [
                "--manifest",
                str(wave1_manifest),
                "--labels",
                str(wave1_labels),
                "--wave2-manifest",
                str(wave2_manifest),
                "--wave2-labels",
                str(wave2_labels),
                "--report",
                str(tmp_path / "w1.md"),
                "--summary",
                str(tmp_path / "w1.json"),
                "--combined-report",
                str(combined),
                "--combined-summary",
                str(summary),
            ]
        )
        == 0
    )
    text = combined.read_text(encoding="utf-8")
    assert "Stop rule" in text and "Combined" in text
    data = json.loads(summary.read_text(encoding="utf-8"))
    assert data["combined"]["rows"] == 7
    assert data["combined"]["overall"]["RELIES_ON"] == 3
    assert data["positives_needed_080"] == 77
    assert data["extra_positives_for_080"] == 74


def test_partial_label_coverage_is_rejected(tmp_path: Path) -> None:
    manifest, label_file = _write_inputs(
        tmp_path, ["RELIES_ON", "MENTIONS"], ["uniform", "uniform"]
    )
    rows = label_file.read_text(encoding="utf-8").splitlines()
    label_file.write_text("\n".join(rows[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(MetricsError, match="manifest has"):
        read_metrics_inputs(manifest, label_file)
