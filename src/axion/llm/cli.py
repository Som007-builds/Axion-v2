"""`axion-cost-report` command-line entry point."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from axion.config.settings import Settings
from axion.llm.ledger import GroupBy, LedgerReport, SQLiteLedger


def _print_table(report: LedgerReport) -> None:
    header = (
        f"{report.group_by:<20} {'calls':>7} {'cache':>7} {'errors':>7} "
        f"{'missing':>8} {'prompt':>10} {'completion':>12} {'usd':>14}"
    )
    print(header)
    for row in report.rows:
        print(
            f"{row.key:<20.20} {row.calls:>7} {row.cache_hits:>7} {row.errors:>7} "
            f"{row.missing_price_calls:>8} {row.prompt_tokens:>10} "
            f"{row.completion_tokens:>12} {row.usd:>14.6f}"
        )
    print("-" * len(header))
    print(
        f"{'TOTAL':<20} {report.total_calls:>7} {report.total_cache_hits:>7} "
        f"{report.total_errors:>7} {report.total_missing_price_calls:>8} "
        f"{report.total_prompt_tokens:>10} {report.total_completion_tokens:>12} "
        f"{report.total_usd:>14.6f}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="axion-cost-report",
        description="Report LLM ledger cost by stage, model, or provider.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Path to the SQLite ledger (defaults to AXION_LEDGER_PATH / AXION_DATA_DIR).",
    )
    parser.add_argument(
        "--group-by",
        choices=("stage", "model", "provider"),
        default="stage",
        help="Aggregation key (default: stage).",
    )
    parser.add_argument("--json", action="store_true", dest="as_json", help="Emit JSON.")
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

    report = SQLiteLedger(db).report(cast(GroupBy, args.group_by))
    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        _print_table(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
