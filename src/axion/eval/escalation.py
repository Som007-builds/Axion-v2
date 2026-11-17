"""Paper-level escalation policy for the P2 cost cascade.

The student is a CPU encoder; the teacher is the frozen P1 extraction run. The
cascade runs the student on every paper and sends a calibrated fraction of
papers to the small LLM (the teacher), then to the large LLM only when the small
LLM returns no accepted claim.

Calibration happened on the gold **dev** split only (P2-05). The confidence
features the phase originally expected (score mean, margin, entropy) did not
predict the student's per-paper retention; they were anti-predictive. Paper
length (sentence count) was the only signal that beat random escalation, so the
shipped rule is length risk, not confidence. The negative confidence result is
part of the evidence, not hidden.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

ESCALATION_FRACTION = 0.30
RISK_SIGNAL = "sentence_count"
POLICY_VERSION = "p2-05-length30-v1"


class EscalationError(Exception):
    """Raised when an escalation policy input is inconsistent."""


@dataclass(frozen=True)
class PaperRisk:
    """The measured signals and outcomes for one paper."""

    paper_id: str
    split: str
    sentences: int
    gold_rows: int
    student_retained: int
    baseline_claims: int
    baseline_cost_usd: float


def _half_up(value: float) -> int:
    return int(value + 0.5)


def select_escalations(
    risks: Sequence[PaperRisk], *, fraction: float = ESCALATION_FRACTION
) -> frozenset[str]:
    """Take the highest-risk fraction of papers, deterministically.

    The risk signal is the number of scorable sentences in the paper. Ties break
    on ``paper_id`` so a replay produces the same set. The fraction is applied
    per batch; the resulting escalation rate ``e`` is the realised count, not the
    requested fraction.
    """
    if not 0.0 < fraction <= 1.0:
        raise EscalationError("fraction must be in (0, 1]")
    if not risks:
        raise EscalationError("no papers to rank")
    count = max(1, _half_up(fraction * len(risks)))
    ordered = sorted(risks, key=lambda risk: (-risk.sentences, risk.paper_id))
    return frozenset(risk.paper_id for risk in ordered[:count])


def stage2_triggers(
    escalated: Sequence[str], accepted_claims: Mapping[str, int]
) -> tuple[str, ...]:
    """Papers that need the large LLM because the small LLM accepted nothing."""
    return tuple(sorted(paper for paper in escalated if accepted_claims.get(paper, 0) <= 0))


__all__ = [
    "ESCALATION_FRACTION",
    "POLICY_VERSION",
    "RISK_SIGNAL",
    "EscalationError",
    "PaperRisk",
    "select_escalations",
    "stage2_triggers",
]
