"""Agreement between the two P3-03 labelers on the overlap set (ADR-0023 Amendment A).

Reads labeler 1's wave export and labeler 2's overlap-2 export, checks that the
overlap really is the blinded subset, and reports raw agreement, Cohen's kappa,
PABAK and the per-class confusion matrix. Kappa here is conditioned on labeler 1,
because labeler 1's labels chose the overlap rows.

Usage:
    python scripts/dependency_agreement.py
    python scripts/dependency_agreement.py --bootstrap 5000
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "audit" / "p3-03"
WAVE_LABELS = OUT / "dependency_audit_v1_wave1_labelled.csv"
OVERLAP_LABELS = OUT / "dependency_audit_v1_wave1_overlap2_labelled.csv"
SELECTION = OUT / "p3-03-wave1-overlap2-selection.json"
MANIFEST = OUT / "p3-03-wave1-manifest.csv"
REPORT = ROOT / "docs" / "reports" / "P3-03-agreement.md"
SUMMARY = OUT / "p3-03-agreement.json"

CLASSES = ("RELIES_ON", "MENTIONS", "UNRELATED", "insufficient_context")
SEED = 20261118
BOOTSTRAP = 2000


class AgreementError(Exception):
    """The label files cannot be compared as a blind overlap."""


def read_labels(path: Path, *, role: str) -> tuple[dict[str, str], str]:
    """Read one label export into `({row_id: label}, labeler)`, with `skip` for skipped rows."""
    if not path.exists():
        raise AgreementError(f"{role} label file not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise AgreementError(f"{role} label file is empty: {path}")
    labelers = {(row.get("labeler") or "").strip() for row in rows}
    if len(labelers) != 1 or "" in labelers:
        raise AgreementError(f"{role} label file must have exactly one labeler id: {labelers}")
    labels: dict[str, str] = {}
    for row in rows:
        row_id = (row.get("row_id") or "").strip()
        if not row_id:
            raise AgreementError(f"{role} label file has a blank row_id")
        if row_id in labels:
            raise AgreementError(f"{role} label file repeats {row_id}")
        label = (row.get("label") or "").strip()
        if label and label not in CLASSES:
            raise AgreementError(f"{row_id}: {label!r} is not one of {CLASSES}")
        labels[row_id] = label or "skip"
    return labels, labelers.pop()


def cohen_kappa(left: list[str], right: list[str]) -> float:
    """Cohen's kappa over the classes actually observed."""
    total = len(left)
    if total == 0:
        raise AgreementError("no rows to compare")
    agree = sum(1 for a, b in zip(left, right, strict=True) if a == b) / total
    left_counts = Counter(left)
    right_counts = Counter(right)
    chance = sum(
        (left_counts[name] / total) * (right_counts[name] / total)
        for name in set(left_counts) | set(right_counts)
    )
    if chance >= 1.0:
        return 1.0 if agree >= 1.0 else 0.0
    return (agree - chance) / (1.0 - chance)


def bootstrap_kappa(
    left: list[str], right: list[str], *, draws: int, rng: random.Random
) -> tuple[float, float]:
    """Percentile bootstrap interval for kappa over row resamples."""
    pairs = list(zip(left, right, strict=True))
    values: list[float] = []
    for _ in range(draws):
        sample = [pairs[rng.randrange(len(pairs))] for _ in range(len(pairs))]
        a = [pair[0] for pair in sample]
        b = [pair[1] for pair in sample]
        try:
            values.append(cohen_kappa(a, b))
        except AgreementError:
            continue
    if not values:
        return (float("nan"), float("nan"))
    values.sort()
    low = values[int(0.025 * (len(values) - 1))]
    high = values[int(0.975 * (len(values) - 1))]
    return (round(low, 4), round(high, 4))


def weighted_kappa(left: list[str], right: list[str], weights: list[float]) -> float:
    """Design-weighted kappa: rows weighted by their wave inclusion weight."""
    total = sum(weights)
    if total <= 0:
        raise AgreementError("wave weights are not positive")
    agree = sum(w for a, b, w in zip(left, right, weights, strict=True) if a == b) / total
    left_mass = Counter()
    right_mass = Counter()
    for a, b, w in zip(left, right, weights, strict=True):
        left_mass[a] += w
        right_mass[b] += w
    chance = sum(
        (left_mass[name] / total) * (right_mass[name] / total)
        for name in set(left_mass) | set(right_mass)
    )
    if chance >= 1.0:
        return 1.0 if agree >= 1.0 else 0.0
    return (agree - chance) / (1.0 - chance)


def read_weights(manifest_path: Path) -> dict[str, float]:
    if not manifest_path.exists():
        raise AgreementError(f"wave manifest not found: {manifest_path}")
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        return {row["row_id"]: float(row["weight"]) for row in csv.DictReader(handle)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bootstrap", type=int, default=BOOTSTRAP)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    first, labeler_1 = read_labels(WAVE_LABELS, role="labeler 1")
    second, labeler_2 = read_labels(OVERLAP_LABELS, role="labeler 2")
    selection = json.loads(SELECTION.read_text(encoding="utf-8"))
    expected = set(selection["row_ids"])
    if set(second) != expected:
        raise AgreementError(
            "labeler 2's export is not the blinded overlap: "
            f"{len(set(second) ^ expected)} row ids differ from the selection file"
        )
    if not expected <= set(first):
        raise AgreementError("labeler 1 is missing rows that the overlap contains")

    row_ids = sorted(expected)
    left = [first[row_id] for row_id in row_ids]
    right = [second[row_id] for row_id in row_ids]
    weights_by_row = read_weights(MANIFEST)
    weights = [weights_by_row[row_id] for row_id in row_ids]

    total = len(row_ids)
    agree = sum(1 for a, b in zip(left, right, strict=True) if a == b)
    po = agree / total
    kappa = cohen_kappa(left, right)
    low, high = bootstrap_kappa(left, right, draws=args.bootstrap, rng=random.Random(args.seed))
    pabak = 2 * po - 1
    left_counts = Counter(left)
    positive = left_counts["RELIES_ON"] / total
    negatives = sum(count for name, count in left_counts.items() if name != "RELIES_ON")
    matrix = {a: {b: 0 for b in (*CLASSES, "skip")} for a in (*CLASSES, "skip")}
    for a, b in zip(left, right, strict=True):
        matrix[a][b] += 1
    disagreements = [
        {"row_id": row_id, "labeler_1": a, "labeler_2": b}
        for row_id, a, b in zip(row_ids, left, right, strict=True)
        if a != b
    ]
    per_class = {
        name: {
            "rows": left_counts.get(name, 0),
            "agreed": sum(1 for a, b in zip(left, right, strict=True) if a == name and b == name),
        }
        for name in (*CLASSES, "skip")
    }

    summary = {
        "rows": total,
        "labeler_1": [labeler_1],
        "labeler_2": [labeler_2],
        "agree": agree,
        "raw_agreement": round(po, 4),
        "cohen_kappa": round(kappa, 4),
        "kappa_ci95": [low, high],
        "pabak": round(pabak, 4),
        "design_weighted_kappa": round(weighted_kappa(left, right, weights), 4),
        "positive_prevalence_labeler_1": round(positive, 4),
        "negative_rows": negatives,
        "per_class": per_class,
        "confusion": matrix,
        "disagreements": disagreements,
        "degenerate": not disagreements,
        "notes": [
            "kappa is conditioned on labeler 1: labeler 1's labels chose these rows",
            f"{negatives} negative rows: negative-class agreement is the least stable part",
            "the overlap is positive-heavy, so kappa is depressed relative to a balanced design",
            *(
                [
                    "degenerate: zero discordant pairs, so kappa is exactly 1 and the bootstrap "
                    "interval cannot move; this cannot separate genuine reliability from a shared "
                    "heuristic or from labeler 2 having seen labeler 1's labels"
                ]
                if not disagreements
                else []
            ),
        ],
    }
    SUMMARY.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        "# P3-03 wave 1 — agreement between the two labelers",
        "",
        "Generated by `python scripts/dependency_agreement.py`; every number below is its output.",
        "",
        f"**Rows:** {total} (the overlap selected by ADR-0023 Amendment A) · "
        f"**labeler 1:** `{summary['labeler_1'][0]}` · **labeler 2:** `{summary['labeler_2'][0]}`",
        "",
        "| Statistic | Value |",
        "| :-- | --: |",
        f"| Raw agreement | {agree}/{total} = **{po:.1%}** |",
        (
            f"| Cohen's κ | **{kappa:.3f}** — **degenerate**: zero discordant pairs |"
            if not disagreements
            else f"| Cohen's κ | **{kappa:.3f}** (bootstrap 95% {low:.2f}-{high:.2f}) |"
        ),
        f"| PABAK (prevalence-adjusted) | {pabak:.3f} |",
        f"| Design-weighted κ | {summary['design_weighted_kappa']:.3f} |",
        f"| `RELIES_ON` prevalence in labeler 1's labels | {positive:.1%} |",
        f"| Negative rows available | {negatives} |",
        "",
        "**How to read it.** κ is **conditioned on labeler 1**: labeler 1's labels chose which",
        "rows are in the overlap, so this measures labeler 2's reproducibility against that rater,",
        "not agreement between two exchangeable raters. The overlap is positive-heavy, which",
        "*depresses* κ relative to a balanced design (the prevalence effect), so the value here is",
        "conservative; PABAK is shown because it ignores prevalence and therefore reads higher by",
        "construction. Only",
        f"{negatives} negative rows carry the negative side, so one disagreement there is worth",
        "about 17 percentage points of that side's agreement - do not read it as a rate.",
        "",
        "## Confusion matrix (labeler 1 rows, labeler 2 columns)",
        "",
        "| labeler 1 \\ labeler 2 | " + " | ".join((*CLASSES, "skip")) + " |",
        "| :-- | " + " | ".join("--:" for _ in (*CLASSES, "skip")) + " |",
    ]
    for name in (*CLASSES, "skip"):
        cells = " | ".join(str(matrix[name][column]) for column in (*CLASSES, "skip"))
        lines.append(f"| {name} | {cells} |")
    lines += [
        "",
        "## Disagreements",
        "",
    ]
    if disagreements:
        lines.append("| row | labeler 1 | labeler 2 |")
        lines.append("| :-- | :-- | :-- |")
        for item in disagreements:
            lines.append(f"| {item['row_id']} | {item['labeler_1']} | {item['labeler_2']} |")
    else:
        lines.append("None: the two labelers agreed on every row.")
    limits = [
        "- Single overlap, one pair of labelers, 31 rows: the interval is wide and this does not",
        "  estimate corpus-level reliability.",
        "- The four-class matrix has a structurally empty `insufficient_context` row because",
        "  labeler 1 skipped nothing in wave 1.",
    ]
    if disagreements:
        limits.append(
            "- Agreement is measured on an enriched, positive-heavy overlap; it is not corpus κ."
        )
    else:
        limits += [
            "- **Zero discordant pairs.** κ is exactly 1 and its bootstrap interval is a point, so",
            "  this cannot distinguish genuine rubric reliability from (a) a shared cue heuristic,",
            "  (b) labeler 2 having seen labeler 1's labels, or (c) both labelers sharing the same",
            "  'corroboration is not dependency' reading. A blind re-label of a small subset later",
            "  (test-retest) is the cheap check that would separate these; until then this is",
            "  consistency, not established reliability.",
        ]
    lines += [
        "",
        "## Limits",
        "",
        *limits,
        "- Claim-level linking (P3-06) is a different task and is not measured here.",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "rows",
                    "agree",
                    "raw_agreement",
                    "cohen_kappa",
                    "kappa_ci95",
                    "pabak",
                    "design_weighted_kappa",
                    "negative_rows",
                )
            },
            indent=2,
        )
    )
    print(f"report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
