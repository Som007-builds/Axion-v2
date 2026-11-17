"""Offline tests for the P2-06 batching lever (no LLM call)."""

from __future__ import annotations

from axion.extract.baseline import PaperPlan
from axion.extract.batching import (
    BatchClaim,
    BatchExtraction,
    attribute,
    plan_batches,
    render_batch_prompt,
)
from axion.extract.claims import BaselineDocument, BaselineSection
from axion.ingest.corpus import CorpusPaper


def _plan(pmcid: str, text: str = "The drug reduced mortality by 30%.") -> PaperPlan:
    document = BaselineDocument(
        paper_id=pmcid,
        paper_title=f"Paper {pmcid}",
        sections=(BaselineSection(label="Results", path=("Results",), text=text),),
    )
    return PaperPlan(
        paper=CorpusPaper(pmcid=pmcid, role="citer"),
        document=document,
        prompt="",
        prompt_tokens_estimate=0,
    )


def _claim(paper_id: str, span: str = "The drug reduced mortality by 30%.") -> BatchClaim:
    return BatchClaim(
        paper_id=paper_id,
        claim_text="The drug reduced mortality.",
        section="Results",
        evidence_span=span,
    )


def test_render_includes_every_paper_delimiter() -> None:
    prompt = render_batch_prompt([_plan("PMC1"), _plan("PMC2")], max_claims=5)
    assert "=== PAPER PMC1 ===" in prompt
    assert "=== PAPER PMC2 ===" in prompt
    assert "at most 5 claims **per paper**" in prompt


def test_batches_respect_the_batch_size() -> None:
    plans = [_plan(f"PMC{index}") for index in range(7)]
    groups = plan_batches(plans, batch_size=3)
    assert [len(group.plans) for group in groups] == [3, 3, 1]
    assert [paper for group in groups for paper in group.paper_ids] == [
        f"PMC{index}" for index in range(7)
    ]


def test_batches_split_on_the_token_ceiling() -> None:
    long_text = "x" * 4000
    plans = [_plan(f"PMC{index}", text=long_text) for index in range(3)]
    groups = plan_batches(plans, batch_size=10, max_batch_tokens=1500)
    assert len(groups) == 3


def test_attribute_routes_claims_to_their_paper() -> None:
    plans = [_plan("PMC1"), _plan("PMC2")]
    extraction = BatchExtraction(claims=[_claim("PMC1"), _claim("PMC2")])
    accepted, failures = attribute(extraction, plans)
    assert [claim.evidence_span for claim in accepted["PMC1"]] == [
        "The drug reduced mortality by 30%."
    ]
    assert len(accepted["PMC2"]) == 1
    assert failures == []


def test_claim_naming_a_paper_outside_the_batch_is_a_failure() -> None:
    plans = [_plan("PMC1")]
    extraction = BatchExtraction(claims=[_claim("PMC9")])
    accepted, failures = attribute(extraction, plans)
    assert accepted["PMC1"] == []
    assert [failure.reason for failure in failures] == ["unknown_paper"]


def test_span_from_the_wrong_paper_is_rejected() -> None:
    plans = [_plan("PMC1"), _plan("PMC2", text="Different sentence entirely.")]
    extraction = BatchExtraction(claims=[_claim("PMC2")])
    accepted, failures = attribute(extraction, plans)
    assert accepted["PMC2"] == []
    assert [failure.reason for failure in failures] == ["evidence_span_not_verbatim"]
