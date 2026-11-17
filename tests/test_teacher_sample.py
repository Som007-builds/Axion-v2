"""Tests for the nested, gold-excluding teacher sample (P2-03a)."""

from __future__ import annotations

from pathlib import Path

import pytest

from axion.eval.cost_estimate import read_paper_id_file, sample_papers_excluding
from axion.ingest.corpus import CorpusPaper


def _paper(pmcid: str) -> CorpusPaper:
    return CorpusPaper(pmcid=pmcid, role="citer")


def _papers(count: int) -> list[CorpusPaper]:
    return [_paper(f"PMC{index:04d}") for index in range(count)]


def test_samples_are_nested_prefixes() -> None:
    papers = _papers(100)
    small = sample_papers_excluding(papers, 10, seed=7)
    large = sample_papers_excluding(papers, 40, seed=7)
    assert [paper.pmcid for paper in large[:10]] == [paper.pmcid for paper in small]


def test_excluded_papers_never_appear() -> None:
    papers = _papers(100)
    exclude = frozenset({f"PMC{index:04d}" for index in range(0, 100, 2)})
    drawn = sample_papers_excluding(papers, 40, seed=7, exclude=exclude)
    assert len(drawn) == 40
    assert not exclude & {paper.pmcid for paper in drawn}


def test_exclusion_does_not_shrink_the_draw() -> None:
    papers = _papers(50)
    exclude = frozenset({paper.pmcid for paper in papers[:20]})
    assert len(sample_papers_excluding(papers, 30, seed=7, exclude=exclude)) == 30


def test_draw_is_deterministic() -> None:
    papers = _papers(60)
    first = [paper.pmcid for paper in sample_papers_excluding(papers, 15, seed=11)]
    second = [paper.pmcid for paper in sample_papers_excluding(papers, 15, seed=11)]
    assert first == second


def test_ids_can_be_read_from_gold_csv() -> None:
    ids = read_paper_id_file(Path("eval/audit/claims_audit_v1.csv"))
    assert len(ids) == 45
    assert all(identifier.startswith("PMC") for identifier in ids)


def test_ids_can_be_read_from_processed_jsonl() -> None:
    path = Path("eval/silver/claims_v1/baseline_flashlite/papers_processed.jsonl")
    if not path.exists():
        pytest.skip("baseline labels are local-only")
    assert len(read_paper_id_file(path)) == 100
