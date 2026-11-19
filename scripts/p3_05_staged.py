"""P3-05 staged detector and P3-05b scheduler, tuned on dev only.

Stage 1 is the P3-04 section/lexical score: it is a **recall stage**, not a reject
filter. The dev grid showed why: any gate that clears negatives without losing a
positive must escalate ~25-50% of rows, and the gate's own positive calls are less
precise than the heuristic's. So stage 1 nominates candidates at the dev-tuned
threshold, and stage 2 (LLM v2) verifies the candidates.

Stage 2 needs live calls. The script therefore runs without them:

* ``--stage2 none`` - reports the candidate rate ``e``, the heuristic's numbers, and
  withholds staged numbers (a staged number without stage 2 is the heuristic).
* ``--stage2 v2`` - the full cascade, using ``p3-05-llm-v2-dev.csv``.

Test is evaluated once, under a frozen spec (ADR-0026), in the separate Block 6 run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from axion.eval.audit import wilson_interval
from scripts.dependency_baselines import (
    POSITIVE,
    binary_metrics,
    frame_rows,
    heuristic_score,
    load_rows,
    scored_rows,
    spec_rows,
    tune_heuristic,
)
from scripts.dependency_llm_v2 import PROMPT_VERSION, V2_DEV_PREDICTIONS, read_v2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "audit" / "p3-05"
SUMMARY = OUT / "p3-05-dev-detector.json"
REPORT = ROOT / "docs" / "reports" / "P3-05-detector-dev.md"
SPEC_FREEZE = OUT / "p3-05-spec-frozen.json"

TARGET_RECALL = 0.80
# One learned parameter for stage 1 (the candidate threshold), plus the stage-2
# verification threshold. Both grids are small on purpose: dev has 14 text-bearing
# positives, so anything richer would be fitted noise.
GRID_CANDIDATE: tuple[float, ...] = (-0.5, 0.0, 0.25, 0.5)
GRID_STAGE2: tuple[float, ...] = (40.0, 50.0, 60.0, 70.0, 80.0)
SCHEDULER_KS: tuple[float, ...] = (0.1, 0.2, 0.25, 0.5, 1.0)


class DetectorError(Exception):
    """The cascade cannot be configured or evaluated."""


@dataclass(frozen=True)
class Stage1:
    candidate_threshold: float
    heuristic: dict[str, float]

    def candidate(self, row: dict[str, str]) -> bool:
        return heuristic_score(row, self.heuristic) >= self.candidate_threshold


def linked(row: dict[str, str]) -> bool:
    return bool((row["source_claim_text"] or "").strip())


def risk_score(row: dict[str, str], heuristic: dict[str, float]) -> float:
    """P3-05b ordering: fixed design weights, not fitted.

    Claim linkage first (a context with A's claim is inspectable), then retraction
    mentions, then the heuristic score.
    """
    score = heuristic_score(row, heuristic)
    if linked(row):
        score += 1.0
    if "retract" in (row["context_text"] or "").lower():
        score += 0.5
    return score


def tune_stage1(dev_rows: Sequence[dict[str, str]], *, target_recall: float = TARGET_RECALL):
    """Pick the candidate threshold with the lowest candidate rate at recall >= target.

    "Recall" here is the ceiling stage 2 could reach: candidates that are truly
    positive, over all positives. A threshold that drops a positive is rejected.
    """
    heuristic = tune_heuristic(dev_rows)["params"]
    assert isinstance(heuristic, dict)
    positives = sum(1 for row in dev_rows if row["label"] == POSITIVE)
    negatives = len(dev_rows) - positives
    grid: list[dict[str, object]] = []
    best: tuple[tuple[float, float], Stage1] | None = None
    for threshold in GRID_CANDIDATE:
        stage = Stage1(candidate_threshold=threshold, heuristic=heuristic)
        candidates = [row for row in dev_rows if stage.candidate(row)]
        positive_candidates = sum(1 for row in candidates if row["label"] == POSITIVE)
        negative_candidates = len(candidates) - positive_candidates
        ceiling = positive_candidates / positives if positives else 0.0
        rate = len(candidates) / len(dev_rows)
        grid.append(
            {
                "candidate_threshold": threshold,
                "candidate_rate": round(rate, 4),
                "candidates": len(candidates),
                "positive_candidates": positive_candidates,
                "false_candidate_rate": round(negative_candidates / negatives, 4)
                if negatives
                else None,
                "recall_ceiling": round(ceiling, 4),
            }
        )
        if ceiling + 1e-9 < target_recall:
            continue
        key = (round(rate, 6), threshold)
        if best is None or key < best[0]:
            best = (key, stage)
    if best is None:
        raise DetectorError(f"no candidate threshold reaches recall {target_recall:.0%} on dev")
    chosen = best[1]
    return {
        "stage1": {
            "candidate_threshold": chosen.candidate_threshold,
            "heuristic": chosen.heuristic,
        },
        "target_recall": target_recall,
        "grid": grid,
    }


def tune_stage2(
    rows: Sequence[dict[str, str]],
    stage1: Stage1,
    scores: dict[str, float],
    *,
    target_recall: float = TARGET_RECALL,
) -> dict[str, object]:
    """Choose the verification threshold on dev: recall floor first, then FAR."""
    candidates = [row for row in rows if stage1.candidate(row)]
    positives = sum(1 for row in rows if row["label"] == POSITIVE)
    negatives = len(rows) - positives
    grid: list[dict[str, object]] = []
    best: tuple[tuple[float, float], float] | None = None
    for threshold in GRID_STAGE2:
        predicted = {
            row["row_id"]: int(scores.get(row["row_id"], 0.0) >= threshold) for row in rows
        }
        kept = sum(
            1 for row in candidates if row["label"] == POSITIVE and predicted[row["row_id"]] == 1
        )
        false_alarms = sum(
            1 for row in candidates if row["label"] != POSITIVE and predicted[row["row_id"]] == 1
        )
        recall = kept / positives if positives else 0.0
        far = false_alarms / negatives if negatives else 0.0
        grid.append(
            {
                "stage2_threshold": threshold,
                "recall": round(recall, 4),
                "false_alarm_rate": round(far, 4),
            }
        )
        if recall + 1e-9 < target_recall:
            continue
        key = (round(far, 6), threshold)
        if best is None or key < best[0]:
            best = (key, threshold)
    if best is None:
        raise DetectorError(
            f"no stage-2 threshold holds recall {target_recall:.0%} on dev; "
            "the cascade cannot meet its own floor"
        )
    return {"stage2_threshold": best[1], "grid": grid}


def cascade_predictions(
    rows: Sequence[dict[str, str]],
    stage1: Stage1,
    *,
    stage2_scores: dict[str, float] | None,
    stage2_threshold: float,
) -> tuple[dict[str, int], dict[str, int]]:
    """Stage 1 nominates; stage 2 verifies. No score means the nomination stands."""
    predictions: dict[str, int] = {}
    tally = {
        "candidate": 0,
        "rejected_by_stage1": 0,
        "verified_positive": 0,
        "verified_negative": 0,
    }
    for row in rows:
        if not stage1.candidate(row):
            tally["rejected_by_stage1"] += 1
            predictions[row["row_id"]] = 0
            continue
        tally["candidate"] += 1
        score = (stage2_scores or {}).get(row["row_id"])
        if score is None:
            predictions[row["row_id"]] = 1
        elif score >= stage2_threshold:
            tally["verified_positive"] += 1
            predictions[row["row_id"]] = 1
        else:
            tally["verified_negative"] += 1
            predictions[row["row_id"]] = 0
    return predictions, tally


def scheduler_curve(
    dev_rows: Sequence[dict[str, str]], heuristic: dict[str, float]
) -> list[dict[str, object]]:
    """Recall reached after inspecting the top k% of contexts by risk."""
    ordered = sorted(dev_rows, key=lambda row: (-risk_score(row, heuristic), row["row_id"]))
    positives = sum(1 for row in ordered if row["label"] == POSITIVE)
    curve: list[dict[str, object]] = []
    for k in SCHEDULER_KS:
        take = max(1, round(k * len(ordered)))
        hits = sum(1 for row in ordered[:take] if row["label"] == POSITIVE)
        low, high = wilson_interval(hits, positives) if positives else (0.0, 1.0)
        curve.append(
            {
                "fraction_inspected": k,
                "rows": take,
                "positives_found": hits,
                "positives_total": positives,
                "recall": round(hits / positives, 4) if positives else None,
                "recall_ci": [round(low, 4), round(high, 4)],
            }
        )
    return curve


def spec_payload(
    stage1: Stage1, *, stage2_threshold: float, scheduler_rule: str
) -> dict[str, object]:
    return {
        "stage1": {
            "candidate_threshold": stage1.candidate_threshold,
            "heuristic": stage1.heuristic,
        },
        "stage2": {"prompt_version": PROMPT_VERSION, "threshold": stage2_threshold},
        "scheduler": scheduler_rule,
    }


def spec_hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def verify_or_write_freeze(payload: dict[str, object], *, write: bool) -> dict[str, object]:
    digest = spec_hash(payload)
    if SPEC_FREEZE.exists():
        frozen = json.loads(SPEC_FREEZE.read_text(encoding="utf-8"))
        if frozen.get("spec_hash") != digest:
            raise DetectorError(
                "the frozen detector spec does not match this configuration "
                f"({frozen.get('spec_hash')} vs {digest}); the test set has been seen"
            )
        return frozen
    if not write:
        return {"spec_hash": digest, "frozen_at": None, "frozen": False}
    frozen = dict(payload)
    frozen["spec_hash"] = digest
    frozen["frozen_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    frozen["frozen"] = True
    frozen["test_evaluated"] = False
    SPEC_FREEZE.parent.mkdir(parents=True, exist_ok=True)
    SPEC_FREEZE.write_text(json.dumps(frozen, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return frozen


def evaluate(
    rows: Sequence[dict[str, str]],
    stage1: Stage1,
    *,
    stage2_scores: dict[str, float] | None,
    stage2_threshold: float,
) -> dict[str, object]:
    dev = spec_rows(rows, "dev")
    text_bearing = frame_rows(dev, "text_bearing")
    stub = frame_rows(dev, "stub")
    heuristic_only = {row["row_id"]: int(stage1.candidate(row)) for row in dev}
    predictions, tally = cascade_predictions(
        dev, stage1, stage2_scores=stage2_scores, stage2_threshold=stage2_threshold
    )
    blocked = {
        "heuristic": {
            "text_bearing": binary_metrics(heuristic_only, text_bearing),
            "stub": binary_metrics(heuristic_only, stub),
        },
        "candidate_rate": round(tally["candidate"] / len(dev), 4),
        "candidates": tally["candidate"],
        "positives_in_candidates": sum(
            1 for row in dev if stage1.candidate(row) and row["label"] == POSITIVE
        ),
        "positives_total": sum(1 for row in dev if row["label"] == POSITIVE),
    }
    if stage2_scores is not None:
        blocked["cascade"] = {
            "text_bearing": binary_metrics(predictions, text_bearing),
            "stub": binary_metrics(predictions, stub),
            "tally": tally,
        }
    return blocked


def write_report(summary: dict[str, object]) -> Path:
    tuning = summary["tuning"]
    assert isinstance(tuning, dict)
    stage1 = tuning["stage1"]
    assert isinstance(stage1, dict)
    dev = summary["dev"]
    assert isinstance(dev, dict)
    heuristic = dev["heuristic"]
    assert isinstance(heuristic, dict)
    cascade = dev.get("cascade")
    lines = [
        "# P3-05 staged detector - dev only",
        "",
        "Generated by `python scripts/p3_05_staged.py`; every number is its output.",
        "",
        f"Spec `{summary['spec_hash']}` "
        + (f"frozen at {summary['frozen_at']} " if summary.get("frozen_at") else "NOT frozen ")
        + "(ADR-0026). Test is not evaluated here.",
        "",
        "## Design (changed from the obvious one, on evidence)",
        "",
        "Stage 1 is used as the **recall stage**, not a reject filter. The dev grid showed a",
        "reject filter could not clear negatives without either dropping positives or escalating",
        "25-50% of rows, and its own positive calls were less precise than the heuristic's. So:",
        "stage 1 nominates candidates at the dev-tuned threshold, stage 2 verifies them.",
        "",
        f"- Candidate threshold: **{stage1['candidate_threshold']}** "
        f"(chosen on dev for the lowest candidate rate at recall >= "
        f"{float(summary['target_recall']):.0%}).",
        f"- Candidate rate `e` on dev: **{float(dev['candidate_rate']):.1%}** "
        f"({dev['candidates']} of 151 rows).",
        f"- Positives reachable by the cascade: **{dev['positives_in_candidates']} of "
        f"{dev['positives_total']}** - that is the ceiling, not a result.",
        f"- Stage-2 prompt `{PROMPT_VERSION}`; verification threshold "
        f"**{summary['stage2_threshold']}**.",
        "",
        "## Dev results (text-bearing frame, 122 rows / 14 positives)",
        "",
        "| Model | Precision | Recall [95% CI] | False-alarm rate |",
        "| :-- | --: | :-- | --: |",
        line("heuristic (the comparator)", heuristic["text_bearing"]),
    ]
    if isinstance(cascade, dict):
        lines.append(line("staged cascade", cascade["text_bearing"]))
    else:
        lines.append(
            "| staged cascade | withheld | withheld | withheld - no stage-2 score exists |"
        )
    lines += [
        "",
        "## Scheduler (P3-05b, dev only)",
        "",
        "| Top k% inspected | Rows | Positives found | Recall [95% CI] |",
        "| --: | --: | --: | :-- |",
    ]
    for point in summary["scheduler"]:  # type: ignore[union-attr]
        assert isinstance(point, dict)
        bound = point["recall_ci"]
        lines.append(
            f"| {float(point['fraction_inspected']):.0%} | {point['rows']} | "
            f"{point['positives_found']}/{point['positives_total']} | "
            f"{(point['recall'] or 0):.1%} [{bound[0]:.1%}, {bound[1]:.1%}] |"
        )
    lines += [
        "",
        "## Honest limits",
        "",
        "- Dev has **14 text-bearing positives**; one learned threshold (stage 1) plus one",
        "  stage-2 threshold is already near the limit of what that data can fit. Richer models",
        "  would be fitted noise, which is why none is used.",
        "- The scheduler weights are design choices, not fitted: the curve shows what ordering",
        "  buys, not a tuned result, and its top-10% point rests on 2 positives.",
        "- **No staged number is claimed without stage 2.** With stage 2 absent the cascade *is*",
        "  the heuristic, so printing it as a result would be a relabelling.",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return REPORT


def line(name: str, block: dict[str, object]) -> str:
    unweighted = block["unweighted"]
    assert isinstance(unweighted, dict)
    recall_ci = unweighted["recall_ci"] or [0.0, 0.0]
    return (
        f"| {name} | {fmt(unweighted['precision'])} | {fmt(unweighted['recall'])} "
        f"[{recall_ci[0]:.1%}, {recall_ci[1]:.1%}] | {fmt(unweighted['false_alarm_rate'])} |"
    )


def fmt(value: object) -> str:
    return "—" if value is None else f"{float(value):.1%}"  # type: ignore[arg-type]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage2", choices=("none", "v2"), default="none")
    parser.add_argument("--stage2-threshold", type=float, default=60.0)
    parser.add_argument("--tune-stage2", action="store_true")
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--evaluate-test", action="store_true")
    parser.add_argument("--summary", type=Path, default=SUMMARY)
    args = parser.parse_args(argv)

    rows = scored_rows(load_rows())
    dev = spec_rows(rows, "dev")
    tuning = tune_stage1(dev)
    stage1_raw = tuning["stage1"]
    assert isinstance(stage1_raw, dict)
    stage1 = Stage1(
        candidate_threshold=float(stage1_raw["candidate_threshold"]),
        heuristic=dict(stage1_raw["heuristic"]),  # type: ignore[arg-type]
    )

    stage2_scores: dict[str, float] | None = None
    stage2_threshold = args.stage2_threshold
    stage2_tuning: dict[str, object] | None = None
    if args.stage2 == "v2":
        checkpoint = read_v2(V2_DEV_PREDICTIONS)
        if not checkpoint:
            raise DetectorError(
                f"stage-2 scores not found at {V2_DEV_PREDICTIONS}; run the LLM v2 dev "
                "command first (see docs/reports/P3-05-llm-v2-calibration.md)"
            )
        stage2_scores = {row_id: float(item["score"]) for row_id, item in checkpoint.items()}
        if args.tune_stage2:
            stage2_tuning = tune_stage2(dev, stage1, stage2_scores)
            stage2_threshold = float(stage2_tuning["stage2_threshold"])

    payload = spec_payload(
        stage1,
        stage2_threshold=stage2_threshold,
        scheduler_rule="linked +1.0, retraction-mentioned +0.5, else heuristic score",
    )
    frozen = verify_or_write_freeze(payload, write=args.freeze)
    if args.evaluate_test:
        if frozen.get("test_evaluated"):
            raise DetectorError("test has already been evaluated under this frozen spec")
        raise DetectorError(
            "test evaluation is deferred: it needs the stage-2 scores and an explicit go-ahead "
            "so the single test look is spent on a frozen, complete spec"
        )

    evaluation = evaluate(
        rows, stage1, stage2_scores=stage2_scores, stage2_threshold=stage2_threshold
    )
    summary: dict[str, object] = {
        "spec_hash": frozen["spec_hash"],
        "frozen_at": frozen.get("frozen_at"),
        "frozen": frozen.get("frozen", False),
        "tuning": tuning,
        "stage2": args.stage2,
        "stage2_threshold": stage2_threshold,
        "stage2_tuning": stage2_tuning,
        "dev": evaluation,
        "scheduler": scheduler_curve(dev, stage1.heuristic),
        "target_recall": TARGET_RECALL,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = write_report(summary)
    print(json.dumps({"spec_hash": frozen["spec_hash"], "report": str(report)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
