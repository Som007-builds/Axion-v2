"""Tests for the Retraction Watch loader, index, and manifest."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from axion.ingest.retractions import (
    RetractionDataError,
    RetractionIndex,
    build_manifest,
    load_retraction_watch_csv,
    normalize_doi,
    normalize_pmid,
    write_manifest,
)

FIXTURE = Path(__file__).parent / "fixtures" / "retraction-watch" / "synthetic.csv"


def test_load_normalizes_rows() -> None:
    records = {record.record_id: record for record in load_retraction_watch_csv(FIXTURE)}
    assert set(records) == {"1001", "1002", "1003", "1004", "1006"}

    alpha = records["1001"]
    assert alpha.nature == "Retraction"
    assert alpha.is_retraction
    assert alpha.original_doi == "10.1000/alpha.1"
    assert alpha.original_pmid == "222"
    assert alpha.retraction_doi == "10.1000/retract.1"
    assert alpha.retraction_date == date(2021, 1, 2)
    assert alpha.original_date == date(2020, 12, 1)
    assert alpha.subjects == ("(HSC) Medicine - Oncology", "(HSC) Medicine - Pharmacology")
    assert alpha.reasons == ("Data Fabrication", "Concerns/Issues about Data")
    assert alpha.paywalled is False

    assert records["1002"].original_doi is None
    assert records["1002"].original_pmid is None
    assert records["1002"].paywalled is True
    assert records["1003"].nature == "Correction"
    assert not records["1003"].is_retraction
    assert records["1004"].original_doi == "10.1000/delta.4"
    assert records["1004"].retraction_doi == "10.1000/retract.4"
    assert records["1004"].paywalled is None
    assert records["1006"].original_pmid == "12345"


def test_duplicate_record_id_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "dupes.csv"
    text = FIXTURE.read_text(encoding="utf-8")
    lines = text.splitlines()
    path.write_text("\n".join([*lines, lines[1]]) + "\n", encoding="utf-8")
    with pytest.raises(RetractionDataError, match="duplicate Record ID"):
        load_retraction_watch_csv(path)


def test_missing_columns_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text("Record ID,Title\n1,x\n", encoding="utf-8")
    with pytest.raises(RetractionDataError, match="missing Retraction Watch columns"):
        load_retraction_watch_csv(path)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("10.1000/ABC", "10.1000/abc"),
        ("https://doi.org/10.1000/ABC", "10.1000/abc"),
        ("doi:10.1000/ABC", "10.1000/abc"),
        ("unavailable", None),
        ("Unavailable", None),
        ("0", None),
        ("", None),
    ],
)
def test_normalize_doi(raw: str, expected: str | None) -> None:
    assert normalize_doi(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("12345", "12345"), (" 42 ", "42"), ("0", None), ("", None), ("abc", None)],
)
def test_normalize_pmid(raw: str, expected: str | None) -> None:
    assert normalize_pmid(raw) == expected


def test_index_links_by_doi_pmid_and_both() -> None:
    index = RetractionIndex.from_csv(FIXTURE)
    assert len(index) == 5

    by_doi = index.link(doi="https://doi.org/10.1000/ALPHA.1")
    assert by_doi.is_retracted
    assert by_doi.matched_by == ("doi",)
    assert by_doi.records[0].record_id == "1001"

    by_pmid = index.link(pmid="12345")
    assert by_pmid.matched_by == ("pmid",)
    assert by_pmid.records[0].record_id == "1006"

    both = index.link(doi="10.1000/alpha.1", pmid="222")
    assert both.matched_by == ("doi", "pmid")
    assert not both.conflict
    assert [record.record_id for record in both.records] == ["1001"]

    assert not index.link(doi="10.9999/missing").is_retracted


def test_index_flags_conflicting_identifiers() -> None:
    index = RetractionIndex.from_csv(FIXTURE)
    conflict = index.link(doi="10.1000/alpha.1", pmid="12345")
    assert conflict.conflict
    assert {record.record_id for record in conflict.records} == {"1001", "1006"}


def test_index_links_pmcid_via_resolver() -> None:
    index = RetractionIndex.from_csv(FIXTURE)
    match = index.link_pmcid("PMC999", lambda pmcid: ("10.1000/alpha.1", None))
    assert match.records[0].record_id == "1001"
    assert not index.link_pmcid("PMC999", lambda pmcid: (None, None)).is_retracted


def test_manifest_is_id_only_and_deterministic(tmp_path: Path) -> None:
    records = load_retraction_watch_csv(FIXTURE)
    manifest = build_manifest(
        records,
        snapshot_commit="abc123",
        snapshot_date="2026-11-13",
        csv_sha256="0" * 64,
        csv_bytes=123,
        record_ids=[record.record_id for record in records],
    )
    assert manifest["rows"] == 5
    assert manifest["record_ids"] == ["1001", "1002", "1003", "1004", "1006"]
    assert manifest["natures"] == {"Correction": 1, "Expression of concern": 1, "Retraction": 3}
    assert "records" not in manifest
    serialized = json.dumps(manifest)
    assert "Alpha trial" not in serialized

    path = tmp_path / "manifest.json"
    write_manifest(path, manifest)
    first = path.read_text(encoding="utf-8")
    write_manifest(path, manifest)
    assert path.read_text(encoding="utf-8") == first
    assert json.loads(first)["licence"] == "CC0"
