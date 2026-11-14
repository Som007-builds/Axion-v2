"""Plan or run the P1-10 baseline claim extraction (offline by default).

Dry run (default): parse the seeded sample, render the versioned prompt, and
estimate calls/tokens. It makes no LLM call and never needs prices.
Execute: requires an explicitly registered provider adapter; none ships in this
repository, so this exits with a clear error until the owner approves an SDK.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from axion.config.settings import Settings
from axion.extract.baseline import (
    DEFAULT_MAX_CALLS,
    DEFAULT_MAX_CLAIMS,
    DryRunEstimate,
    PlanReport,
    build_plan,
    dry_run_estimate,
)
from axion.extract.claims import PROMPT_VERSION
from axion.extract.prompting import PromptError
from axion.ingest.corpus import read_manifest, read_papers_csv
from axion.llm.adapters import ProviderAdapter

DEFAULT_MANIFEST = Path("docs/reports/P1-corpus-manifest.json")
DEFAULT_OUT = Path("docs/reports/P1-baseline-estimate")
DEFAULT_SILVER_DIR = Path("eval/silver/claims_v1")


def _markdown(estimate: DryRunEstimate, plan: PlanReport) -> str:
    values = estimate.model_dump()
    lines = [
        "# P1 baseline extraction — dry-run plan (ESTIMATE)",
        "",
        "**No extractor was run and no LLM call was made.** This plan parses real",
        "corpus text and estimates prompt tokens; the claims/paper rate is a scenario,",
        "not a measurement. Prices are blank, so no dollar cost is stated.",
        "",
        "## Sample",
        "",
        f"- Requested papers: {plan.requested}",
        f"- Usable papers with baseline text: {plan.with_text}",
        f"- Missing full text: {plan.missing_fulltext}",
        f"- Parse failures: {plan.parse_failures}",
        f"- Empty baseline documents: {plan.empty_documents}",
        f"- Seed: {values['seed']}; prompt version: `{values['prompt_version']}`",
        "",
        "## Prompt tokens (estimate)",
        "",
        "| Mean | Median | p95 |",
        "| --: | --: | --: |",
        f"| {plan.mean_prompt_tokens:,.0f} | {plan.median_prompt_tokens:,.0f} | "
        f"{plan.p95_prompt_tokens:,.0f} |",
        "",
        f"Total for {values['estimated_calls']} calls: "
        f"**{values['prompt_tokens_total']:,}** prompt tokens (chars/4 heuristic).",
        "",
        "## Expected claims and output tokens",
        "",
        "| Claims/paper (assumed) | Expected claims | Output tokens |",
        "| --: | --: | --: |",
    ]
    for key in values["claims_per_paper_scenarios"]:
        lines.append(
            f"| {key} | {values['expected_claims_by_scenario'][key]:,.0f} | "
            f"{values['output_tokens_by_scenario'][key]:,} |"
        )
    lines.extend(
        [
            "",
            "## Size recommendation",
            "",
            f"- Clears 200 claims at 5 claims/paper: "
            f"**{values['clears_200_claims_at_5_per_paper']}**",
            f"- Recommended sample: **{values['recommended_sample_size']} papers** "
            "(seeded, paper-level, uniform over corpus papers with full text).",
            "- The recommendation is based on the conservative 5-claims/paper scenario;",
            "  the paid run must record the observed rate and may stop early only with",
            "  owner approval.",
            "",
            "## Method",
            "",
            values["method"],
            "",
            "## Cost",
            "",
            values["cost_status"],
            "Formula once prices exist: `input_tokens * input_price_per_Mtok / 1e6 + "
            "output_tokens * output_price_per_Mtok / 1e6`.",
            "",
            "## Owner inputs required before the paid run",
            "",
            "1. Provider hosting for the chosen large tier (tier IDs are configured in `.env`).",
            "2. Verified input/output prices in `src/axion/config/pricing.yaml`.",
            "3. A paid budget cap in `_private/budget.md`.",
            "4. Approval to install the chosen provider SDK (no adapter ships here).",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20261114)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--prompt-version", default=PROMPT_VERSION)
    parser.add_argument("--max-claims", type=int, default=DEFAULT_MAX_CLAIMS)
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--silver-dir", type=Path, default=DEFAULT_SILVER_DIR)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="call a registered provider adapter; unavailable until SDK approval",
    )
    args = parser.parse_args(argv)
    if args.sample < 1:
        parser.error("--sample must be at least 1")
    if args.max_calls < 1:
        parser.error("--max-calls must be at least 1")

    manifest = read_manifest(args.manifest)
    papers = read_papers_csv(args.manifest.parent / Path(manifest.files.papers_csv).name)
    settings = Settings()
    cache_dir = args.cache_dir or settings.resolved_europepmc_cache_dir

    try:
        plans, report = build_plan(
            papers,
            cache_dir,
            sample_size=args.sample,
            seed=args.seed,
            prompt_version=args.prompt_version,
            max_claims=args.max_claims,
        )
    except PromptError as exc:
        print(f"prompt error: {exc}", flush=True)
        return 1
    if not plans:
        print("no usable papers in the sample; run the corpus ingest first", flush=True)
        return 1

    estimate = dry_run_estimate(plans, report, seed=args.seed, prompt_version=args.prompt_version)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    report_md = Path(f"{args.out}.md")
    report_json = Path(f"{args.out}.json")
    report_md.write_text(_markdown(estimate, report), encoding="utf-8", newline="\n")
    report_json.write_text(
        json.dumps(
            {
                "plan": {
                    "requested": report.requested,
                    "with_text": report.with_text,
                    "missing_fulltext": report.missing_fulltext,
                    "parse_failures": report.parse_failures,
                    "empty_documents": report.empty_documents,
                    "mean_prompt_tokens": report.mean_prompt_tokens,
                    "median_prompt_tokens": report.median_prompt_tokens,
                    "p95_prompt_tokens": report.p95_prompt_tokens,
                },
                "estimate": estimate.model_dump(),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(
        f"planned={report.with_text} prompt_tokens={estimate.prompt_tokens_total:,} "
        f"expected_claims@5={estimate.expected_claims_by_scenario.get('5', 0):,.0f}",
        flush=True,
    )
    print(f"report: {report_md}", flush=True)
    print(f"json: {report_json}", flush=True)

    if not args.execute:
        return 0

    if not ProviderAdapter.__subclasses__():
        print(
            "no provider adapter is registered or shipped; install and approve a "
            "provider SDK and implement ProviderAdapter before --execute",
            flush=True,
        )
        return 1

    print(
        "--execute is not wired in this session: construct the approved adapter and "
        "pass it to axion.extract.baseline.run_extraction",
        flush=True,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
