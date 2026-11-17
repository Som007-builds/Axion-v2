"""P2-06: run the batched claim-extraction lever (dry run by default).

Packs whole papers into one teacher call and records what batching costs:
parse failures, attribution failures, verbatim-span rejects, and the ledger cost
of the run. Uses the same sample, model, and generation config as the frozen
baseline; only the prompt version and the packing differ.

Usage:
    python scripts/run_batched_extraction.py --batch-size 3
    AXION_DRY_RUN=false python scripts/run_batched_extraction.py --execute --batch-size 3
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from axion.config.settings import DEFAULT_RATE_LIMITS_PATH, Settings
from axion.extract.baseline import DEFAULT_MAX_CLAIMS, build_plan
from axion.extract.batching import (
    BATCH_PROMPT_VERSION,
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_BATCH_TOKENS,
    plan_batches,
    run_batches,
)
from axion.ingest.corpus import read_manifest, read_papers_csv
from axion.llm.ledger import SQLiteLedger
from axion.llm.pacing import PACIFIC, RequestPacer, load_rate_limits
from run_baseline_extraction import (  # same directory, executed as a script
    DEFAULT_BASELINE_MODEL,
    DEFAULT_MANIFEST,
    DEFAULT_MAX_OUTPUT_TOKENS,
    DEFAULT_THINKING_LEVEL,
    _build_client,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SILVER_DIR = ROOT / "eval" / "silver" / "claims_v1" / "batching"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--max-batch-tokens", type=int, default=DEFAULT_MAX_BATCH_TOKENS)
    parser.add_argument("--max-claims", type=int, default=DEFAULT_MAX_CLAIMS)
    parser.add_argument("--max-calls", type=int, default=100)
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument("--model", default=DEFAULT_BASELINE_MODEL)
    parser.add_argument("--thinking-level", default=DEFAULT_THINKING_LEVEL)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "reports" / "P2-06-batching")
    parser.add_argument("--silver-dir", type=Path, default=DEFAULT_SILVER_DIR)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--rate-limits", type=Path, default=DEFAULT_RATE_LIMITS_PATH)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)

    manifest = read_manifest(args.manifest)
    papers = read_papers_csv(args.manifest.parent / Path(manifest.files.papers_csv).name)
    settings = Settings()
    cache_dir = settings.resolved_europepmc_cache_dir
    plans, report = build_plan(
        papers,
        cache_dir,
        sample_size=args.sample,
        seed=args.seed,
        max_claims=args.max_claims,
    )
    groups = plan_batches(
        plans,
        batch_size=args.batch_size,
        max_batch_tokens=args.max_batch_tokens,
        max_claims=args.max_claims,
    )
    prompt_tokens = sum(group.prompt_tokens_estimate for group in groups)
    grouped_papers = sum(len(group.plans) for group in groups)
    print(
        f"papers={len(plans)} batches={len(groups)} "
        f"max_batch={max((len(group.plans) for group in groups), default=0)} "
        f"prompt_tokens_estimate={prompt_tokens:,}",
        flush=True,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    plan_path = Path(f"{args.out}.plan.json")
    plan_path.write_text(
        json.dumps(
            {
                "prompt_version": BATCH_PROMPT_VERSION,
                "batch_size": args.batch_size,
                "max_batch_tokens": args.max_batch_tokens,
                "sample": args.sample,
                "seed": args.seed,
                "papers_with_text": len(plans),
                "papers_grouped": grouped_papers,
                "batches": len(groups),
                "prompt_tokens_estimate": prompt_tokens,
                "batch_paper_ids": [list(group.paper_ids) for group in groups],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"plan: {plan_path}", flush=True)
    if not args.execute:
        return 0

    if settings.dry_run:
        print("AXION_DRY_RUN is true; set it to false for the run", flush=True)
        return 1
    if not settings.llm_provider_chain or settings.llm_provider_chain[0] != "gemini":
        print("LLM_PROVIDER_CHAIN must start with 'gemini'", flush=True)
        return 1

    model = args.model.strip()
    rate_table = load_rate_limits(args.rate_limits)
    rate = rate_table.require(model)
    ledger = SQLiteLedger(settings.resolved_ledger_path)
    pacer = RequestPacer.from_calls(rate, ledger.calls_for_model(model))
    print(
        f"pacing: {rate.rpm} RPM, cap {rate.daily_cap}/day, {pacer.requests_today} used today",
        flush=True,
    )
    run_id = args.run_id or (f"p2-06-batch{args.batch_size}-s{args.seed}-n{args.sample}")
    client = _build_client(settings, max_output_tokens=args.max_output_tokens)
    batch_report = run_batches(
        client,
        groups,
        run_id=run_id,
        output_dir=args.silver_dir,
        max_calls=args.max_calls,
        max_output_tokens=args.max_output_tokens,
        model=model,
        temperature=settings.llm_temperature,
        thinking_level=args.thinking_level,
        pacer=pacer,
    )
    payload = batch_report.payload()
    payload["cost_usd"] = str(
        sum((call.usd or Decimal("0") for call in ledger.calls_for_run(run_id)), Decimal("0"))
    )
    payload["finished_at"] = datetime.now(UTC).replace(microsecond=0).isoformat()
    payload["pacific_date"] = str(datetime.now(UTC).astimezone(PACIFIC).date())
    report_path = Path(f"{args.out}.json")
    report_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"run={run_id} papers={batch_report.papers} claims={batch_report.claims} "
        f"calls={batch_report.calls} parse_failures={batch_report.parse_failures} "
        f"attribution_failures={batch_report.attribution_failures} "
        f"stopped={batch_report.stopped_reason}",
        flush=True,
    )
    print(f"report: {report_path}", flush=True)
    if batch_report.stopped_reason == "daily_quota_reached":
        print("daily quota reached; resume after midnight America/Los_Angeles", flush=True)
        return 2
    return 0 if batch_report.stopped_reason is None else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
