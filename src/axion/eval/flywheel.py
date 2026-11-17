"""P2-05b flywheel selection: low-agreement papers become new silver labels.

The P2-05 escalation policy is length-based, so retraining cannot change its
escalation rate by construction. The flywheel therefore uses an **agreement**
signal on non-gold papers: a paper whose student output covers few of the
teacher's silver claims is a candidate for a new teacher label. The threshold is
calibrated on a candidate pool and measured on a disjoint held-out pool, so the
before/after escalation rate is not an in-sample artefact.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

FLYWHEEL_SEED = 20261118
CANDIDATE_FRACTION = 0.70
ESCALATION_FRACTION = 0.30


class FlywheelError(Exception):
    """Raised when flywheel inputs are inconsistent."""


@dataclass(frozen=True)
class PoolSplit:
    candidate: tuple[str, ...]
    heldout: tuple[str, ...]


def split_pool(
    papers: Iterable[str],
    *,
    seed: int = FLYWHEEL_SEED,
    candidate_fraction: float = CANDIDATE_FRACTION,
) -> PoolSplit:
    """Split paper IDs into a calibration pool and a disjoint held-out pool."""
    if not 0.0 < candidate_fraction < 1.0:
        raise FlywheelError("candidate_fraction must be in (0, 1)")
    unique = sorted(set(papers))
    if len(unique) < 2:
        raise FlywheelError("need at least two papers")
    shuffled = list(unique)
    random.Random(seed).shuffle(shuffled)
    count = max(1, min(len(unique) - 1, int(len(unique) * candidate_fraction + 0.5)))
    return PoolSplit(
        candidate=tuple(sorted(shuffled[:count])),
        heldout=tuple(sorted(shuffled[count:])),
    )


def agreement_threshold(
    scores: Mapping[str, float], *, fraction: float = ESCALATION_FRACTION
) -> float:
    """Threshold at the requested low tail of the candidate agreement scores.

    Ties can make the realised selection larger than ``fraction``; the realised
    rate is always reported as ``e``.
    """
    if not 0.0 < fraction <= 1.0:
        raise FlywheelError("fraction must be in (0, 1]")
    if not scores:
        raise FlywheelError("no agreement scores")
    values = sorted(float(value) for value in scores.values())
    if not all(math.isfinite(value) for value in values):
        raise FlywheelError("agreement scores must be finite")
    count = max(1, int(len(values) * fraction + 0.5))
    return values[count - 1]


def select_low_agreement(scores: Mapping[str, float], threshold: float) -> tuple[str, ...]:
    """Deterministically select the papers at or below the threshold."""
    return tuple(sorted(paper for paper, value in scores.items() if float(value) <= threshold))


def escalation_rate(scores: Mapping[str, float], threshold: float) -> float:
    """Share of papers the frozen threshold would escalate."""
    if not scores:
        raise FlywheelError("no agreement scores")
    return len(select_low_agreement(scores, threshold)) / len(scores)


__all__ = [
    "CANDIDATE_FRACTION",
    "ESCALATION_FRACTION",
    "FLYWHEEL_SEED",
    "FlywheelError",
    "PoolSplit",
    "agreement_threshold",
    "escalation_rate",
    "select_low_agreement",
    "split_pool",
]
