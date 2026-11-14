"""Tests for the P1-06 coverage report (offline, synthetic inputs)."""

from __future__ import annotations

from pathlib import Path

import pytest
from scripts.retraction_coverage import (
    SampleRow,
    file_digest,
    render,
    resolve_sample,
    summarize_snapshot,
    wilson,
)

from axion.ingest.europepmc import (
    CitationPage,
    CitationRecord,
    EuropePmcRecord,
    EuropePmcResponseError,
)
from axion.ingest.retractions import RetractionIndex, load_retraction_watch_csv

FIXTURE = Path(__file__).parent / "fixtures" / "retraction-watch" / "synthetic.csv"


class FakeClient:
    def __init__(
        self,
        records: dict[str, EuropePmcRecord] | None = None,
        citation_counts: dict[str, int] | None = None,
        errors: set[str] | None = None,
    ) -> None:
        self.records = records or {}
        self.citation_counts = citation_counts or {}
        self.errors = errors or set()
        self.calls: list[str] = []

    def find_by_doi(self, doi: str) -> EuropePmcRecord | None:
        self.calls.append(f"doi:{doi}")
        if doi in self.errors:
            raise EuropePmcResponseError("boom")
        return self.records.get(doi)

    def find_by_pmid(self, pmid: str) -> EuropePmcRecord | None:
        self.calls.append(f"pmid:{pmid}")
        return self.records.get(pmid)

    def citations(self, pmid: str, *, page_size: int) -> CitationPage:
        count = self.citation_counts.get(pmid, 0)
        record = CitationRecord("MED", "1", "t", "j", 2024, 0)
        return CitationPage(pmid=pmid, records=(record,), hit_count=count)


def _record(
    doi: str | None = None, pmid: str | None = None, pmcid: str | None = None
) -> EuropePmcRecord:
    return EuropePmcRecord(
        pmcid=pmcid,
        pmid=pmid,
        doi=doi,
        title="t",
        journal_title="j",
        year=2020,
        is_open_access=True,
        has_full_text=True,
        cited_by_count=5,
    )


def test_summarize_snapshot_counts_fixture() -> None:
    records = load_retraction_watch_csv(FIXTURE)
    coverage = summarize_snapshot(records)
    assert coverage.total_rows == 5
    assert coverage.retractions == 3
    assert coverage.natures["Retraction"] == 3
    assert coverage.natures["Correction"] == 1
    assert coverage.with_doi == 4
    assert coverage.with_pmid == 3
    assert coverage.with_either == 4


def test_resolve_sample_is_seeded_and_tracks_availability() -> None:
    records = load_retraction_watch_csv(FIXTURE)
    client = FakeClient(
        records={
            "10.1000/alpha.1": _record(doi="10.1000/alpha.1", pmid="222", pmcid="PMC1"),
            "10.1000/delta.4": _record(doi="10.1000/delta.4", pmid="333", pmcid="PMC2"),
        },
        citation_counts={"222": 9, "333": 0},
    )
    first = resolve_sample(records, client, size=2, seed=5)  # type: ignore[arg-type]
    second = resolve_sample(
        records,
        FakeClient(records=client.records, citation_counts=client.citation_counts),
        size=2,
        seed=5,
    )  # type: ignore[arg-type]
    assert [row.record_id for row in first] == [row.record_id for row in second]
    resolved = [row for row in first if row.found]
    assert resolved
    assert all(row.in_epmc for row in resolved)
    assert any(row.citations_checked for row in resolved)


def test_resolve_sample_records_errors_not_as_missing() -> None:
    records = load_retraction_watch_csv(FIXTURE)
    client = FakeClient(errors={"10.1000/alpha.1"})
    rows = resolve_sample(records, client, size=2, seed=1, check_citations=False)  # type: ignore[arg-type]
    errors = [row for row in rows if row.error]
    assert len(errors) == 1
    assert errors[0].found is False


def test_resolve_sample_rejects_oversized_request() -> None:
    records = load_retraction_watch_csv(FIXTURE)
    with pytest.raises(ValueError, match="exceeds"):
        resolve_sample(records, FakeClient(), size=99, seed=1)  # type: ignore[arg-type]


def test_wilson_and_render() -> None:
    low, high = wilson(8, 10)
    assert 0 < low < 0.8 < high < 1

    coverage = summarize_snapshot(load_retraction_watch_csv(FIXTURE))
    coverage.sample = [
        SampleRow(
            record_id="1001",
            nature="Retraction",
            has_doi=True,
            has_pmid=True,
            found=True,
            pmcid="PMC1",
            is_open_access=True,
            in_epmc=True,
            pmid="222",
            cited_by_count=4,
            citations_checked=True,
        )
    ]
    report = render(
        coverage,
        snapshot_commit="abc",
        snapshot_date="2026-11-13",
        csv_sha256="0" * 64,
        csv_bytes=1234,
        sample_size=1,
        seed=1,
        live=True,
    )
    assert "Retraction Watch coverage (P1-06)" in report
    assert "CC0" in report
    assert "Found in Europe PMC | 1" in report
    assert "Median citations per checked record: **4**" in report
    assert "abc" in report


def test_file_digest(tmp_path: Path) -> None:
    path = tmp_path / "x.csv"
    path.write_bytes(b"abc")
    digest, size = file_digest(path)
    assert size == 3
    assert digest == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_index_from_snapshot_matches_loader() -> None:
    records = load_retraction_watch_csv(FIXTURE)
    assert len(RetractionIndex(records)) == len(records)
