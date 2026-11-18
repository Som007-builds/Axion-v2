"""Offline tests for the P3-02 deterministic candidate generator."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from axion.ingest.corpus import CorpusCite, CorpusPaper
from axion.link.candidates import (
    CandidateError,
    build_candidates,
    load_candidates,
    source_claim_proxy_text,
    validate_source_counts,
)
from axion.parse.jats import parse_jats
from axion.store.memory import InMemoryGraph

SOURCE_ONE = """<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <journal-meta>
      <journal-title-group><journal-title>Test Journal</journal-title></journal-title-group>
    </journal-meta>
    <article-meta>
      <article-id pub-id-type="pmcid">PMC1</article-id>
      <article-id pub-id-type="pmid">42</article-id>
      <article-id pub-id-type="doi">10.1000/source1</article-id>
      <title-group><article-title>Source Paper One</article-title></title-group>
      <pub-date><year>2020</year></pub-date>
      <abstract><p>This source reported that treatment reduced mortality
      in the trial cohort by thirty percent.</p></abstract>
    </article-meta>
  </front>
  <body><sec><p>Source body text.</p></sec></body>
</article>
"""

SOURCE_TWO = """<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <journal-meta>
      <journal-title-group><journal-title>Test Journal</journal-title></journal-title-group>
    </journal-meta>
    <article-meta>
      <article-id pub-id-type="pmcid">PMC2</article-id>
      <article-id pub-id-type="pmid">43</article-id>
      <article-id pub-id-type="doi">10.1000/source2</article-id>
      <title-group><article-title>Source Paper Two</article-title></title-group>
      <pub-date><year>2021</year></pub-date>
      <abstract><p>The second source describes a different cohort
      and reports no mortality difference.</p></abstract>
    </article-meta>
  </front>
  <body><sec><p>Second source body text.</p></sec></body>
</article>
"""

CITER = """<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <journal-meta>
      <journal-title-group><journal-title>Citing Journal</journal-title></journal-title-group>
    </journal-meta>
    <article-meta>
      <article-id pub-id-type="pmcid">PMC3</article-id>
      <article-id pub-id-type="pmid">44</article-id>
      <article-id pub-id-type="doi">10.1000/citer</article-id>
      <title-group><article-title>Citing Paper</article-title></title-group>
      <pub-date><year>2022</year></pub-date>
    </article-meta>
  </front>
  <body><sec><p>Prior work found a mortality benefit
  <xref ref-type="bibr" rid="b1">1</xref> in the trial cohort.</p></sec></body>
  <back><ref-list><ref id="b1"><label>1</label><element-citation>
    <article-title>Source Paper One</article-title>
    <year>2020</year>
    <pub-id pub-id-type="doi">10.1000/source1</pub-id>
  </element-citation></ref></ref-list></back>
</article>
"""

PAPERS = [
    CorpusPaper(
        pmcid="PMC1", pmid="42", doi="10.1000/source1", role="source", rw_record_ids=("7",)
    ),
    CorpusPaper(
        pmcid="PMC2", pmid="43", doi="10.1000/source2", role="source", rw_record_ids=("8",)
    ),
    CorpusPaper(pmcid="PMC3", pmid="44", doi="10.1000/citer", role="citer"),
]
CITES = [
    CorpusCite(citer_pmcid="PMC3", source_pmcid="PMC1", contexts=1),
    CorpusCite(citer_pmcid="PMC3", source_pmcid="PMC2", contexts=0),
]


def _cache(tmp_path: Path) -> Path:
    cache = tmp_path / "cache"
    (cache / "fulltext").mkdir(parents=True, exist_ok=True)
    (cache / "fulltext" / "PMC1.xml").write_text(SOURCE_ONE, encoding="utf-8")
    (cache / "fulltext" / "PMC2.xml").write_text(SOURCE_TWO, encoding="utf-8")
    (cache / "fulltext" / "PMC3.xml").write_text(CITER, encoding="utf-8")
    return cache


def test_candidate_bundle_is_deterministic_and_reports_zero_context_sources(
    tmp_path: Path,
) -> None:
    first = build_candidates(PAPERS, CITES, cache_dir=_cache(tmp_path), expected_contexts=1)
    second = build_candidates(PAPERS, CITES, cache_dir=_cache(tmp_path), expected_contexts=1)

    assert first.context_rows == second.context_rows
    assert first.source_claim_rows == second.source_claim_rows
    assert first.source_counts == second.source_counts
    assert first.totals.candidate_contexts == 1
    assert first.totals.source_papers_with_citers == 2
    assert first.totals.source_papers_with_contexts == 1
    assert first.totals.source_papers_without_contexts == 1
    assert first.totals.citer_papers == 1
    assert first.totals.source_claim_proxies == 2
    assert first.totals.contexts_with_source_claim == 1
    assert first.totals.contexts_without_source_claim == 0
    assert first.context_rows[0]["source_pmcid"] == "PMC1"
    assert first.context_rows[0]["source_claim_id"] == "rule:PMC1:abstract:1"
    assert first.context_rows[0]["ctx_id"] == "PMC3:p0:c0"
    assert first.source_counts[0].source_pmcid == "PMC1"
    assert first.source_counts[0].candidate_contexts == 1
    assert first.source_counts[1].source_pmcid == "PMC2"
    assert first.source_counts[1].candidate_contexts == 0


def test_candidate_load_is_idempotent(tmp_path: Path) -> None:
    bundle = build_candidates(PAPERS, CITES, cache_dir=_cache(tmp_path), expected_contexts=1)
    graph = InMemoryGraph()

    first = load_candidates(bundle, graph=graph, run_id="p3-02-test")
    second = load_candidates(bundle, graph=graph, run_id="p3-02-test")

    assert first.graph_counts == second.graph_counts
    assert first.graph_counts["Paper"] == 3
    assert first.graph_counts["Claim"] == 2
    assert first.graph_counts["CitationContext"] == 1
    assert first.graph_counts["CITES"] == 2
    assert first.graph_counts["IN_PAPER"] == 1
    assert first.graph_counts["POINTS_TO"] == 1
    assert first.graph_counts["EXTRACTED_FROM"] == 2
    assert first.graph_counts["RETRACTED_BY"] == 2
    assert graph.contexts["PMC3:p0:c0"]["source_claim_id"] == "rule:PMC1:abstract:1"


def test_missing_source_abstract_leaves_candidate_unlinked(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    (cache / "fulltext" / "PMC1.xml").write_text(
        re.sub(r"\s*<abstract>.*?</abstract>", "", SOURCE_ONE, flags=re.DOTALL),
        encoding="utf-8",
    )

    bundle = build_candidates(PAPERS, CITES, cache_dir=cache, expected_contexts=1)

    assert bundle.context_rows[0]["source_claim_id"] == ""
    assert bundle.totals.source_claim_proxies == 1
    assert bundle.totals.contexts_with_source_claim == 0
    assert bundle.totals.contexts_without_source_claim == 1


def test_candidate_total_mismatch_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(CandidateError, match="candidate contexts 1 != manifest contexts_total 2"):
        build_candidates(PAPERS, CITES, cache_dir=_cache(tmp_path), expected_contexts=2)


def test_per_source_mismatch_fails_loudly(tmp_path: Path) -> None:
    bundle = build_candidates(PAPERS, CITES, cache_dir=_cache(tmp_path), expected_contexts=1)
    wrong = [CorpusCite(citer_pmcid="PMC3", source_pmcid="PMC1", contexts=2)]
    with pytest.raises(CandidateError, match="source context counts disagree"):
        validate_source_counts(wrong, bundle)


def test_source_claim_proxy_skips_background_and_withdrawn_sentences() -> None:
    paper = parse_jats(
        """<?xml version="1.0" encoding="UTF-8"?>
<article><front><article-meta>
<abstract><p>Background: this is not a substantive source claim for the proxy.
This article has been withdrawn and should not become a claim proxy.
The trial reported a thirty percent mortality reduction in the treated cohort.</p></abstract>
</article-meta></front><body><p>Body.</p></body></article>""",
        paper_id="PMCX",
    )

    assert source_claim_proxy_text(paper) == (
        "The trial reported a thirty percent mortality reduction in the treated cohort."
    )
