"""P2-07 cost-vs-quality frontier from measured ablation rows.

No LLM call, no new label, no tuning: this only ranks configurations that were
already measured, checks each against the PRD P2 gate, and states where `e` and
`s` come from.

Usage:
    python scripts/frontier.py
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = ROOT / "eval" / "ablation" / "results" / "results.json"
DEFAULT_ESCALATION = ROOT / "eval" / "escalation" / "run_manifest.json"
DEFAULT_STUDENT = ROOT / "eval" / "student" / "student_v1.manifest.json"
DEFAULT_REPORT = ROOT / "docs" / "reports" / "P2-frontier.md"
BASELINE = "baseline"
# ASSUMPTION (not a measurement): local CPU cost used by ADR-0020 for `s`.
CPU_USD_PER_HOUR = Decimal("0.05")
SAVINGS_TARGET = 0.50
PRECISION_TOLERANCE = 0.02


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _cost(row: dict[str, object]) -> float | None:
    value = row.get("cost_per_paper_usd")
    return None if value is None else float(str(value))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--escalation", type=Path, default=DEFAULT_ESCALATION)
    parser.add_argument("--student", type=Path, default=DEFAULT_STUDENT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)

    rows = json.loads(args.results.read_text(encoding="utf-8"))
    if not isinstance(rows, list) or not rows:
        print("no ablation results")
        return 1
    by_name = {str(row["config"]): row for row in rows}
    if BASELINE not in by_name:
        print("baseline row missing; cannot compute savings")
        return 1
    baseline = by_name[BASELINE]
    baseline_cost = _cost(baseline)
    baseline_precision = float(str(baseline["by_split"]["test"]["precision"]))
    if baseline_cost is None:
        print("baseline has no measured cost")
        return 1

    escalation = (
        json.loads(args.escalation.read_text(encoding="utf-8")) if args.escalation.exists() else {}
    )
    student = json.loads(args.student.read_text(encoding="utf-8")) if args.student.exists() else {}
    e_values = escalation.get("e", {})
    student_ms = escalation.get("student_ms_per_paper") or student.get("pipeline_ms_per_paper")

    def _student_ratio(row: dict[str, object]) -> Decimal | None:
        """s = local student cost / LLM-everywhere cost, using measured ms/paper."""
        if (
            str(row.get("kind")) not in {"student_run"}
            and row.get("inference_ms_per_paper") is None
        ):
            return None
        ms = row.get("inference_ms_per_paper") or student_ms
        if not ms:
            return None
        hours = Decimal(str(ms)) / Decimal(3_600_000)
        return (hours * CPU_USD_PER_HOUR / Decimal(str(baseline_cost))).quantize(Decimal("0.0001"))

    table = []
    for row in rows:
        name = str(row["config"])
        cost = _cost(row)
        test_precision = float(str(row["by_split"]["test"]["precision"]))
        retention = float(str(row["by_split"]["test"]["retention"]))
        core = float(str(row["overall"].get("core_retention", 0.0)))
        savings = None if cost is None else 1 - cost / baseline_cost
        s_value = _student_ratio(row)
        e_value: float | None
        if name.startswith("escalation"):
            e_value = float(e_values.get("all", 0.0)) or None
        elif s_value is not None or name in {BASELINE, "sections-core", "batching"}:
            # No LLM is called after the cheaper stage, so e is a measured zero.
            e_value = 0.0
        else:
            e_value = None
        table.append(
            {
                "config": name,
                "cost": cost,
                "savings": savings,
                "test_precision": test_precision,
                "retention": retention,
                "core_retention": core,
                "e": e_value,
                "s": s_value,
                "gate_cost": savings is not None and savings >= SAVINGS_TARGET,
                "gate_precision": test_precision >= baseline_precision - PRECISION_TOLERANCE,
            }
        )
    table.sort(key=lambda item: (item["cost"] is None, item["cost"] or 0.0))

    # 2-D Pareto frontier on (cost per paper, test precision). Retention is
    # reported beside it because a cheaper, equally precise row can still be
    # reading far less of the corpus.
    measured = [item for item in table if item["cost"] is not None]
    frontier = [
        item
        for item in measured
        if not any(
            other["cost"] <= item["cost"]
            and other["test_precision"] >= item["test_precision"]
            and (other["cost"] < item["cost"] or other["test_precision"] > item["test_precision"])
            for other in measured
        )
    ]

    lines = [
        "# P2-07 — cost-vs-quality frontier",
        "",
        "> Generated by `python scripts/frontier.py` from the measured ablation rows",
        "> (`eval/ablation/results/results.json`) and the escalation/student manifests.",
        "> **No new LLM call and no new label.** Gold measures precision only; retention is",
        "> agreement with the baseline's audited output, not recall.",
        "",
        "## How to read this",
        "",
        "- `$/paper` is list price from the ledger (free tier: real spend is $0).",
        "- `savings` is relative to the P1 baseline's measured `$0.005645/paper`.",
        "- `retention (test)` is the share of the 200 gold claims still emitted; `core` is",
        "  the ADR-0021 (proposed) view over abstract/results/conclusion claims.",
        "- `e` is the escalation rate actually realised; `s` is the measured student compute",
        "  time priced at an **ASSUMPTION** of $0.05 per CPU-hour (ADR-0020).",
        "",
        "## Measured rows",
        "",
        "| Config | $/paper | Savings | Test precision | Retention (test) | Core | e | s |",
        "| :-- | --: | --: | --: | --: | --: | --: | --: |",
    ]
    for item in table:
        cost = "n/a" if item["cost"] is None else f"${item['cost']:.9f}"
        savings = "n/a" if item["savings"] is None else _pct(item["savings"])
        e_text = "n/a" if item["e"] is None else _pct(item["e"])
        s_text = "n/a" if item["s"] is None else f"{item['s'] * 100:.2f}%"
        lines.append(
            f"| `{item['config']}` | {cost} | {savings} | {_pct(item['test_precision'])} | "
            f"{_pct(item['retention'])} | {_pct(item['core_retention'])} | {e_text} | {s_text} |"
        )

    lines.extend(
        [
            "",
            "## Pareto frontier (cost vs test precision)",
            "",
            "| Config | $/paper | Test precision | Retention (test) |",
            "| :-- | --: | --: | --: |",
        ]
    )
    for item in frontier:
        assert item["cost"] is not None
        lines.append(
            f"| `{item['config']}` | ${item['cost']:.9f} | {_pct(item['test_precision'])} | "
            f"{_pct(item['retention'])} |"
        )

    lines.extend(
        [
            "",
            "## PRD P2 gate (literal reading: ≥50% savings within 2 precision points)",
            "",
            "| Config | Savings ≥ 50% | Precision within 2 points | Gate |",
            "| :-- | :-- | :-- | :-- |",
        ]
    )
    for item in table:
        if item["cost"] is None:
            verdict = "not priced (no provider cost)"
        else:
            verdict = "PASS" if item["gate_cost"] and item["gate_precision"] else "FAIL"
        lines.append(
            f"| `{item['config']}` | {'yes' if item['gate_cost'] else 'no'} | "
            f"{'yes' if item['gate_precision'] else 'no'} | {verdict} |"
        )

    passing = [
        item
        for item in table
        if item["cost"] is not None and item["gate_cost"] and item["gate_precision"]
    ]
    # Among gate-passing rows, keep the one that retains the most audited output,
    # then the cheaper one: a configuration that passes on cost and precision by
    # reading almost nothing is not an operating point (ADR-0021, proposed).
    best = (
        max(passing, key=lambda item: (item["retention"], -(item["cost"] or 0.0)))
        if passing
        else None
    )
    lines.extend(["", "## Operating point", ""])
    if best is None:
        lines.extend(
            [
                "No measured configuration meets the literal gate. Publish the negative result",
                "per PRD §P2 and take the best frontier point.",
            ]
        )
    else:
        assert best["cost"] is not None and best["savings"] is not None
        lines.extend(
            [
                f"Candidate: **`{best['config']}`** — ${best['cost']:.9f}/paper "
                f"({_pct(best['savings'])} cheaper), test precision "
                f"{_pct(best['test_precision'])}, retention {_pct(best['retention'])}.",
                "",
                "It passes the literal gate (cost and precision) but its retention is the weak",
                "point, so it is proposed in an ADR rather than adopted here. Under ADR-0021",
                "(proposed) the agreement-with-baseline requirement would also apply, and that",
                "decision is the owner's.",
            ]
        )

    lines.extend(
        [
            "",
            "## Limits",
            "",
            "- Rows were measured on different paper sets (100-paper sample vs the 45 gold",
            "  papers), so `$/paper` is comparable in scale but not like-for-like per paper.",
            "- Non-LLM rows (`student-minilm`, `flywheel-student`) have no provider cost and are",
            "  not on the priced frontier; their cost is local compute plus the escalated teacher",
            "  calls they would still need.",
            "- `s` is a compute-time measurement priced with an assumed CPU rate, not a billed",
            "  cost.",
            "- Precision is measured on output that aligns with a gold row; unverifiable output is",
            "  counted separately and never as correct.",
            "",
        ]
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"rows={len(table)} frontier={len(frontier)} passing={len(passing)}")
    print(f"operating point: {best['config'] if best else 'none'}")
    print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
