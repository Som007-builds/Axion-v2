"""Offline tests for the wave-2 draw (ADR-0024)."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from scripts.dependency_wave2 import (
    WAVE2_SEED,
    WaveError,
    build_rows,
    draw_wave2,
    wave1_context_ids,
)


def _context(index: int, source: str) -> dict:
    return {
        "ctx_id": f"PMC{index}:p1:c{index}",
        "citer_pmcid": f"PMC{index}",
        "source_pmcid": source,
        "section": "Results",
        "section_bucket": "Results",
        "text": "text",
        "cue_score": 1,
        "cues": "comparison",
        "linked": "true" if index % 2 else "false",
        "source_claim_id": "clm" if index % 2 else None,
    }


def _pool(size: int = 400, sources: int = 80) -> list[dict]:
    return [_context(index, f"SRC{index % sources}") for index in range(size)]


def test_draw_excludes_wave1_and_respects_the_cap() -> None:
    pool = _pool()
    used = {row["ctx_id"] for row in pool[:150]}
    chosen, pool_size = draw_wave2(pool, used, size=150)

    assert pool_size == len(pool) - len(used)
    assert len(chosen) == 150
    assert not ({row["ctx_id"] for row in chosen} & used)
    per_source: dict[str, int] = {}
    for row in chosen:
        per_source[row["source_pmcid"]] = per_source.get(row["source_pmcid"], 0) + 1
    assert max(per_source.values()) <= 8


def test_draw_is_deterministic() -> None:
    pool = _pool()
    first, _ = draw_wave2(pool, set(), size=150)
    second, _ = draw_wave2(pool, set(), size=150)
    assert [row["ctx_id"] for row in first] == [row["ctx_id"] for row in second]
    assert WAVE2_SEED != 20261119, "wave 2 must use its own stream"


def test_draw_rejects_a_pool_that_is_too_small() -> None:
    with pytest.raises(WaveError, match="wave 2 needs"):
        draw_wave2(_pool(size=20), set(), size=150)


def test_rows_carry_nominal_weight_and_inherited_split() -> None:
    pool = _pool()
    chosen, pool_size = draw_wave2(pool, set(), size=150)
    splits = {
        source: ("dev" if index % 2 else "test")
        for index, source in enumerate(sorted({row["source_pmcid"] for row in pool}))
    }
    rows = build_rows(chosen, splits, pool_size, size=150)

    assert len(rows) == 150
    assert rows[0]["row_id"] == "P3W2-001"
    for row in rows:
        assert row["frame"] == "uniform"
        assert row["stratum"] == "uniform"
        assert row["overlap"] == "false"
        assert row["split"] == splits[row["source_pmcid"]]
        assert row["weight"] == pytest.approx(round(pool_size / 150, 4))
        assert row["inclusion_prob"] == pytest.approx(round(150 / pool_size, 8))


def test_rows_are_sorted_by_split_then_source() -> None:
    pool = _pool()
    chosen, pool_size = draw_wave2(pool, set(), size=150)
    splits = {source: "dev" for source in {row["source_pmcid"] for row in pool}}
    rows = build_rows(chosen, splits, pool_size, size=150)
    keys = [(row["split"], row["source_pmcid"], row["ctx_id"]) for row in rows]
    assert keys == sorted(keys)


def test_wave1_ids_are_read_from_the_manifest(tmp_path: Path) -> None:
    path = tmp_path / "manifest.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["row_id", "ctx_id"])
        writer.writerow(["P3W1-001", "PMC1:p1:c1"])
    assert wave1_context_ids(path) == {"PMC1:p1:c1"}


def test_missing_wave1_manifest_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(WaveError, match="wave 1 manifest not found"):
        wave1_context_ids(tmp_path / "absent.csv")
