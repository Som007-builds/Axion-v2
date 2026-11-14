"""Tests for the P1-07 feasibility spike helpers (no live calls)."""

from __future__ import annotations

from scripts.feasibility_spike import (
    CANDIDATES,
    CategoryResult,
    SourcePaper,
    count_source_contexts,
    estimate,
    normalize_title,
    reference_matches,
    render,
    resolve_by_dois,
    seeded_pairs,
)

from axion.ingest.europepmc import EuropePmcRecord, SearchPage
from axion.parse.jats import CitationContext, ParsedPaper, Reference


def _source(
    doi: str | None = "10.1000/source",
    pmid: str = "999",
    title: str = "A Landmark Trial of Drug X",
    year: int | None = 2020,
) -> SourcePaper:
    return SourcePaper(
        record_id="1",
        doi=doi,
        pmid=pmid,
        pmcid="PMC999",
        title=title,
        year=year,
        cited_by_count=10,
    )


def _context(ref_id: str, index: int = 0) -> CitationContext:
    return CitationContext(
        context_id=f"c{index}",
        paragraph_index=0,
        sentence_index=index,
        text="Drug X reduced Y [1].",
        paragraph_text="Drug X reduced Y [1].",
        marker="1",
        ref_id=ref_id,
        resolved=True,
    )


def test_normalize_title() -> None:
    assert normalize_title("A  Landmark-Trial: Drug X!") == "a landmark trial drug x"
    assert normalize_title(None) == ""


def test_reference_matches_by_doi_pmid_title_and_rejects_mismatch() -> None:
    source = _source()
    assert reference_matches(Reference(ref_id="b1", doi="10.1000/SOURCE"), source)
    assert reference_matches(Reference(ref_id="b1", pmid="999"), source)
    assert reference_matches(
        Reference(ref_id="b1", title="A Landmark Trial of Drug X.", year=2021), source
    )
    assert not reference_matches(
        Reference(ref_id="b1", title="A Landmark Trial of Drug X.", year=2015), source
    )
    assert not reference_matches(Reference(ref_id="b1", doi="10.1000/other"), source)
    assert not reference_matches(Reference(ref_id="b1", title="Different paper"), source)


def test_reference_matches_doi_inside_citation_text() -> None:
    source = _source()
    reference = Reference(ref_id="b1", citation_text="Smith J. Trial. J Test. doi:10.1000/source.")
    assert reference_matches(reference, source)


def test_count_source_contexts_counts_only_matching_refs() -> None:
    source = _source()
    paper = ParsedPaper(
        paper_id="PMC1",
        references=(
            Reference(ref_id="b1", doi="10.1000/source"),
            Reference(ref_id="b2", doi="10.1000/other"),
        ),
        citation_contexts=(
            _context("b1", 0),
            _context("b2", 1),
            _context("b1", 2),
        ),
    )
    assert count_source_contexts(paper, source) == 2


def test_estimate_multiplies_measured_rates() -> None:
    result = CategoryResult(candidate=CANDIDATES[0])
    result.linkable = 1000
    result.sampled = 100
    result.oa_full_text = 50
    result.source_sample = [
        SourcePaper("1", "10.1/a", "1", "PMC1", "t", 2020, 0) for _ in range(20)
    ]
    result.citers_total = 200
    result.citers_measured = 100
    result.oa_citers = 40
    result.context_pairs = 10
    result.contexts_found = 15
    estimate(result, result.linkable)
    assert result.estimated_sources == 500
    assert result.oa_share == 0.4
    assert result.estimated_citers == 2000
    assert result.contexts_per_pair == 1.5
    assert result.estimated_contexts == 3000
    assert 0 < result.estimated_contexts_low < result.estimated_contexts
    assert result.estimated_contexts_high > result.estimated_contexts


def test_passes_requires_both_lower_bounds() -> None:
    result = CategoryResult(candidate=CANDIDATES[0])
    result.estimated_sources_low = 29
    result.estimated_contexts_low = 1000
    assert not result.passes
    result.estimated_sources_low = 30
    result.estimated_contexts_low = 299
    assert not result.passes
    result.estimated_contexts_low = 300
    assert result.passes


def test_seeded_pairs_is_deterministic() -> None:
    source = _source()
    pairs = [(source, str(index)) for index in range(50)]
    first = seeded_pairs(pairs, 10, 7)
    second = seeded_pairs(list(reversed(pairs)), 10, 7)
    assert [pair[1] for pair in first] == [pair[1] for pair in second]
    assert len(first) == 10


class FakeSearchClient:
    def __init__(self, records: list[EuropePmcRecord]) -> None:
        self.records = records
        self.queries: list[str] = []

    def search(self, query: str, *, page_size: int) -> SearchPage:
        self.queries.append(query)
        return SearchPage(
            query=query,
            records=tuple(self.records),
            hit_count=len(self.records),
            next_cursor_mark=None,
        )


def test_resolve_by_dois_batches_and_maps() -> None:
    record = EuropePmcRecord("PMC1", "1", "10.1000/a", "t", "j", 2020, True, True, 3)
    client = FakeSearchClient([record])
    found = resolve_by_dois(client, ["10.1000/a", "10.1000/b"])  # type: ignore[arg-type]
    assert found["10.1000/a"].pmcid == "PMC1"
    assert len(client.queries) == 1
    assert 'DOI:"10.1000/a"' in client.queries[0]


def test_render_marks_passing_candidate_and_chooses_best() -> None:
    weak = CategoryResult(candidate=CANDIDATES[0])
    weak.linkable = 100
    weak.estimated_sources = 40
    weak.estimated_sources_low = 31
    weak.estimated_contexts = 400
    weak.estimated_contexts_low = 310
    strong = CategoryResult(candidate=CANDIDATES[1])
    strong.linkable = 200
    strong.estimated_sources = 80
    strong.estimated_sources_low = 60
    strong.estimated_contexts = 900
    strong.estimated_contexts_low = 700
    report = render([weak, strong], seed=1)
    assert "yes" in report
    assert "**cardiovascular** is the proposed sub-topic" in report
    assert "**not** a joint confidence interval" in report
