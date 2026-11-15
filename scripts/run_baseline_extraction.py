"""Plan or run the P1-10 baseline claim extraction (offline by default).

Dry run (default): parse the seeded sample, render the versioned prompt, and
estimate calls/tokens. It makes no LLM call and never needs prices.
Execute: calls the owner-approved Groq adapter through ``LLMClient``, writes
silver candidates plus audit-ready context, and stops cleanly at the budget cap
or a provider failure. The paid run is opt-in with ``--execute``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from axion.config.pricing import estimate_cost, load_pricing
from axion.config.settings import Settings
from axion.extract.baseline import (
    DEFAULT_MAX_CALLS,
    DEFAULT_MAX_CLAIMS,
    DryRunEstimate,
    PaperPlan,
    PlanReport,
    RunReport,
    build_plan,
    dry_run_estimate,
    run_extraction,
)
from axion.extract.claims import PROMPT_VERSION
from axion.extract.prompting import PromptError
from axion.ingest.corpus import read_manifest, read_papers_csv
from axion.llm.client import LLMClient
from axion.llm.groq import GroqAdapter
from axion.llm.ledger import SQLiteLedger
from axion.llm.providers import ProviderRegistry

DEFAULT_MANIFEST = Path("docs/reports/P1-corpus-manifest.json")
DEFAULT_OUT = Path("docs/reports/P1-baseline-estimate")
DEFAULT_SILVER_DIR = Path("eval/silver/claims_v1")
DEFAULT_MAX_OUTPUT_TOKENS = 8192


def _markdown(estimate: DryRunEstimate, plan: PlanReport) -> str:
    values = estimate.model_dump()
    lines = [
        "# P1 baseline extraction — dry-run plan (ESTIMATE)",
        "",
        "**No extractor was run and no LLM call was made.** This plan parses real",
        "corpus text and estimates prompt tokens; the claims/paper rate is a scenario,",
        "not a measurement. Prices are verified for the paid run, but this file is",
        "not a cost measurement.",
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
            "Formula used by the paid run: `input_tokens * input_price_per_Mtok / 1e6 + "
            "output_tokens * output_price_per_Mtok / 1e6`.",
            "",
            "## Owner inputs status",
            "",
            "1. Provider hosting: Groq `openai/gpt-oss-120b` (large tier).",
            "2. Prices: filled in `src/axion/config/pricing.yaml` from the official Groq",
            "   model pages, checked 2026-11-15.",
            "3. Budget: a $3 total P1-10 cap is recorded in the untracked private budget file.",
            "4. SDK: the official `groq==1.7.0` package is approved, pinned, and installed",
            "   behind `src/axion/llm/groq.py`.",
            "5. Remaining blocker: the Groq free tier allows 8,000 tokens per minute and",
            "   200,000 per day; this plan's mean prompt is 7,641 tokens and its p95 is",
            "   15,867, so the paid run cannot complete without an owner decision on the",
            "   limit, provider, or sampling rule.",
            "",
        ]
    )
    return "\n".join(lines)


def _error_summary(error: str | None) -> str | None:
    if not error:
        return None
    cleaned = re.sub(r"organization `[^`]+` ", "", error)
    cleaned = re.sub(r"organization [^ ]+ ", "", cleaned)
    if "rate_limit_exceeded" in cleaned or "tokens per minute" in cleaned:
        limit = re.search(r"TPM\): Limit (\d+)", cleaned)
        requested = re.search(r"Requested (\d+)", cleaned)
        if limit and requested:
            return (
                f"Groq rate limit: request {requested.group(1)} tokens exceeds "
                f"TPM {limit.group(1)}"
            )
        return "Groq rate limit exceeded"
    return cleaned[:300]


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


def _build_client(settings: Settings, *, max_output_tokens: int) -> LLMClient:
    if not settings.groq_api_key:
        raise ValueError("GROQ_API_KEY is not set; cannot run the paid baseline")
    registry = ProviderRegistry()
    registry.register(
        GroqAdapter(
            settings.groq_api_key,
            timeout_s=120.0,
            max_output_tokens=max_output_tokens,
        )
    )
    return LLMClient.from_settings(settings, registry)


def _worst_case_projection(
    plans: list[PaperPlan],
    *,
    pricing_path: Path,
    model: str,
    max_output_tokens: int,
    already_spent: Decimal,
) -> tuple[Decimal, Decimal]:
    """Return (worst-case total USD, worst-case USD for one call)."""
    pricing = load_pricing(pricing_path)
    worst = Decimal("0")
    for plan in plans:
        prompt = int(plan.prompt_tokens_estimate * 1.2) + 512
        cost = estimate_cost(
            pricing,
            model,
            prompt,
            max_output_tokens,
            dry_run=False,
        )
        if cost is None:
            raise ValueError(f"missing list price for {model!r}")
        worst = max(worst, cost)
    return already_spent + worst * len(plans), worst


def _write_run_report(
    *,
    run: RunReport,
    plans: list[PaperPlan],
    ledger: SQLiteLedger,
    run_id: str,
    estimate_prompt_tokens: int,
    out_dir: Path,
) -> Path:
    processed_path = run.claims_path.parent / "papers_processed.jsonl"
    processed_ids = set()
    if processed_path.exists():
        for line in processed_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                processed_ids.add(str(json.loads(line).get("paper_id")))
    if processed_ids:
        estimate_prompt_tokens = sum(
            plan.prompt_tokens_estimate for plan in plans if plan.paper.pmcid in processed_ids
        )
    calls = ledger.calls_for_run(run_id)
    completed = [
        call
        for call in calls
        if call.error is None and not call.cache_hit and call.prompt_tokens > 0
    ]
    cache_hits = sum(1 for call in calls if call.cache_hit)
    failed_calls = sum(1 for call in calls if call.error)
    prompt_tokens = sum(call.prompt_tokens for call in completed)
    completion_tokens = sum(call.completion_tokens for call in completed)
    reasoning_tokens = sum(call.reasoning_tokens for call in completed)
    cost = sum((call.usd or Decimal("0") for call in completed), Decimal("0"))
    latencies = [call.latency_ms for call in completed if call.latency_ms is not None]

    per_paper: dict[str, dict[str, float | int | str]] = defaultdict(
        lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "usd": Decimal("0"),
            "latency_ms": 0.0,
            "calls": 0,
        }
    )
    for call in completed:
        key = call.paper_id or "unknown"
        row = per_paper[key]
        row["prompt_tokens"] = int(row["prompt_tokens"]) + call.prompt_tokens
        row["completion_tokens"] = int(row["completion_tokens"]) + call.completion_tokens
        row["reasoning_tokens"] = int(row["reasoning_tokens"]) + call.reasoning_tokens
        row["usd"] = Decimal(str(row["usd"])) + (call.usd or Decimal("0"))
        row["latency_ms"] = float(row["latency_ms"]) + (call.latency_ms or 0.0)
        row["calls"] = int(row["calls"]) + 1

    failures = []
    if run.failures_path.exists():
        for line in run.failures_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                failures.append(json.loads(line))
    parse_failures = sum(1 for row in failures if row.get("reason") == "structured_output")
    span_failures = sum(1 for row in failures if row.get("reason") == "evidence_span_not_verbatim")
    ledger_errors = [call.error for call in calls if call.error]
    error_detail = _error_summary(ledger_errors[-1] if ledger_errors else None)
    extracted = run.claims + span_failures
    verbatim_rate = (run.claims / extracted) if extracted else 1.0
    paper_costs = [float(row["usd"]) for row in per_paper.values()]
    paper_tokens = [
        int(row["prompt_tokens"]) + int(row["completion_tokens"]) for row in per_paper.values()
    ]
    gap = (prompt_tokens / estimate_prompt_tokens - 1.0) if estimate_prompt_tokens else 0.0
    report = {
        "run_id": run_id,
        "papers_processed": run.papers_processed,
        "claims": run.claims,
        "failures": run.failures,
        "parse_failures": parse_failures,
        "evidence_span_failures": span_failures,
        "evidence_span_verbatim_rate": round(verbatim_rate, 6),
        "calls": len(completed),
        "failed_calls": failed_calls,
        "cache_hits": cache_hits,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "list_price_usd": format(cost, "f"),
        "estimate_prompt_tokens": estimate_prompt_tokens,
        "prompt_token_gap_fraction": round(gap, 6),
        "per_paper": {
            "mean_prompt_tokens": statistics.fmean(
                [int(row["prompt_tokens"]) for row in per_paper.values()]
            )
            if per_paper
            else 0.0,
            "mean_completion_tokens": statistics.fmean(
                [int(row["completion_tokens"]) for row in per_paper.values()]
            )
            if per_paper
            else 0.0,
            "mean_reasoning_tokens": statistics.fmean(
                [int(row["reasoning_tokens"]) for row in per_paper.values()]
            )
            if per_paper
            else 0.0,
            "mean_total_tokens": statistics.fmean(paper_tokens) if paper_tokens else 0.0,
            "mean_usd": statistics.fmean(paper_costs) if paper_costs else 0.0,
            "median_usd": statistics.median(paper_costs) if paper_costs else 0.0,
            "p95_usd": _percentile(paper_costs, 0.95),
        },
        "latency_ms": {
            "mean": statistics.fmean(latencies) if latencies else 0.0,
            "p95": _percentile(latencies, 0.95),
        },
        "stopped_reason": run.stopped_reason,
        "provider_failure_detail": error_detail,
        "candidates_path": str(run.candidates_path),
        "claims_path": str(run.claims_path),
        "manifest_path": str(run.manifest_path),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "run_report.json"
    json_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    lines = [
        "# P1-10 baseline extraction — measured run",
        "",
        *(
            ["> **PARTIAL RUN:** stopped before the planned sample; this is not a baseline.", ""]
            if run.stopped_reason
            else []
        ),
        f"- Run id: `{run_id}`",
        f"- Papers processed: **{run.papers_processed}**",
        f"- Silver candidate claims: **{run.claims}**",
        f"- Failures: **{run.failures}** (structured output: {parse_failures}; "
        f"span not verbatim: {span_failures})",
        f"- Evidence-span verbatim rate (accepted / extracted): **{verbatim_rate:.1%}**",
        f"- Calls: **{len(completed)} succeeded**, **{failed_calls} failed** "
        f"(cache hits: {cache_hits})",
        f"- Tokens: prompt **{prompt_tokens:,}**, completion **{completion_tokens:,}** "
        f"(reasoning **{reasoning_tokens:,}**), total **{prompt_tokens + completion_tokens:,}**",
        f"- List-price cost: **${cost:.6f}**",
        f"- Prompt-token gap vs chars/4 estimate: **{gap:+.1%}** "
        f"({estimate_prompt_tokens:,} estimated)",
        "",
        "## Per paper",
        "",
        "| Metric | Mean | Median | p95 |",
        "| :-- | --: | --: | --: |",
        f"| Prompt tokens | {report['per_paper']['mean_prompt_tokens']:,.0f} | — | — |",
        f"| Completion tokens | {report['per_paper']['mean_completion_tokens']:,.0f} | — | — |",
        f"| Reasoning tokens | {report['per_paper']['mean_reasoning_tokens']:,.0f} | — | — |",
        f"| Total tokens | {report['per_paper']['mean_total_tokens']:,.0f} | — | — |",
        f"| USD | {report['per_paper']['mean_usd']:.6f} | "
        f"{report['per_paper']['median_usd']:.6f} | {report['per_paper']['p95_usd']:.6f} |",
        "",
        f"Latency: mean **{report['latency_ms']['mean']:.0f} ms**, "
        f"p95 **{report['latency_ms']['p95']:.0f} ms**.",
        "",
        f"Stopped reason: **{run.stopped_reason or 'completed'}**.",
        *(
            [f"Provider detail: `{report['provider_failure_detail']}`", ""]
            if report["provider_failure_detail"]
            else []
        ),
        "Silver candidates are training-only and are not gold labels.",
        "",
    ]
    md_path = out_dir / "run_report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return json_path


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
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--budget-usd", type=Decimal, default=Decimal("3.00"))
    parser.add_argument("--max-output-tokens", type=int, default=DEFAULT_MAX_OUTPUT_TOKENS)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="call the approved Groq adapter through LLMClient (paid run)",
    )
    args = parser.parse_args(argv)
    if args.sample < 1:
        parser.error("--sample must be at least 1")
    if args.max_calls < 1:
        parser.error("--max-calls must be at least 1")
    if args.budget_usd <= 0:
        parser.error("--budget-usd must be positive")
    if args.max_output_tokens < 1:
        parser.error("--max-output-tokens must be positive")

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

    if settings.dry_run:
        print("AXION_DRY_RUN is true; set it to false for the owner-approved paid run", flush=True)
        return 1
    if not settings.llm_large_model:
        print("LLM_LARGE_MODEL is not configured", flush=True)
        return 1

    ledger = SQLiteLedger(settings.resolved_ledger_path)
    already_spent = ledger.report("stage").total_usd
    if already_spent >= args.budget_usd:
        print(
            f"budget cap reached: spent ${already_spent:.6f} of ${args.budget_usd:.2f}",
            flush=True,
        )
        return 1
    try:
        projection, worst_call = _worst_case_projection(
            plans,
            pricing_path=settings.resolved_pricing_path,
            model=settings.llm_large_model,
            max_output_tokens=args.max_output_tokens,
            already_spent=already_spent,
        )
    except ValueError as exc:
        print(f"pricing error: {exc}", flush=True)
        return 1
    print(
        f"worst-case projection=${projection:.6f} for {len(plans)} calls "
        f"(cap ${args.budget_usd:.2f}; worst call ${worst_call:.6f})",
        flush=True,
    )
    if projection > args.budget_usd:
        print("projected worst-case cost exceeds the owner cap; refusing to start", flush=True)
        return 1

    run_id = args.run_id or f"p1-10-s{args.seed}-n{args.sample}"
    try:
        client = _build_client(settings, max_output_tokens=args.max_output_tokens)
    except ValueError as exc:
        print(f"provider error: {exc}", flush=True)
        return 1

    estimate_prompt_tokens = sum(plan.prompt_tokens_estimate for plan in plans)
    run = run_extraction(
        client,
        plans,
        run_id=run_id,
        output_dir=args.silver_dir,
        corpus_manifest_sha256=hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
        papers_file=manifest.files.papers_csv,
        papers_sha256=manifest.files.papers_sha256,
        sample_size=args.sample,
        seed=args.seed,
        prompt_version=args.prompt_version,
        max_calls=args.max_calls,
        max_output_tokens=args.max_output_tokens,
    )
    report_path = _write_run_report(
        run=run,
        plans=plans,
        ledger=ledger,
        run_id=run_id,
        estimate_prompt_tokens=estimate_prompt_tokens,
        out_dir=args.silver_dir,
    )
    total_spent = ledger.report("stage").total_usd
    print(
        f"run={run_id} papers={run.papers_processed} claims={run.claims} "
        f"failures={run.failures} calls={run.calls} stopped={run.stopped_reason}",
        flush=True,
    )
    print(f"run report: {report_path}", flush=True)
    print(f"P1-10 cumulative list-price spend: ${total_spent:.6f}", flush=True)
    if total_spent > args.budget_usd:
        print("BUDGET CAP EXCEEDED; stop and report to the owner", flush=True)
        return 1
    return 0 if run.stopped_reason is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
