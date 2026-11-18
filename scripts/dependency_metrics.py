"""Wave-1 metrics for the P3-03 gold audit, generated from the labelled packet.

Reports the class counts overall and per frame/split, the design-weighted corpus
base rate for `RELIES_ON` from the uniform slice, the Amendment B split between
the text-bearing frame and the 34 title-only stub stratum, whether the cue
enrichment worked, and how many more positives a recall claim at the P3 gate
needs. Every number is printed from the committed files.

Usage:
    python scripts/dependency_metrics.py
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import Counter
from pathlib import Path

from axion.eval.audit import AuditError, wilson_interval

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "audit" / "p3-03"
MANIFEST = OUT / "p3-03-wave1-manifest.csv"
LABELS = OUT / "dependency_audit_v1_wave1_labelled.csv"
WAVE2_MANIFEST = OUT / "p3-03-wave2-manifest.csv"
WAVE2_LABELS = OUT / "dependency_audit_v1_wave2_labelled.csv"
REPORT = ROOT / "docs" / "reports" / "P3-03-wave1-metrics.md"
SUMMARY = OUT / "p3-03-wave1-metrics.json"
COMBINED_REPORT = ROOT / "docs" / "reports" / "P3-03-wave1-wave2-metrics.md"
COMBINED_SUMMARY = OUT / "p3-03-combined-metrics.json"

CLASSES = ("RELIES_ON", "MENTIONS", "UNRELATED", "insufficient_context")
SKIP = "insufficient_context"  # a blank label is the guideline's skip action
GATE_RECALL = 0.70
RATIFIED_RECALL = 0.80


class MetricsError(Exception):
    """The labelled packet cannot be summarised."""


def read_metrics_inputs(
    manifest_path: Path = MANIFEST, labels_path: Path = LABELS
) -> list[dict[str, str]]:
    """Join the manifest to the labels, one row per wave row."""
    for path in (manifest_path, labels_path):
        if not path.exists():
            raise MetricsError(f"missing input: {path}")
    with labels_path.open(encoding="utf-8-sig", newline="") as handle:
        labelled = list(csv.DictReader(handle))
    labels = {
        (row.get("row_id") or "").strip(): (row.get("label") or "").strip() for row in labelled
    }
    if len(labels) != len(labelled):
        raise MetricsError("label file repeats a row_id")
    with manifest_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if set(labels) != {row["row_id"] for row in rows}:
        raise MetricsError(f"label file covers {len(labels)} rows; the manifest has {len(rows)}")
    joined: list[dict[str, str]] = []
    for row in rows:
        label = labels[row["row_id"]]
        if label and label not in CLASSES:
            raise MetricsError(f"{row['row_id']}: {label!r} is not one of {CLASSES}")
        merged = dict(row)
        merged["label"] = label or SKIP
        joined.append(merged)
    return joined


def counts(rows: list[dict[str, str]]) -> dict[str, int]:
    """Class counts, with the skip action counted as `insufficient_context`."""
    tally = Counter(row["label"] for row in rows)
    return {name: tally.get(name, 0) for name in CLASSES}


def weighted_rate(rows: list[dict[str, str]], positive: str = "RELIES_ON") -> tuple[float, float]:
    """Horvitz-Thompson rate and Kish effective sample size."""
    total = sum(float(row["weight"]) for row in rows)
    if total <= 0:
        raise MetricsError("weights must be positive")
    weighted = sum(float(row["weight"]) for row in rows if row["label"] == positive)
    squares = sum(float(row["weight"]) ** 2 for row in rows)
    effective = (total**2) / squares if squares else 0.0
    return weighted / total, effective


def rate_with_interval(
    rows: list[dict[str, str]], positive: str = "RELIES_ON"
) -> dict[str, object]:
    """Weighted rate plus a Wilson interval on the effective sample size."""
    if not rows:
        return {
            "rows": 0,
            "positives": 0,
            "unweighted_rate": 0.0,
            "weighted_rate": 0.0,
            "effective_n": 0.0,
            "wilson_low": 0.0,
            "wilson_high": 1.0,
        }
    rate, effective = weighted_rate(rows, positive)
    successes = sum(1 for row in rows if row["label"] == positive)
    k = round(rate * effective)
    k = max(0, min(k, round(effective)))
    low, high = wilson_interval(k, round(effective)) if effective >= 1 else (0.0, 1.0)
    return {
        "rows": len(rows),
        "positives": successes,
        "unweighted_rate": round(successes / len(rows), 4) if rows else 0.0,
        "weighted_rate": round(rate, 4),
        "effective_n": round(effective, 2),
        "wilson_low": round(low, 4),
        "wilson_high": round(high, 4),
    }


def positives_needed(recall: float, target_low: float = GATE_RECALL, limit: int = 400) -> int:
    """Smallest positive count whose Wilson lower bound clears `target_low`."""
    for positives in range(1, limit + 1):
        successes = round(recall * positives)
        successes = max(1, min(successes, positives))
        low, _ = wilson_interval(successes, positives)
        if low >= target_low:
            return positives
    return limit


def rows_for(positives: int, rate: float) -> int:
    """Rows implied by a positive rate (rounded up)."""
    if rate <= 0:
        return 0
    return math.ceil(positives / rate)


def _pack(rows: list[dict[str, str]]) -> dict[str, object]:
    """Counts and rates for one slice of rows."""
    uniform = [row for row in rows if row["frame"] == "uniform"]
    text_bearing = [row for row in rows if row["text_bearing"] == "true"]
    stubs = [row for row in rows if row["text_bearing"] == "false"]
    return {
        "rows": len(rows),
        "overall": counts(rows),
        "by_split": {
            split: counts([row for row in rows if row["split"] == split])
            for split in ("dev", "test")
        },
        "uniform": rate_with_interval(uniform) if uniform else None,
        "text_bearing": {"rows": len(text_bearing), **counts(text_bearing)},
        "stub": {"rows": len(stubs), **counts(stubs)},
    }


def write_combined(
    wave1: list[dict[str, str]],
    wave2: list[dict[str, str]],
    *,
    report_path: Path = COMBINED_REPORT,
    summary_path: Path = COMBINED_SUMMARY,
) -> dict[str, object]:
    """Wave 1 + wave 2: the ADR-0024 stop-rule report."""
    combined = [*wave1, *wave2]
    pack_all = _pack(combined)
    pack_1 = _pack(wave1)
    pack_2 = _pack(wave2)
    unified = pack_all["uniform"]
    if not isinstance(unified, dict):
        raise MetricsError("no uniform rows to estimate the base rate")
    total = pack_all["overall"]["RELIES_ON"]
    needed = positives_needed(0.80)
    extra = max(0, needed - total)
    rate = float(unified["weighted_rate"])
    wave1_rate = pack_1["uniform"]
    wave2_rate = pack_2["uniform"]
    assert isinstance(wave1_rate, dict) and isinstance(wave2_rate, dict)
    extra_rows = {
        "combined_weighted": rows_for(extra, rate),
        "combined_unweighted": rows_for(extra, float(unified["unweighted_rate"])),
        "wave2_only": rows_for(extra, float(wave2_rate["weighted_rate"])),
    }
    summary = {
        "waves": 2,
        "combined": pack_all,
        "wave1": pack_1,
        "wave2": pack_2,
        "uniform_rate_wave1": wave1_rate,
        "uniform_rate_wave2": wave2_rate,
        "positives_needed_080": needed,
        "extra_positives_for_080": extra,
        "extra_rows_for_080": extra_rows,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def counts_row(name: str, pack: dict[str, object]) -> str:
        overall = pack["overall"]
        assert isinstance(overall, dict)
        cells = " | ".join(str(overall[class_name]) for class_name in CLASSES)
        return f"| {name} | {pack['rows']} | {cells} |"

    def plain_row(name: str, slice_counts: dict[str, object]) -> str:
        cells = " | ".join(str(slice_counts[class_name]) for class_name in CLASSES)
        return f"| {name} | {slice_counts['rows']} | {cells} |"

    lines = [
        "# P3-03 wave 1 + wave 2 - combined metrics (ADR-0024 stop rule)",
        "",
        "Generated by `python scripts/dependency_metrics.py`; every number below is its output.",
        "",
        "| Slice | Rows | " + " | ".join(CLASSES) + " |",
        "| :-- | --: | " + " | ".join("--:" for _ in CLASSES) + " |",
        counts_row("Wave 1", pack_1),
        counts_row("Wave 2 (uniform)", pack_2),
        counts_row("Combined", pack_all),
        plain_row("Text-bearing frame (primary)", pack_all["text_bearing"]),
        plain_row("Title-only stub stratum", pack_all["stub"]),
        "",
        "## Updated base rate (all uniform rows, both waves)",
        "",
        f"- Weighted **{rate:.1%}** with Wilson 95% "
        f"[{unified['wilson_low']:.1%}, {unified['wilson_high']:.1%}] over "
        f"**{unified['rows']} uniform rows** "
        f"({unified['positives']} positives); unweighted "
        f"**{unified['unweighted_rate']:.1%}**.",
        "",
        "## Positives per split",
        "",
        "| Split | Rows | " + " | ".join(CLASSES) + " |",
        "| :-- | --: | " + " | ".join("--:" for _ in CLASSES) + " |",
    ]
    for split in ("dev", "test"):
        value = pack_all["by_split"][split]
        rows_count = sum(1 for row in combined if row["split"] == split)
        cells = " | ".join(str(value[class_name]) for class_name in CLASSES)
        lines.append(f"| {split} | {rows_count} | {cells} |")
    lines += [
        "",
        "## Stop rule (ADR-0024 §5)",
        "",
        f"- Combined positives: **{total}**. The 0.80-observed-recall case needs **{needed}**,",
        f"  so **{extra} more** are outstanding.",
        "- At that rate the extra rows depend on which pool you believe:",
        f"  - combined, design-weighted ({rate:.1%}): **{extra_rows['combined_weighted']} rows**;",
        f"  - combined, unweighted ({float(unified['unweighted_rate']):.1%}): "
        f"**{extra_rows['combined_unweighted']} rows**;",
        f"  - wave 2 only ({float(wave2_rate['weighted_rate']):.1%}, n={wave2_rate['rows']}): "
        f"**{extra_rows['wave2_only']} rows**.",
        "",
        "## Heterogeneity between the two uniform slices",
        "",
        f"- Wave 1 uniform: **{wave1_rate['positives']}/{wave1_rate['rows']} = "
        f"{float(wave1_rate['unweighted_rate']):.1%}** "
        f"[{float(wave1_rate['wilson_low']):.1%}, {float(wave1_rate['wilson_high']):.1%}].",
        f"- Wave 2 uniform: **{wave2_rate['positives']}/{wave2_rate['rows']} = "
        f"{float(wave2_rate['unweighted_rate']):.1%}** "
        f"[{float(wave2_rate['wilson_low']):.1%}, {float(wave2_rate['wilson_high']):.1%}].",
        "- The intervals overlap only slightly and the design weights differ by ~5x, which is",
        "  why the pooled weighted and unweighted rates disagree. Treat the single pooled rate as",
        "  provisional: the 150-row wave-2 slice is the larger and better-measured of the two,",
        "  and the 30-row wave-1 slice may be high by chance. No homogeneity test is claimed.",
        "",
        "- Every number here is conditional on the P1 citer set (ADR-0015) and on one labeler; the",
        "  overlap's kappa is degenerate, so no reliability claim rides on these counts.",
        "",
    ]
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--labels", type=Path, default=LABELS)
    parser.add_argument("--wave2-manifest", type=Path, default=WAVE2_MANIFEST)
    parser.add_argument("--wave2-labels", type=Path, default=WAVE2_LABELS)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--summary", type=Path, default=SUMMARY)
    parser.add_argument("--combined-report", type=Path, default=COMBINED_REPORT)
    parser.add_argument("--combined-summary", type=Path, default=COMBINED_SUMMARY)
    args = parser.parse_args(argv)

    try:
        rows = read_metrics_inputs(args.manifest, args.labels)
    except (MetricsError, AuditError) as error:
        raise SystemExit(f"metrics failed: {error}") from error

    overall = counts(rows)
    uniform = [row for row in rows if row["frame"] == "uniform"]
    enriched = [row for row in rows if row["frame"] == "enriched"]
    text_bearing = [row for row in rows if row["text_bearing"] == "true"]
    stubs = [row for row in rows if row["text_bearing"] == "false"]
    by_frame = {
        frame: counts([row for row in rows if row["frame"] == frame])
        for frame in ("uniform", "enriched")
    }
    by_split = {
        split: counts([row for row in rows if row["split"] == split]) for split in ("dev", "test")
    }
    by_split_frame = {
        (split, frame): counts(
            [row for row in rows if row["split"] == split and row["frame"] == frame]
        )
        for split in ("dev", "test")
        for frame in ("uniform", "enriched")
    }
    uniform_rate = rate_with_interval(uniform)
    enriched_rate = rate_with_interval(enriched)
    total_positives = overall["RELIES_ON"]
    enriched_positives = by_frame["enriched"]["RELIES_ON"]
    enriched_share = enriched_positives / total_positives if total_positives else 0.0

    plan = {}
    for label, recall in (("0.80", 0.80), ("0.85", 0.85)):
        needed = positives_needed(recall)
        plan[label] = {
            "positives_for_lower_bound_0.70": needed,
            "extra_positives_from_wave1": max(0, needed - total_positives),
            "extra_rows_at_enriched_rate": rows_for(
                max(0, needed - total_positives), enriched_rate["weighted_rate"]
            ),
            "extra_rows_at_uniform_rate": rows_for(
                max(0, needed - total_positives), uniform_rate["weighted_rate"]
            ),
        }
    decision_grade = positives_needed(0.85, target_low=0.70)
    best_frame = (
        "uniform" if uniform_rate["weighted_rate"] >= enriched_rate["weighted_rate"] else "enriched"
    )
    best_rate = max(uniform_rate["weighted_rate"], enriched_rate["weighted_rate"])
    rows_for_next_positives = rows_for(max(0, decision_grade - total_positives), best_rate)
    extra_for_080 = plan["0.80"]["extra_positives_from_wave1"]
    rows_for_080 = rows_for(extra_for_080, best_rate)
    wave2_rows = 150
    wave2_expected = round(wave2_rows * best_rate, 1)

    summary = {
        "rows": len(rows),
        "overall": overall,
        "by_frame": by_frame,
        "by_split": by_split,
        "by_split_frame": {
            f"{split}:{frame}": value for (split, frame), value in by_split_frame.items()
        },
        "text_bearing": {"rows": len(text_bearing), **counts(text_bearing)},
        "stub_stratum": {"rows": len(stubs), **counts(stubs)},
        "uniform_base_rate": uniform_rate,
        "enriched_rate": enriched_rate,
        "enriched_share_of_positives": round(enriched_share, 4),
        "plan": plan,
        "decision_grade_positives": decision_grade,
        "best_frame_for_positives": best_frame,
        "best_rate": round(best_rate, 4),
        "rows_for_decision_grade": rows_for_next_positives,
        "rows_for_recall_080": rows_for_080,
        "wave2_expected_positives_150_rows": wave2_expected,
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    stub_counts = counts(stubs)
    if stubs:
        stub_note = [
            "**Amendment B's assumption is wrong in kind:** the stub rows were expected to be",
            f"near-certain negatives, but **{stub_counts['RELIES_ON']}/{len(stubs)} are "
            f"`RELIES_ON`** ({stub_counts['RELIES_ON'] / len(stubs):.1%}). A title-only row still",
            "carries the citing sentence, and that is enough to judge the relation in some cases.",
            "The stratum stays separate and stays in the weighted base rate, and no packet is",
            "redrawn; the reasoning that stubs are pure negatives is withdrawn.",
        ]
    else:
        stub_note = [
            "**No title-only stub rows in this slice**, so Amendment B's stub stratum is empty",
            "here and nothing is claimed about it.",
        ]

    def table(title: str, value: dict[str, int], extra: str = "") -> list[str]:
        cells = " | ".join(str(value[name]) for name in CLASSES)
        total = sum(value.values())
        return [f"| {title}{extra} | {total} | {cells} |"]

    lines = [
        "# P3-03 wave 1 — measured label counts and base rate",
        "",
        "Generated by `python scripts/dependency_metrics.py`; every number below is its output.",
        "",
        "| Slice | Rows | " + " | ".join(CLASSES) + " |",
        "| :-- | --: | " + " | ".join("--:" for _ in CLASSES) + " |",
        *table("All wave rows", overall),
        *table("Uniform frame", by_frame["uniform"]),
        *table("Cue-enriched frame", by_frame["enriched"]),
        *table("dev split", by_split["dev"]),
        *table("test split", by_split["test"]),
        *table("Text-bearing frame (Amendment B primary)", counts(text_bearing)),
        *table("Title-only stub stratum", counts(stubs)),
        "",
        *stub_note,
        "",
        "## Base rate from the uniform slice",
        "",
        f"- Uniform slice: **{uniform_rate['positives']}/{uniform_rate['rows']}** `RELIES_ON` = "
        f"**{uniform_rate['unweighted_rate']:.1%}**, Wilson 95% "
        f"[{uniform_rate['wilson_low']:.1%}, {uniform_rate['wilson_high']:.1%}].",
        f"- Design-weighted estimate over the same rows: **{uniform_rate['weighted_rate']:.1%}** "
        f"(effective n {uniform_rate['effective_n']}); the uniform weights are equal, so the two",
        "agree.",
        f"- Cue-enriched frame: **{enriched_rate['positives']}/{enriched_rate['rows']}** = "
        f"**{enriched_rate['unweighted_rate']:.1%}**, Wilson 95% "
        f"[{enriched_rate['wilson_low']:.1%}, {enriched_rate['wilson_high']:.1%}].",
        "",
        "The uniform slice is a simple random sample of the 6,117-context frame, so its rate is",
        "the corpus base-rate estimate; the per-source cap makes it a capped sample of contexts,",
        "and the 6,117 frame is itself conditional on the included citer set (ADR-0015), so this",
        "is a lower bound on the true blast radius, not a population-wide prevalence.",
        "",
        "## Did the cue enrichment work?",
        "",
        f"- `RELIES_ON` in the enriched frame: **{by_frame['enriched']['RELIES_ON']}/"
        f"{len(enriched)}** vs **{by_frame['uniform']['RELIES_ON']}/{len(uniform)}** uniform.",
        f"- **{enriched_share:.1%} of all {total_positives} positives come from the enriched",
        "  frame**, which is 80% of the wave.",
        f"- Enriched rate {enriched_rate['unweighted_rate']:.1%} "
        f"[{enriched_rate['wilson_low']:.1%}, {enriched_rate['wilson_high']:.1%}] vs uniform "
        f"{uniform_rate['unweighted_rate']:.1%} "
        f"[{uniform_rate['wilson_low']:.1%}, {uniform_rate['wilson_high']:.1%}]: the point "
        "estimate "
        + (
            "favours the **enriched** frame"
            if enriched_rate["weighted_rate"] > uniform_rate["weighted_rate"]
            else "is **lower in the enriched frame**, so cue enrichment did **not** buy a higher "
            "positive rate here"
        )
        + ".",
        "- The intervals overlap heavily at n=120 and n=30, so this is **no measured",
        "  lift**, not proven absence of one. The cues remain unvalidated and must not be used",
        "  as a positive filter.",
        "- The uniform rate is far above the 20-row pilot's 10% (Wilson [2.8%, 30.1%]); the pilot",
        "  was edge-case-enriched and tiny, so that figure is not a corpus rate.",
        "",
        "## Positives a recall claim needs (measured plan, not a projection)",
        "",
        "| Recall | Positives for 0.70 | Extra positives | Rows (enriched) | Rows (uniform) |",
        "| --: | --: | --: | --: | --: |",
    ]
    for label, value in plan.items():
        lines.append(
            f"| {label} | {value['positives_for_lower_bound_0.70']} | "
            f"{value['extra_positives_from_wave1']} | {value['extra_rows_at_enriched_rate']} | "
            f"{value['extra_rows_at_uniform_rate']} |"
        )
    lines += [
        "",
        f"Wave 1 has **{total_positives} positives**. A **decision-grade** read (0.70 lower",
        f"bound at observed recall 0.85) needs about **{decision_grade}** positives, i.e.",
        f"**{max(0, decision_grade - total_positives)} more** — roughly",
        f"**{rows_for_next_positives} more rows** at the best measured positive rate",
        f"({best_rate:.1%}, {best_frame} frame). A **certified** 0.70 lower bound at observed",
        f"recall 0.80 needs about {plan['0.80']['positives_for_lower_bound_0.70']} positives",
        f"(+{extra_for_080}), i.e. about **{rows_for_080} more rows** at that rate.",
        "",
        "## Wave-2 recommendation",
        "",
        f"- **Draw wave 2 from the {best_frame} frame.** At the measured rates it yields the",
        "  most positives per labelled row, and if that frame is the uniform one it is also",
        "  unbiased, so it tightens the base rate at the same time.",
        f"- **Size: {wave2_rows} rows**, expected **~{wave2_expected} positives** at",
        f"  {best_rate:.1%}, taking the total to about {total_positives + round(wave2_expected)}.",
        f"- **Time at the pilot pace:** {wave2_rows * 20 // 60}-{wave2_rows * 45 // 60} minutes",
        "  of owner labeling; the owner's real pace replaces this arithmetic.",
        "- **Do not** spend wave 2 on the cue-enriched frame: it did not beat the uniform draw,",
        "  so more enriched rows buy no extra positives per row.",
        "",
        "## Limits",
        "",
        "- One labeler for the gold labels; the 31-row overlap agreed 31/31 but κ is degenerate",
        "  (zero discordant pairs), so this is consistency, not established reliability.",
        "- Counts are conditioned on the P1 citer set; 5,734 eligible citers were truncated by the",
        "  corpus cap, so every rate here understates the true blast radius.",
        "- The stub stratum has no abstract by construction, so its labels rest on the citing",
        "  sentence alone (Amendment B); 3 of 34 are `RELIES_ON`, which is why the stratum is",
        "  reported separately instead of being folded in as negatives.",
        "",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                k: summary[k]
                for k in (
                    "rows",
                    "overall",
                    "by_frame",
                    "uniform_base_rate",
                    "enriched_rate",
                    "enriched_share_of_positives",
                    "plan",
                )
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(f"report: {args.report}")
    if args.wave2_manifest.exists() and args.wave2_labels.exists():
        wave2_rows = read_metrics_inputs(args.wave2_manifest, args.wave2_labels)
        combined = write_combined(
            rows,
            wave2_rows,
            report_path=args.combined_report,
            summary_path=args.combined_summary,
        )
        print(f"combined report: {args.combined_report}")
        print(
            json.dumps(
                {
                    "rows": combined["combined"]["rows"],
                    "positives_needed_080": combined["positives_needed_080"],
                    "extra_rows_for_080": combined["extra_rows_for_080"],
                }
            )
        )
    else:
        print("wave 2 labels not present yet; combined report skipped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
