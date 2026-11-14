"""`axion-cost-report` command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import cast

from axion.config.settings import Settings
from axion.llm.ledger import GroupBy, LedgerReport, SQLiteLedger, TrainingRun


def _print_table(report: LedgerReport) -> None:
    header = (
        f"{report.group_by:<20} {'calls':>7} {'cache':>7} {'errors':>7} "
        f"{'missing':>8} {'escal':>7} {'prompt':>10} {'completion':>12} {'usd':>14}"
    )
    print(header)
    for row in report.rows:
        print(
            f"{row.key:<20.20} {row.calls:>7} {row.cache_hits:>7} {row.errors:>7} "
            f"{row.missing_price_calls:>8} {row.escalated_calls:>7} "
            f"{row.prompt_tokens:>10} {row.completion_tokens:>12} {row.usd:>14.6f}"
        )
    print("-" * len(header))
    print(
        f"{'TOTAL':<20} {report.total_calls:>7} {report.total_cache_hits:>7} "
        f"{report.total_errors:>7} {report.total_missing_price_calls:>8} "
        f"{report.total_escalated_calls:>7} {report.total_prompt_tokens:>10} "
        f"{report.total_completion_tokens:>12} {report.total_usd:>14.6f}"
    )


def _print_training_runs(runs: Sequence[TrainingRun]) -> None:
    header = f"{'run_id':<24} {'model':<24} {'hardware':<16} {'duration_s':>11} {'usd':>12}"
    print(header)
    for run in runs:
        print(
            f"{run.run_id:<24.24} {run.model:<24.24} {run.hardware:<16.16} "
            f"{run.duration_s:>11.1f} {run.estimated_usd:>12.6f}"
        )
    print("-" * len(header))
    total: Decimal = sum((run.estimated_usd for run in runs), Decimal("0"))
    print(f"{'TOTAL':<24} {'':<24} {'':<16} {'':>11} {total:>12.6f}")


def _training_runs_payload(runs: Sequence[TrainingRun]) -> dict[str, object]:
    return {
        "training_runs": [
            {
                "run_id": run.run_id,
                "ts": run.ts,
                "model": run.model,
                "data_hash": run.data_hash,
                "hardware": run.hardware,
                "duration_s": run.duration_s,
                "estimated_usd": format(run.estimated_usd, "f"),
            }
            for run in runs
        ],
        "total_estimated_usd": format(sum((run.estimated_usd for run in runs), Decimal("0")), "f"),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="axion-cost-report",
        description="Report LLM ledger cost by stage, model, provider, or tier.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to the SQLite ledger (defaults to AXION_LEDGER_PATH / AXION_DATA_DIR).",
    )
    parser.add_argument(
        "--group-by",
        choices=("stage", "model", "provider", "tier"),
        default="stage",
        help="Aggregation key (default: stage).",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON.")
    parser.add_argument(
        "--training-runs",
        action="store_true",
        dest="training_runs",
        help="Report recorded training runs instead of LLM calls.",
    )
    args = parser.parse_args(argv)

    db: Path | None = args.db
    if db is None:
        try:
            db = Settings().resolved_ledger_path
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    if not db.exists():
        print(f"error: ledger not found: {db}", file=sys.stderr)
        return 1

    ledger = SQLiteLedger(db)
    if args.training_runs:
        runs = ledger.training_runs()
        if args.as_json:
            print(json.dumps(_training_runs_payload(runs), indent=2))
        else:
            _print_training_runs(runs)
        return 0

    report = ledger.report(cast(GroupBy, args.group_by))
    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_table(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
