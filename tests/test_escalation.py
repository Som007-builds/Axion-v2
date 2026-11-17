"""Offline tests for the P2 escalation policy."""

from __future__ import annotations

import pytest

from axion.eval.escalation import (
    EscalationError,
    PaperRisk,
    select_escalations,
    stage2_triggers,
)


def _risk(paper_id: str, sentences: int, *, split: str = "dev") -> PaperRisk:
    return PaperRisk(
        paper_id=paper_id,
        split=split,
        sentences=sentences,
        gold_rows=1,
        student_retained=0,
        baseline_claims=1,
        baseline_cost_usd=0.01,
    )


def test_selects_the_longest_fraction() -> None:
    risks = [_risk(f"P{index}", index) for index in range(1, 11)]
    chosen = select_escalations(risks, fraction=0.3)
    assert chosen == frozenset({"P8", "P9", "P10"})


def test_ties_break_on_paper_id() -> None:
    risks = [_risk("P2", 5), _risk("P1", 5), _risk("P3", 1)]
    assert select_escalations(risks, fraction=0.67) == frozenset({"P1", "P2"})


def test_fraction_is_applied_half_up() -> None:
    risks = [_risk(f"P{index}", index) for index in range(1, 23)]  # 22 papers
    chosen = select_escalations(risks, fraction=0.3)  # 6.6 -> 7
    assert len(chosen) == 7
    assert "P22" in chosen


def test_single_paper_is_always_escalated() -> None:
    assert select_escalations([_risk("P1", 3)], fraction=0.01) == frozenset({"P1"})


def test_fraction_is_validated() -> None:
    with pytest.raises(EscalationError):
        select_escalations([_risk("P1", 3)], fraction=0.0)
    with pytest.raises(EscalationError):
        select_escalations([_risk("P1", 3)], fraction=1.5)


def test_empty_input_is_rejected() -> None:
    with pytest.raises(EscalationError):
        select_escalations([], fraction=0.3)


def test_stage2_triggers_only_on_zero_accepted_claims() -> None:
    escalated = ("P1", "P2", "P3")
    assert stage2_triggers(escalated, {"P1": 2, "P2": 0, "P3": 1}) == ("P2",)
    assert stage2_triggers(escalated, {"P1": 1, "P2": 1, "P3": 1}) == ()
