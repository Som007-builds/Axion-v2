"""Offline tests for the P1-08 corpus models, checkpoints, and citation matching."""

from __future__ import annotations

from pathlib import Path

import pytest

from axion.ingest.corpus import (
    CorpusCite,
    CorpusConfigError,
    CorpusPaper,
    JsonlCheckpoint,
    canonical_config_sha256,
    load_corpus_config,
    read_cites_csv,
    read_papers_csv,
    sha256_file,
    write_cites_csv,
    write_papers_csv,
)
from axion.ingest.corpus_pipeline import (
    build_edges,
    citer_papers,
    fetch_citations,
    resolve_sources,
    run_ingest,
    select_citers,
    source_papers,
)
from axion.ingest.europepmc import (
    CitationPage,
    CitationRecord,
    EuropePmcRecord,
    SearchPage,
)
from axion.ingest.retractions import RetractionRecord
from axion.link.citations import SourceIndex, SourceTarget
from axion.parse.jats import CitationContext, ParsedPaper, Reference

CONFIG = Path("src/axion/config/corpus/infectious-disease.yaml")

SOURCE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <journal-meta><journal-title-group><journal-title>J</journal-title></journal-title-group></journal-meta>
    <article-meta>
      <article-id pub-id-type="pmcid">PMC1</article-id>
      <article-id pub-id-type="pmid">42</article-id>
      <article-id pub-id-type="doi">10.1000/source</article-id>
      <title-group><article-title>Source Paper</article-title></title-group>
      <pub-date><year>2020</year></pub-date>
    </article-meta>
  </front>
  <body><sec><p>The trial reported a large effect.</p></sec></body>
</article>
"""

CITER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <journal-meta><journal-title-group><journal-title>J2</journal-title></journal-title-group></journal-meta>
    <article-meta>
      <article-id pub-id-type="pmcid">PMC2</article-id>
      <article-id pub-id-type="pmid">43</article-id>
      <article-id pub-id-type="doi">10.1000/citer</article-id>
      <title-group><article-title>Citing Paper</article-title></title-group>
      <pub-date><year>2022</year></pub-date>
    </article-meta>
  </front>
  <body><sec><p>The trial reported a large effect.
  The effect was robust <xref ref-type="bibr" rid="b1">1</xref>.</p></sec></body>
  <back><ref-list><ref id="b1"><label>1</label><element-citation>
    <article-title>Source Paper</article-title><year>2020</year>
    <pub-id pub-id-type="doi">10.1000/source</pub-id>
  </element-citation></ref></ref-list></back>
</article>
"""


def _context(ref_id: str, index: int = 0) -> CitationContext:
    return CitationContext(
        context_id=f"c{index}",
        paragraph_index=0,
        sentence_index=index,
        text="A prior trial reported this [1].",
        paragraph_text="A prior trial reported this [1].",
        marker="1",
        ref_id=ref_id,
        resolved=True,
    )


def _record(**overrides: object) -> EuropePmcRecord:
    values: dict[str, object] = {
        "pmcid": "PMC1",
        "pmid": "42",
        "doi": "10.1000/source",
        "title": "A Landmark Trial of Drug X",
        "journal_title": "Test Journal",
        "year": 2020,
        "is_open_access": True,
        "has_full_text": True,
        "cited_by_count": 9,
    }
    values.update(overrides)
    return EuropePmcRecord(**values)  # type: ignore[arg-type]


def test_config_is_total_corpus_and_configurable() -> None:
    config = load_corpus_config(CONFIG)
    assert config.corpus_id == "infectious-disease-v1"
    assert config.retraction_subject == "(HSC) Medicine - Infectious Disease"
    assert config.cap == 5000
    assert canonical_config_sha256(config) == canonical_config_sha256(config)


def test_invalid_config_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("corpus_id: x\n", encoding="utf-8")
    with pytest.raises(CorpusConfigError):
        load_corpus_config(path)


def test_checkpoint_resumes_and_ignores_a_partial_trailing_line(tmp_path: Path) -> None:
    path = tmp_path / "state.jsonl"
    checkpoint = JsonlCheckpoint(path, "id")
    checkpoint.append([{"id": "a", "value": 1}, {"id": "b", "value": 2}])
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"id": "c"')

    rows = JsonlCheckpoint(path, "id").load()
    assert set(rows) == {"a", "b"}
    assert rows["a"]["value"] == 1


def test_id_only_csv_round_trip(tmp_path: Path) -> None:
    papers = [
        CorpusPaper(pmcid="PMC1", pmid="42", doi="10.1/x", role="source", rw_record_ids=("7",)),
        CorpusPaper(pmcid="PMC2", pmid="43", doi=None, role="citer"),
    ]
    papers_path = tmp_path / "papers.csv"
    assert write_papers_csv(papers_path, papers) == 2
    assert read_papers_csv(papers_path) == papers

    cites = [CorpusCite(citer_pmcid="PMC2", source_pmcid="PMC1", contexts=3)]
    cites_path = tmp_path / "cites.csv"
    assert write_cites_csv(cites_path, cites) == 1
    assert read_cites_csv(cites_path) == cites
    assert len(sha256_file(cites_path)) == 64


def test_source_index_matches_doi_pmid_and_title_and_counts_contexts() -> None:
    index = SourceIndex(
        [
            SourceTarget("A", "10.1/a", "1", "Paper A", 2020),
            SourceTarget("B", None, "2", "Paper B", 2021),
            SourceTarget("C", None, None, "Paper C", 2019),
        ]
    )
    paper = ParsedPaper(
        references=(
            Reference(ref_id="r1", doi="10.1/A"),
            Reference(ref_id="r2", pmid="2"),
            Reference(ref_id="r3", title="Paper C.", year=2020),
            Reference(ref_id="r4", title="Unknown"),
        ),
        citation_contexts=(
            _context("r1", 0),
            _context("r1", 1),
            _context("r2", 2),
            _context("r3", 3),
            _context("r4", 4),
        ),
    )
    assert index.count_contexts(paper) == {"A": 2, "B": 1, "C": 1}


def test_source_index_rejects_ambiguous_titles_and_mismatched_ids() -> None:
    index = SourceIndex(
        [
            SourceTarget("A", "10.1/a", "1", "Same title", 2020),
            SourceTarget("B", "10.1/b", "2", "Same title", 2020),
        ]
    )
    assert index.match(Reference(ref_id="r1", title="Same title", year=2020)) is None
    assert index.match(Reference(ref_id="r1", doi="10.1/a")) == "A"
    assert index.match(Reference(ref_id="r1", doi="10.1/nope", title="Same title")) is None


def test_source_index_finds_doi_inside_citation_text() -> None:
    index = SourceIndex([SourceTarget("A", "10.1000/a", None, "Paper A", 2020)])
    reference = Reference(ref_id="r1", citation_text="Smith J. Trial. J Test. doi:10.1000/a.")
    assert index.match(reference) == "A"


def test_citer_cap_is_deterministic_and_reports_truncation() -> None:
    citers = {
        "PMC10": type("C", (), {"pmcid": "PMC10", "pmid": "10"})(),
        "PMC11": type("C", (), {"pmcid": "PMC11", "pmid": "11"})(),
    }
    edges = {"PMC10": {"PMC1"}, "PMC11": {"PMC2"}}
    included, truncated = select_citers(citers, edges, {"PMC1": 0, "PMC2": 1}, cap=3)
    assert [citer.pmcid for citer in included] == ["PMC10"]
    assert [citer.pmcid for citer in truncated] == ["PMC11"]


class _FakeClient:
    def __init__(self) -> None:
        self.search_calls = 0
        self.citation_calls = 0

    def search(self, query: str, *, page_size: int = 25, **_: object) -> SearchPage:
        self.search_calls += 1
        if query.startswith("EXT_ID:"):
            return SearchPage(
                query=query,
                records=(_record(pmcid="PMC1", pmid="42"),),
                hit_count=1,
                next_cursor_mark=None,
            )
        return SearchPage(query=query, records=(_record(),), hit_count=1, next_cursor_mark=None)

    def citations(self, pmid: str, **_: object) -> CitationPage:
        self.citation_calls += 1
        return CitationPage(
            pmid=pmid,
            records=(
                CitationRecord(
                    source="MED",
                    identifier="43",
                    title="Citing paper",
                    journal_abbreviation="J",
                    pub_year=2022,
                    cited_by_count=1,
                ),
            ),
            hit_count=1,
        )


def _rw_record() -> RetractionRecord:
    return RetractionRecord(
        record_id="7",
        title="Retracted paper",
        journal="J",
        subjects=("(HSC) Medicine - Infectious Disease",),
        nature="Retraction",
        original_doi="10.1000/source",
        original_pmid="42",
        retraction_doi=None,
        retraction_pmid=None,
        retraction_date=None,
        original_date=None,
        reasons=("Fabrication",),
        paywalled=False,
    )


def test_source_resolution_resumes_without_repeating_requests(tmp_path: Path) -> None:
    client = _FakeClient()
    first = resolve_sources(client, [_rw_record()], tmp_path)  # type: ignore[arg-type]
    assert first["7"]["pmcid"] == "PMC1"
    calls_after_first = client.search_calls
    assert calls_after_first == 1

    second = resolve_sources(client, [_rw_record()], tmp_path)  # type: ignore[arg-type]
    assert second == first
    assert client.search_calls == calls_after_first


def test_citation_fetch_resumes_from_checkpoint(tmp_path: Path) -> None:
    client = _FakeClient()
    config = load_corpus_config(CONFIG)
    sources, *_ = source_papers(
        [_rw_record()],
        {
            "7": {
                "record_id": "7",
                "found": True,
                "pmcid": "PMC1",
                "pmid": "42",
                "doi": "10.1000/source",
                "title": "Retracted paper",
                "year": 2020,
                "is_open_access": True,
                "has_full_text": True,
                "cited_by_count": 1,
            }
        },
        filters=config.filters,
    )
    rows = fetch_citations(client, list(sources.values()), config, tmp_path)  # type: ignore[arg-type]
    assert rows["42"]["med_ids"] == ["43"]
    assert client.citation_calls == 1

    fetch_citations(client, list(sources.values()), config, tmp_path)  # type: ignore[arg-type]
    assert client.citation_calls == 1


def test_source_papers_filters_and_dedupes() -> None:
    config = load_corpus_config(CONFIG)
    rows = {
        "7": {
            "record_id": "7",
            "found": True,
            "pmcid": "PMC1",
            "pmid": "42",
            "doi": "10.1000/source",
            "title": "Retracted paper",
            "year": 2020,
            "is_open_access": True,
            "has_full_text": True,
            "cited_by_count": 1,
        }
    }
    sources, non_oa, no_ft, no_pmcid, _ = source_papers(
        [_rw_record(), _rw_record()], rows, filters=config.filters
    )
    assert len(sources) == 1
    assert sources["PMC1"].rw_record_ids == ("7",)
    assert (non_oa, no_ft, no_pmcid) == (0, 0, 0)


def test_build_edges_and_citer_filtering() -> None:
    config = load_corpus_config(CONFIG)
    med_ids = {"43", "44"}
    rows = {
        "43": {
            "pmid": "43",
            "found": True,
            "pmcid": "PMC2",
            "doi": "10.1000/citer",
            "is_open_access": True,
            "has_full_text": True,
        },
        "44": {
            "pmid": "44",
            "found": True,
            "pmcid": "PMC3",
            "doi": None,
            "is_open_access": False,
            "has_full_text": True,
        },
    }
    citers, resolved, not_found, non_oa, no_ft, no_pmcid = citer_papers(
        med_ids, rows, filters=config.filters
    )
    assert set(citers) == {"PMC2"}
    assert (resolved, not_found, non_oa, no_ft, no_pmcid) == (2, 0, 1, 0, 0)

    source = type("S", (), {"pmid": "42", "pmcid": "PMC1"})()
    edges = build_edges(
        {"PMC1": source},  # type: ignore[dict-item]
        {"42": {"med_ids": ["43", "44"]}},
        citers,
    )
    assert edges == {"PMC2": {"PMC1"}}


def test_citer_cap_counts_sources_in_the_total() -> None:
    citers = {
        "PMC10": type("C", (), {"pmcid": "PMC10", "pmid": "10"})(),
        "PMC11": type("C", (), {"pmcid": "PMC11", "pmid": "11"})(),
    }
    edges = {"PMC10": {"PMC1"}, "PMC11": {"PMC2"}}
    included, truncated = select_citers(citers, edges, {"PMC1": 0, "PMC2": 1}, cap=2)
    assert included == []
    assert [citer.pmcid for citer in truncated] == ["PMC10", "PMC11"]


def test_end_to_end_pipeline_is_resumable_and_deterministic(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    (cache / "fulltext").mkdir(parents=True)
    csv_path = tmp_path / "rw.csv"
    csv_path.write_text(
        "Record ID,Title,Journal,Subject,RetractionDate,RetractionDOI,"
        "RetractionPubMedID,OriginalPaperDate,OriginalPaperDOI,OriginalPaperPubMedID,"
        "RetractionNature,Reason,Paywalled\n"
        '7,"Retracted paper",J,"(HSC) Medicine - Infectious Disease",'
        "15/01/2021,10.1000/notice,,15/01/2020,10.1000/source,42,Retraction,Fabrication,No\n",
        encoding="utf-8",
    )
    manifest_path = tmp_path / "rw-manifest.json"
    import hashlib
    import json

    manifest_path.write_text(
        json.dumps(
            {
                "snapshot_commit": "abc",
                "snapshot_date": "2026-11-13",
                "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                "csv_bytes": csv_path.stat().st_size,
                "rows": 1,
            }
        ),
        encoding="utf-8",
    )

    class FakeClient:
        def __init__(self) -> None:
            self.cache_dir = cache
            self.citation_calls = 0

        def search(self, query: str, **_: object) -> SearchPage:
            if query.startswith("EXT_ID:"):
                record = _record(pmcid="PMC2", pmid="43", doi="10.1000/citer")
            else:
                record = _record()
            return SearchPage(query=query, records=(record,), hit_count=1, next_cursor_mark=None)

        def citations(self, pmid: str, **_: object) -> CitationPage:
            self.citation_calls += 1
            return CitationPage(
                pmid=pmid,
                records=(
                    CitationRecord(
                        source="MED",
                        identifier="43",
                        title="Citing paper",
                        journal_abbreviation="J",
                        pub_year=2022,
                        cited_by_count=1,
                    ),
                ),
                hit_count=1,
            )

        def fetch_full_text(self, pmcid: str) -> str:
            text = SOURCE_XML if pmcid == "PMC1" else CITER_XML
            (cache / "fulltext" / f"{pmcid}.xml").write_text(text, encoding="utf-8")
            return text

    client = FakeClient()
    kwargs = {
        "config_path": CONFIG,
        "rw_csv_path": csv_path,
        "rw_manifest_path": manifest_path,
        "work_dir": tmp_path / "work",
        "out_prefix": tmp_path / "out",
        "client": client,
        "base_url": "https://example.invalid",
        "max_sources": 1,
    }
    first = run_ingest(**kwargs)  # type: ignore[arg-type]
    calls = client.citation_calls
    second = run_ingest(**kwargs)  # type: ignore[arg-type]

    assert first.counts == second.counts
    assert first.files.papers_sha256 == second.files.papers_sha256
    assert first.files.cites_sha256 == second.files.cites_sha256
    assert first.counts.papers_total == 2
    assert first.counts.sources_total == 1
    assert first.counts.citers_included == 1
    assert first.counts.contexts_total == 1
    assert calls == 1
    assert client.citation_calls == calls
