"""Offline tests for the P1-10 dry-run estimate helpers."""

from __future__ import annotations

from axion.eval.cost_estimate import (
    PaperTextStats,
    estimate_tokens,
    paper_text_stats,
    papers_for_claims,
    sample_papers,
    summarize,
    usd_cost,
)
from axion.ingest.corpus import CorpusPaper
from axion.parse.jats import Paragraph, ParsedPaper


def _paper(pmcid: str) -> CorpusPaper:
    return CorpusPaper(pmcid=pmcid, pmid=None, doi=None, role="citer")


def test_sample_is_seeded_paper_level_and_covers_short_inputs() -> None:
    papers = [_paper(f"PMC{index:03d}") for index in range(20)]
    first = sample_papers(papers, 5, seed=7)
    assert first == sample_papers(papers, 5, seed=7)
    assert len(first) == 5
    assert len({paper.pmcid for paper in first}) == 5
    assert sample_papers(papers, 50, seed=7) == papers


def test_paper_stats_counts_parsed_text_not_references() -> None:
    parsed = ParsedPaper(
        pmcid="PMC1",
        paragraphs=(
            Paragraph(index=0, text="First sentence. Second sentence!"),
            Paragraph(index=1, text="A third one?"),
        ),
    )
    stats = paper_text_stats(parsed)
    assert stats.chars == len("First sentence. Second sentence!\nA third one?")
    assert stats.words == 7
    assert stats.sentences == 3
    assert stats.tokens == 12


def test_summary_and_token_estimate_are_deterministic() -> None:
    stats = [
        PaperTextStats("PMC1", 2, 3, 400, 80, 4, 1),
        PaperTextStats("PMC2", 3, 4, 800, 160, 8, 2),
    ]
    summary = summarize(stats)
    assert summary.tokens_mean == 150
    assert summary.tokens_median == 150
    estimate = estimate_tokens(
        summary,
        papers=10,
        claims_per_paper=10,
        prompt_overhead_tokens=100,
        output_tokens_per_claim=50,
    )
    assert estimate.input_tokens == 150 * 10 + 100 * 10
    assert estimate.output_tokens == 10 * 10 * 50
    assert estimate.total_tokens == 2500 + 5000


def test_claims_sizing_and_cost_formula() -> None:
    assert papers_for_claims(200, 5, margin=1.5) == 60
    assert papers_for_claims(300, 10, margin=1.5) == 45
    summary = summarize([PaperTextStats("PMC1", 1, 1, 400, 80, 1, 0)])
    estimate = estimate_tokens(
        summary,
        papers=10,
        claims_per_paper=5,
        prompt_overhead_tokens=0,
        output_tokens_per_claim=100,
    )
    assert (
        usd_cost(estimate, input_usd_per_mtok=1.0, output_usd_per_mtok=2.0)
        == (1000 * 1.0 + 5000 * 2.0) / 1_000_000
    )
