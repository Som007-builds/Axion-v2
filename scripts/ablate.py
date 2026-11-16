"""Evaluate versioned pipeline configurations against the frozen gold audit.

Offline by default: reads the gold CSV, a configuration's claim JSONL, the
source JATS cache (for sentence alignment), and the SQLite ledger (for cost).
No LLM call is made.

Usage:
    python scripts/ablate.py --config baseline
    python scripts/ablate.py --all --report docs/reports/P2-ablation.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from axion.eval.ablation import (
    AblationError,
    baseline_check,
    evaluate_config,
    load_configs,
    render_report,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG_DIR = ROOT / "eval" / "ablation" / "configs"
DEFAULT_GOLD = ROOT / "eval" / "audit" / "claims_audit_v1.csv"
DEFAULT_SOURCE = ROOT / "data" / "raw" / "europepmc" / "fulltext"
DEFAULT_OUT_DIR = ROOT / "eval" / "ablation" / "results"
DEFAULT_REPORT = ROOT / "docs" / "reports" / "P2-ablation.md"


def _resolve(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", action="append", default=[], help="config name (repeatable)")
    parser.add_argument("--all", action="store_true", help="evaluate every config")
    parser.add_argument("--config-dir", type=Path, default=DEFAULT_CONFIG_DIR)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--source-dir", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args(argv)

    if not args.config and not args.all:
        parser.error("choose --config NAME or --all")
    if not args.gold.exists():
        print(f"missing gold audit: {args.gold}", file=sys.stderr)
        return 1

    try:
        configs = load_configs(args.config_dir)
    except AblationError as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 1
    names = sorted(configs) if args.all else args.config
    missing = [name for name in names if name not in configs]
    if missing:
        print(f"unknown config(s): {', '.join(missing)}; available: {', '.join(sorted(configs))}")
        return 1

    scores = []
    for name in names:
        config = configs[name]
        # Resolve repo-relative claims/ledger paths without mutating the model.
        resolved = config.model_copy(
            update={
                "claims_path": str(_resolve(config.claims_path)),
                "paper_ids_path": (
                    None if config.paper_ids_path is None else str(_resolve(config.paper_ids_path))
                ),
                "ledgers": tuple(str(_resolve(path)) for path in config.ledgers),
            }
        )
        try:
            score = evaluate_config(resolved, gold_path=args.gold, source_dir=args.source_dir)
        except (AblationError, FileNotFoundError) as exc:
            print(f"{name}: cannot evaluate: {exc}", file=sys.stderr)
            return 1
        scores.append(score)
        print(
            f"{name}: papers={score.papers} claims={score.claims} "
            f"dev={score.by_split['dev'].precision} test={score.by_split['test'].precision} "
            f"retention={score.overall.retention:.3f} cost/paper={score.cost_per_paper_usd}"
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    payload = [score.model_dump(mode="json") for score in scores]
    json_path = args.json_out or (args.out_dir / "results.json")
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"results: {json_path}")

    report_path = args.report
    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_report(scores), encoding="utf-8", newline="\n")
        print(f"report: {report_path}")

    if "baseline" in names:
        check = baseline_check(scores[names.index("baseline")])
        print("baseline check: " + json.dumps(check, sort_keys=True))
        if not check["precision_matches"] or not check["retention_complete"]:
            print("BASELINE REPLAY MISMATCH (tolerance is zero for a replay)", file=sys.stderr)
            return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
