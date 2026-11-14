"""Unit tests for the committed-artifact corpus link coverage summary."""

from __future__ import annotations

from scripts.corpus_coverage import link_coverage

from axion.ingest.corpus import CorpusCite, CorpusPaper


def test_link_coverage_counts_isolated_sources_and_citers() -> None:
    papers = [
        CorpusPaper(pmcid="PMC1", role="source"),
        CorpusPaper(pmcid="PMC2", role="source"),
        CorpusPaper(pmcid="PMC3", role="citer"),
        CorpusPaper(pmcid="PMC4", role="citer"),
        CorpusPaper(pmcid="PMC5", role="source"),
    ]
    cites = [
        CorpusCite(citer_pmcid="PMC3", source_pmcid="PMC1", contexts=1),
        CorpusCite(citer_pmcid="PMC5", source_pmcid="PMC2", contexts=1),
    ]

    assert link_coverage(papers, cites) == {
        "source_papers_with_incoming_edge": 2,
        "source_papers_without_incoming_edge": 1,
        "citer_papers_with_outgoing_edge": 2,
        "citer_papers_without_outgoing_edge": 1,
        "papers_without_any_edge": 1,
        "dual_role_papers_with_outgoing_edge": 1,
    }
