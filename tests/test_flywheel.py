"""Offline tests for P2-05b flywheel selection."""

from __future__ import annotations

import pytest

from axion.eval.flywheel import (
    FlywheelError,
    agreement_threshold,
    escalation_rate,
    select_low_agreement,
    split_pool,
)


def test_pool_split_is_disjoint_and_covers_everything() -> None:
    papers = [f"P{index:02d}" for index in range(40)]
    split = split_pool(papers)
    assert len(split.candidate) == 28
    assert len(split.heldout) == 12
    assert set(split.candidate).isdisjoint(split.heldout)
    assert set(split.candidate) | set(split.heldout) == set(papers)


def test_pool_split_is_deterministic() -> None:
    papers = [f"P{index:02d}" for index in range(40)]
    assert split_pool(papers) == split_pool(reversed(papers))


def test_threshold_selects_the_low_tail() -> None:
    scores = {f"P{index:02d}": float(index) for index in range(28)}
    threshold = agreement_threshold(scores, fraction=0.30)
    chosen = select_low_agreement(scores, threshold)
    assert len(chosen) == 8
    assert threshold == 7.0
    assert chosen == tuple(f"P{index:02d}" for index in range(8))


def test_escalation_rate_uses_the_frozen_threshold() -> None:
    scores = {"P1": 0.1, "P2": 0.2, "P3": 0.8, "P4": 0.9}
    assert escalation_rate(scores, 0.2) == 0.5
    assert escalation_rate(scores, 0.0) == 0.0


def test_validation() -> None:
    with pytest.raises(FlywheelError):
        split_pool(["P1"])
    with pytest.raises(FlywheelError):
        split_pool(["P1", "P2"], candidate_fraction=0.0)
    with pytest.raises(FlywheelError):
        agreement_threshold({}, fraction=0.3)
    with pytest.raises(FlywheelError):
        agreement_threshold({"P1": 0.1}, fraction=0.0)
    with pytest.raises(FlywheelError):
        agreement_threshold({"P1": float("nan")}, fraction=0.3)
    with pytest.raises(FlywheelError):
        escalation_rate({}, 0.3)
