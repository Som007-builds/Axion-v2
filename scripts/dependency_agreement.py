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

from axion.eval.audit import wilson_interval

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "audit" / "p3-03"
WAVE_LABELS = OUT / "dependency_audit_v1_wave1_labelled.csv"
OVERLAP_LABELS = OUT / "dependency_audit_v1_wave1_overlap2_labelled.csv"
SELECTION = OUT / "p3-03-wave1-overlap2-selection.json"
MANIFEST = OUT / "p3-03-wave1-manifest.csv"
REPORT = ROOT / "docs" / "reports" / "P3-03-agreement.md"
SUMMARY = OUT / "p3-03-agreement.json"

WAVE2_LABELS = OUT / "dependency_audit_v1_wave2_labelled.csv"
WAVE2_OVERLAP_LABELS = (
    ROOT / "eval" / "audit" / "p3-03-labeler2" / "dependency_audit_v1_wave2_overlap2_labelled.csv"
)
WAVE2_SELECTION = OUT / "p3-03-wave2-overlap2-selection.json"
WAVE2_MANIFEST = OUT / "p3-03-wave2-manifest.csv"
WAVE2_REPORT = ROOT / "docs" / "reports" / "P3-03-wave2-agreement.md"
WAVE2_SUMMARY = OUT / "p3-03-wave2-agreement.json"

CLASSES = ("RELIES_ON", "MENTIONS", "UNRELATED", "insufficient_context")
NEGATIVE_FLOOR = 15  # ADR-0023 Amendment C: below this, negative-side kappa is not estimable
OWNER_PACE_S = 38.0  # owner-reported wave-2 pace (95 min / 150 rows)
SECOND_PACE_S = 120.0  # labeler-2 reported pace (60 min / 30 rows)
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


def negative_side(
    left: dict[str, str], right: dict[str, str], row_ids: list[str]
) -> dict[str, object]:
    """Agreement restricted to labeler 1's negative rows.

    Two different questions, both worth reporting separately:

    * a 3-class kappa over the negative classes (does each labeler place a
      negative in the same negative class?), and
    * specificity agreement (does labeler 2 leave the row negative at all?), with a
      Wilson interval, which is the number a downstream rule actually consumes.
    """
    neg_ids = [row_id for row_id in row_ids if left[row_id] != "RELIES_ON"]
    if not neg_ids:
        return {"rows": 0, "kappa": None, "specificity": None, "specificity_ci": None}
    neg_left = [left[row_id] for row_id in neg_ids]
    neg_right = [right[row_id] for row_id in neg_ids]
    kappa = cohen_kappa(neg_left, neg_right) if len(neg_ids) > 1 else None
    stay_negative = sum(1 for label in neg_right if label != "RELIES_ON")
    low, high = wilson_interval(stay_negative, len(neg_ids))
    return {
        "rows": len(neg_ids),
        "kappa": None if kappa is None else round(kappa, 4),
        "specificity": round(stay_negative / len(neg_ids), 4),
        "specificity_ci": [round(low, 4), round(high, 4)],
        "called_positive_by_labeler_2": len(neg_ids) - stay_negative,
        "classes_seen": sorted({*neg_left, *neg_right}),
    }


ALLOWED_HANDOFF_SUFFIXES = ("-blind.csv", "-labeler.html", "README.md")


def isolation_audit(
    overlap_labels: Path,
    selection: dict[str, object],
    *,
    labeler_1: str,
    labeler_2: str,
    owner_pace_s: float | None,
    second_pace_s: float | None,
    blind_path: Path | None,
) -> list[dict[str, str]]:
    """Check what the repository can actually show about labeler isolation.

    Each check records its evidence and a verdict of ``pass``, ``weak`` or
    ``fail``. Nothing here proves who a person is; it records what the files
    support, so the report does not imply more.
    """
    checks: list[dict[str, str]] = []

    distinct = bool(labeler_1) and bool(labeler_2) and labeler_1 != labeler_2
    checks.append(
        {
            "check": "labeler ids differ",
            "evidence": f"'{labeler_1}' vs '{labeler_2}'",
            "verdict": "pass" if distinct else "fail",
        }
    )

    parent = overlap_labels.parent.resolve()

    def shown(path: Path) -> str:
        return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)

    declared = str(selection.get("handoff_dir") or "")
    declared_path = (ROOT / declared).resolve() if declared else None
    matches = declared_path is not None and parent == declared_path
    checks.append(
        {
            "check": "export sits in the declared handoff directory",
            "evidence": (
                f"{shown(parent)} vs handoff_dir="
                f"{(declared.replace(chr(92), '/') or '(missing)')}"
            ),
            "verdict": "pass" if matches else "fail",
        }
    )

    stray: list[str] = []
    if parent.exists():
        for item in sorted(parent.iterdir()):
            name = item.name
            # Only the blind artefacts and labeler 2's own export belong here. Any
            # other label file - including labeler 1's export under a different name -
            # is a protocol failure, so nothing is whitelisted by filename.
            if name == overlap_labels.name or name.endswith(ALLOWED_HANDOFF_SUFFIXES):
                continue
            stray.append(name)
    checks.append(
        {
            "check": "handoff directory holds only blind artefacts",
            "evidence": ", ".join(stray) if stray else "no manifest, selection or foreign export",
            "verdict": "pass" if not stray else "fail",
        }
    )

    forbidden = {
        "weight",
        "inclusion_prob",
        "split",
        "frame",
        "stratum",
        "cue_score",
        "cues",
        "text_bearing",
    }
    if blind_path is not None and blind_path.exists():
        with blind_path.open(encoding="utf-8", newline="") as handle:
            blind_columns = set(csv.DictReader(handle).fieldnames or [])
        with overlap_labels.open(encoding="utf-8-sig", newline="") as handle:
            export_columns = set(csv.DictReader(handle).fieldnames or [])
        extra = sorted(export_columns - blind_columns)
        leaked = sorted(export_columns & forbidden)
        verdict = "pass" if not extra and not leaked else "fail"
        evidence = (
            "export columns match the blind schema"
            if verdict == "pass"
            else f"extra columns: {extra or 'none'}; internal columns: {leaked or 'none'}"
        )
    else:
        verdict = "weak"
        evidence = "blind CSV not found next to the export; schema not compared"
    checks.append(
        {
            "check": "export carries no internal columns",
            "evidence": evidence,
            "verdict": verdict,
        }
    )

    if owner_pace_s and second_pace_s:
        ratio = second_pace_s / owner_pace_s
        checks.append(
            {
                "check": "labeling pace differs (weak corroboration only)",
                "evidence": (
                    f"{owner_pace_s:.0f} s/row (labeler 1) vs {second_pace_s:.0f} s/row "
                    f"(labeler 2), ratio {ratio:.1f}x - reported by the owner, not measured here"
                ),
                "verdict": "weak" if ratio >= 1.5 else "fail",
            }
        )
    else:
        checks.append(
            {
                "check": "labeling pace differs (weak corroboration only)",
                "evidence": "pace not supplied",
                "verdict": "weak",
            }
        )
    return checks


def wave_config(name: str, *, owner_pace_s: float, second_pace_s: float) -> dict[str, object]:
    """Paths and expectations for one wave's agreement run."""
    if name == "wave1":
        return {
            "label": "wave 1",
            "labels": WAVE_LABELS,
            "overlap": OVERLAP_LABELS,
            "selection": SELECTION,
            "manifest": MANIFEST,
            "report": REPORT,
            "summary": SUMMARY,
            "isolation_required": False,
            "owner_pace_s": owner_pace_s,
            "second_pace_s": second_pace_s,
            "blind": None,
        }
    if name == "wave2":
        return {
            "label": "wave 2",
            "labels": WAVE2_LABELS,
            "overlap": WAVE2_OVERLAP_LABELS,
            "selection": WAVE2_SELECTION,
            "manifest": WAVE2_MANIFEST,
            "report": WAVE2_REPORT,
            "summary": WAVE2_SUMMARY,
            "isolation_required": True,
            "owner_pace_s": owner_pace_s,
            "second_pace_s": second_pace_s,
            "blind": WAVE2_OVERLAP_LABELS.parent / "p3-03-wave2-overlap2-blind.csv",
        }
    raise AgreementError(f"unknown wave {name!r}; expected 'wave1' or 'wave2'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wave", choices=("wave1", "wave2"), default="wave1")
    parser.add_argument("--bootstrap", type=int, default=BOOTSTRAP)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--owner-pace-s", type=float, default=OWNER_PACE_S)
    parser.add_argument("--second-pace-s", type=float, default=SECOND_PACE_S)
    args = parser.parse_args(argv)

    cfg = wave_config(args.wave, owner_pace_s=args.owner_pace_s, second_pace_s=args.second_pace_s)
    wave_label = str(cfg["label"])
    labels_path = Path(str(cfg["labels"]))
    overlap_path = Path(str(cfg["overlap"]))
    selection_path = Path(str(cfg["selection"]))
    manifest_path = Path(str(cfg["manifest"]))
    report_path = Path(str(cfg["report"]))
    summary_path = Path(str(cfg["summary"]))

    first, labeler_1 = read_labels(labels_path, role="labeler 1")
    second, labeler_2 = read_labels(overlap_path, role="labeler 2")
    selection = json.loads(selection_path.read_text(encoding="utf-8"))
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
    weights_by_row = read_weights(manifest_path)
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
    negative_side_estimable = negatives >= NEGATIVE_FLOOR
    matrix = {a: {b: 0 for b in (*CLASSES, "skip")} for a in (*CLASSES, "skip")}
    for a, b in zip(left, right, strict=True):
        matrix[a][b] += 1
    off_diagonal = sum(
        matrix[a][b] for a in (*CLASSES, "skip") for b in (*CLASSES, "skip") if a != b
    )
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
    negative = negative_side(first, second, row_ids)
    blind_path = cfg["blind"]
    isolation = (
        isolation_audit(
            overlap_path,
            selection,
            labeler_1=labeler_1,
            labeler_2=labeler_2,
            owner_pace_s=args.owner_pace_s,
            second_pace_s=args.second_pace_s,
            blind_path=Path(str(blind_path)) if blind_path else None,
        )
        if cfg["isolation_required"]
        else []
    )
    isolation_failures = [check["check"] for check in isolation if check["verdict"] == "fail"]

    summary = {
        "wave": wave_label,
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
        "negative_side_estimable": negative_side_estimable,
        "negative_side": negative,
        "off_diagonal_cells": off_diagonal,
        "per_class": per_class,
        "confusion": matrix,
        "disagreements": disagreements,
        "degenerate": not disagreements,
        "isolation": isolation,
        "isolation_failures": isolation_failures,
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
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    lines = [
        f"# P3-03 {wave_label} — agreement between the two labelers",
        "",
        "Generated by `python scripts/dependency_agreement.py`; every number below is its output.",
        "",
        f"**Rows:** {total} (the overlap selected by ADR-0023 Amendment A) · "
        f"**labeler 1:** `{labeler_1}` · **labeler 2:** `{labeler_2}`",
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
        f"| Negative rows in the overlap | {negatives} |",
        f"| Off-diagonal cells | {off_diagonal} of {total} |",
        "",
        "**How to read it.** κ is **conditioned on labeler 1**: labeler 1's labels chose which",
        "rows are in the overlap, so this measures labeler 2's reproducibility against that rater,",
        "not agreement between two exchangeable raters. The overlap is positive-heavy, which",
        "*depresses* κ relative to a balanced design (the prevalence effect), so the value here is",
        "conservative; PABAK is shown because it ignores prevalence and therefore reads higher by",
        "construction.",
        "",
    ]
    if negative_side_estimable:
        lines += [
            "## Negative side (ADR-0023 Amendment C)",
            "",
            f"The floor of {NEGATIVE_FLOOR} negative rows is met ({negatives} available), so",
            "agreement on the side that produces false alarms can be estimated rather than "
            "counted.",
            "",
            "| Negative-side statistic | Value |",
            "| :-- | --: |",
            f"| Negative rows | {negative['rows']} |",
            f"| κ over the negative classes | **{negative['kappa']}** |",
            f"| Labeler 2 keeps the row negative | {float(negative['specificity']):.1%} "
            f"[{negative['specificity_ci'][0]:.1%}, {negative['specificity_ci'][1]:.1%}] |",
            f"| Labeler 2 calls it `RELIES_ON` | {negative['called_positive_by_labeler_2']} |",
            "",
        ]
    else:
        lines += [
            f"**Negative-side κ is not estimable**: {negatives} negative rows is below the "
            f"{NEGATIVE_FLOOR}-row floor in ADR-0023 Amendment C. Agreement on `MENTIONS`,",
            "`UNRELATED` and `insufficient_context` is a raw count here, not a rate. Only",
            f"{negatives} negative rows carry the negative side, so one disagreement there is",
            f"worth about {100 / max(negatives, 1):.0f} percentage points of that side's",
            "agreement.",
            "",
        ]
    lines += [
        "## Confusion matrix (labeler 1 rows, labeler 2 columns)",
        "",
        "| labeler 1 vs labeler 2 | " + " | ".join((*CLASSES, "skip")) + " |",
        "| :-- | " + " | ".join("--:" for _ in (*CLASSES, "skip")) + " |",
    ]
    for name in (*CLASSES, "skip"):
        cells = " | ".join(str(matrix[name][column]) for column in (*CLASSES, "skip"))
        lines.append(f"| {name} | {cells} |")
    lines += [
        "",
        "## Off-diagonal cells",
        "",
    ]
    if disagreements:
        lines += [
            f"**{off_diagonal} of {total} rows are off-diagonal.**",
            "",
            "| row | labeler 1 | labeler 2 |",
            "| :-- | :-- | :-- |",
        ]
        for item in disagreements:
            lines.append(f"| {item['row_id']} | {item['labeler_1']} | {item['labeler_2']} |")
    else:
        lines += [
            f"**Zero of {total} rows are off-diagonal.** The matrix is diagonal only: "
            f"{matrix['RELIES_ON']['RELIES_ON']} `RELIES_ON`, "
            f"{matrix['MENTIONS']['MENTIONS']} `MENTIONS`, "
            f"{matrix['UNRELATED']['UNRELATED']} `UNRELATED`, "
            f"{matrix['insufficient_context']['insufficient_context']} skipped.",
            "",
            "What that does and does not say about the rubric:",
            "",
            "- **It says the partition is reproducible.** Two people working from the written",
            "  guideline put the same rows in `RELIES_ON`, `MENTIONS` and `UNRELATED`. The three",
            "  labels are not being used idiosyncratically on this sample, which is the practical",
            "  property the downstream detector needs.",
            "- **It says nothing about the ambiguous boundary.** With no discordant "
            "pair, the sample",
            "  contains no evidence about where the rubric is fragile. A rubric can be perfectly",
            "  reproducible on rows both labelers find easy and still disagree on the "
            "hard ones the",
            "  overlap was supposed to expose.",
            "- **κ cannot separate the explanations.** Zero discordant pairs force κ to "
            "exactly 1 and",
            "  flatten its interval to a point. Genuine reliability, a shared reading of the same",
            "  guideline, and a shared heuristic are indistinguishable here. A 10-row "
            "blind re-label",
            "  by labeler 1 (test-retest) is the cheap check that would separate at "
            "least the first",
            "  from the others; the owner declined it for now.",
        ]
    lines += [
        "",
        "## Protocol checks (ADR-0023 Amendment C)",
        "",
        "- **Blinded subset:** the export's row ids match the selection file exactly; any mismatch",
        "  is rejected before comparison.",
        (
            f"- **Negative floor (>= {NEGATIVE_FLOOR} rows): met** with {negatives} negative rows."
            if negative_side_estimable
            else f"- **Negative floor (>= {NEGATIVE_FLOOR} rows): NOT met** - only {negatives} "
            "negative rows, so negative-side κ is not estimable and is reported as a count."
        ),
    ]
    if cfg["isolation_required"]:
        lines += [
            "- **Isolation of labeler 1's labels: checked below.**",
            "",
            "## Isolation audit",
            "",
            "What the repository and the export can show, with a verdict on each check. None of",
            "these proves who a person is; together they are the evidence the protocol asks for.",
            "",
            "| Check | Evidence | Verdict |",
            "| :-- | :-- | :-- |",
        ]
        for check in isolation:
            lines.append(f"| {check['check']} | {check['evidence']} | **{check['verdict']}** |")
        lines.append("")
        if not isolation_failures:
            lines += [
                "**All isolation checks passed.** Labeler 2's export was written into the",
                "handoff directory that holds only the blind CSV, the labeler HTML and its",
                "README: no labeler-1 export, manifest or selection file was reachable from it,",
                "and the export carries no weights, strata, split or cue columns. The two",
                "labeler ids are distinct, and the reported paces (38 s/row vs 120 s/row) are",
                "consistent with two people - but they are reported by the owner, not measured",
                "here, so pace is weak corroboration and not proof of identity.",
            ]
        else:
            lines += [
                f"**{len(isolation_failures)} isolation check(s) failed: "
                f"{', '.join(isolation_failures)}.** The agreement numbers below are reported but",
                "the isolation claim does not hold; treat the result as consistency only.",
            ]
    else:
        lines += [
            "- **Isolation of labeler 1's labels: NOT met for wave 1.** The labelled export sat in",
            "  `eval/audit/p3-03/` next to labeler 2's packet, so exposure cannot be"
            "excluded. Wave",
            "  1's agreement is therefore recorded as consistency only; the isolation rule applies",
            "  from wave 2.",
        ]
    limits = [
        "- The four-class matrix has a structurally empty `insufficient_context` row because",
        f"  labeler 1 skipped nothing in {wave_label}.",
    ]
    if disagreements:
        limits.append("- Agreement is measured on a positive-heavy overlap; it is not corpus κ.")
    else:
        limits += [
            "- **Zero discordant pairs.** κ is exactly 1 and its bootstrap interval is a point, so",
            "  this cannot distinguish genuine rubric reliability from (a) a shared cue heuristic,",
            "  (b) a shared reading of the guideline, or (c) labeler 2 having seen labeler 1's",
            "  labels. A blind re-label of a small subset later (test-retest) is the cheap check",
            "  that would separate these; until then this is consistency, not established",
            "  reliability.",
        ]
    lines += [
        "",
        "## Limits",
        "",
        f"- Single overlap, one pair of labelers, {total} rows: this does not estimate",
        "  corpus-level reliability.",
        *limits,
        "- Claim-level linking (P3-06) is a different task and is not measured here.",
        "",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "wave",
                    "rows",
                    "agree",
                    "raw_agreement",
                    "cohen_kappa",
                    "kappa_ci95",
                    "pabak",
                    "design_weighted_kappa",
                    "negative_rows",
                    "off_diagonal_cells",
                    "isolation_failures",
                )
            },
            indent=2,
        )
    )
    print(f"report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
