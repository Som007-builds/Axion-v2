"""Plan or run the P1-10 baseline claim extraction (offline by default).

Dry run (default): parse the seeded sample, render the versioned prompt, and
estimate calls/tokens. It makes no LLM call and never needs prices.

Execute (``--execute``): calls the owner-approved Gemini free-tier adapter
through ``LLMClient``, writes silver candidates plus audit-ready context, paces
requests against the free-tier RPM/RPD limits, and stops cleanly at the daily
quota or a provider failure. Real spend stays zero; list-price cost is recorded.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

from axion.config.pricing import estimate_cost_details, load_pricing
from axion.config.settings import DEFAULT_RATE_LIMITS_PATH, Settings
from axion.eval.audit import (
    DEFAULT_SEED as AUDIT_SEED,
)
from axion.eval.audit import (
    MIN_SAMPLE,
    assign_paper_splits,
    corpus_snapshot_id,
    export_rows,
    load_claims,
    sample_claims,
    write_export,
)
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
from axion.llm.gemini import GeminiAdapter
from axion.llm.ledger import SQLiteLedger
from axion.llm.pacing import (
    PACIFIC,
    PacingConfigError,
    RateLimit,
    RateLimitTable,
    RequestPacer,
    load_rate_limits,
    next_midnight_pacific,
    requests_by_pacific_day,
)
from axion.llm.providers import ProviderRegistry

DEFAULT_MANIFEST = Path("docs/reports/P1-corpus-manifest.json")
DEFAULT_OUT = Path("docs/reports/P1-baseline-estimate")
DEFAULT_SILVER_DIR = Path("eval/silver/claims_v1")
DEFAULT_AUDIT_OUT = Path("eval/audit/claims_audit_v1.csv")
DEFAULT_MAX_OUTPUT_TOKENS = 8192
AUDIT_MIN_ACCEPTED_CLAIMS = 250


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
            "1. Provider hosting: Google Gemini free tier via AI Studio.",
            "2. Baseline tiers: `gemini-3.5-flash-lite` (small) and `gemini-3.8-flash` " "(large).",
            "3. Prices: official Google list prices, checked 2026-11-15; free-tier calls "
            "record list price with `billing=free_tier` and real spend $0.",
            "4. Free-tier limits: 3.8 Flash 5 RPM / 250K TPM / 20 RPD; 3.5 Flash-Lite "
            "15 RPM / 250K TPM / 500 RPD. RPD resets at midnight Pacific.",
            "5. SDK: the official `google-genai==2.8.0` package is pinned and installed "
            "behind `src/axion/llm/gemini.py`.",
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
    if "daily quota" in cleaned.lower() or "perday" in cleaned.lower().replace("_", ""):
        return "Gemini daily quota exhausted; resume after the Pacific reset"
    return cleaned[:300]


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


def _build_client(settings: Settings, *, max_output_tokens: int) -> LLMClient:
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEY is not set; cannot run the Gemini baseline")
    registry = ProviderRegistry()
    registry.register(
        GeminiAdapter(
            settings.gemini_api_key,
            timeout_s=120.0,
            max_output_tokens=max_output_tokens,
        )
    )
    return LLMClient.from_settings(settings, registry)


@dataclass(frozen=True)
class Projection:
    call_usd: Decimal
    total_usd: Decimal
    post_call_usd: Decimal
    post_total_usd: Decimal


def _worst_case_projection(
    plans: list[PaperPlan],
    *,
    pricing_path: Path,
    model: str,
    max_output_tokens: int,
    already_spent: Decimal,
    already_post_spent: Decimal,
    on_date: date,
) -> Projection:
    """Worst-case list-price projection for the remaining calls."""
    pricing = load_pricing(pricing_path)
    worst = Decimal("0")
    worst_post = Decimal("0")
    for plan in plans:
        prompt = int(plan.prompt_tokens_estimate * 1.2) + 512
        details = estimate_cost_details(
            pricing,
            model,
            prompt,
            max_output_tokens,
            dry_run=False,
            on_date=on_date,
        )
        if details.usd is None or details.post_promotion_usd is None:
            raise ValueError(f"missing list price for {model!r}")
        worst = max(worst, details.usd)
        worst_post = max(worst_post, details.post_promotion_usd)
    return Projection(
        call_usd=worst,
        total_usd=already_spent + worst * len(plans),
        post_call_usd=worst_post,
        post_total_usd=already_post_spent + worst_post * len(plans),
    )


def _maybe_export_audit(
    run: RunReport,
    *,
    out_path: Path,
    sample_size: int = MIN_SAMPLE,
    seed: int = AUDIT_SEED,
) -> dict[str, object] | None:
    """Create the audit CSV once >=250 accepted claims exist; never overwrite."""
    if run.claims < AUDIT_MIN_ACCEPTED_CLAIMS:
        return None
    if out_path.exists():
        return {"path": str(out_path), "status": "already_exists"}
    claims = load_claims(run.candidates_path)
    sample = sample_claims(claims, sample_size, seed=seed)
    rows = export_rows(sample, seed=seed)
    write_export(out_path, rows)
    paper_ids = sorted({claim.paper_id for claim in sample})
    splits = assign_paper_splits(paper_ids, seed=seed)
    split_counts = Counter(splits.values())
    summary: dict[str, object] = {
        "path": str(out_path),
        "status": "written",
        "claims": len(sample),
        "papers": len(paper_ids),
        "papers_dev": split_counts.get("dev", 0),
        "papers_test": split_counts.get("test", 0),
        "seed": seed,
        "corpus_snapshot_id": corpus_snapshot_id(claims),
        "source_candidates": str(run.candidates_path),
    }
    summary_path = out_path.with_suffix(".summary.json")
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return summary


def _write_run_report(
    *,
    run: RunReport,
    plans: list[PaperPlan],
    ledger: SQLiteLedger,
    run_id: str,
    estimate_prompt_tokens: int,
    out_dir: Path,
    model: str,
    provider: str,
    prompt_version: str,
    thinking_level: str | None,
    temperature: float | None,
    max_output_tokens: int,
    billing: str,
    rate: RateLimit,
    rate_table: RateLimitTable,
    audit_summary: dict[str, object] | None,
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
    post_cost = sum((call.usd_post_promotion or Decimal("0") for call in completed), Decimal("0"))
    real_cost = sum(
        (call.usd or Decimal("0") for call in completed if call.billing == "paid"),
        Decimal("0"),
    )
    input_cost = sum((call.input_usd or Decimal("0") for call in completed), Decimal("0"))
    output_cost = sum((call.output_usd or Decimal("0") for call in completed), Decimal("0"))
    latencies = [call.latency_ms for call in completed if call.latency_ms is not None]

    per_paper: dict[str, dict[str, Decimal | int | float]] = defaultdict(
        lambda: {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "usd": Decimal("0"),
            "post_usd": Decimal("0"),
            "real_usd": Decimal("0"),
            "input_usd": Decimal("0"),
            "output_usd": Decimal("0"),
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
        row["post_usd"] = Decimal(str(row["post_usd"])) + (call.usd_post_promotion or Decimal("0"))
        row["real_usd"] = Decimal(str(row["real_usd"])) + (
            (call.usd or Decimal("0")) if call.billing == "paid" else Decimal("0")
        )
        row["input_usd"] = Decimal(str(row["input_usd"])) + (call.input_usd or Decimal("0"))
        row["output_usd"] = Decimal(str(row["output_usd"])) + (call.output_usd or Decimal("0"))
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
    strict_extracted = run.strict_claims + run.strict_span_failures
    strict_rate = (run.strict_claims / strict_extracted) if strict_extracted else 1.0
    paper_costs = [float(row["usd"]) for row in per_paper.values()]
    paper_tokens = [
        int(row["prompt_tokens"]) + int(row["completion_tokens"]) for row in per_paper.values()
    ]
    paper_rows = [
        {
            "paper_id": key,
            "calls": int(row["calls"]),
            "prompt_tokens": int(row["prompt_tokens"]),
            "completion_tokens": int(row["completion_tokens"]),
            "reasoning_tokens": int(row["reasoning_tokens"]),
            "total_tokens": int(row["prompt_tokens"]) + int(row["completion_tokens"]),
            "usd": format(Decimal(str(row["usd"])), "f"),
            "post_promotion_usd": format(Decimal(str(row["post_usd"])), "f"),
            "real_usd": format(Decimal(str(row["real_usd"])), "f"),
            "input_usd": format(Decimal(str(row["input_usd"])), "f"),
            "output_usd": format(Decimal(str(row["output_usd"])), "f"),
            "latency_ms": float(row["latency_ms"]),
        }
        for key, row in sorted(per_paper.items())
    ]
    gap = (prompt_tokens / estimate_prompt_tokens - 1.0) if estimate_prompt_tokens else 0.0
    model_calls = ledger.calls_for_model(model) if model else ()
    requests_by_day = requests_by_pacific_day(model_calls)
    today = datetime.now(UTC).astimezone(PACIFIC).date()
    requests_today = requests_by_day.get(today.isoformat(), 0)
    accepted = run.claims
    cost_per_claim = (cost / accepted) if accepted else Decimal("0")
    post_cost_per_claim = (post_cost / accepted) if accepted else Decimal("0")
    output_share = (output_cost / cost) if cost else Decimal("0")
    price_versions = sorted(
        {call.price_version for call in completed if call.price_version is not None}
    )
    report = {
        "run_id": run_id,
        "papers_processed": run.papers_processed,
        "claims": run.claims,
        "accepted_claims": accepted,
        "failures": run.failures,
        "parse_failures": parse_failures,
        "evidence_span_failures": span_failures,
        "evidence_span_verbatim_rate": round(verbatim_rate, 6),
        "strict_claims": run.strict_claims,
        "strict_evidence_span_failures": run.strict_span_failures,
        "strict_evidence_span_verbatim_rate": round(strict_rate, 6),
        "normalization_fixes": run.normalization_fixes,
        "calls": len(completed),
        "failed_calls": failed_calls,
        "cache_hits": cache_hits,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "list_price_usd": format(cost, "f"),
        "post_promotion_usd": format(post_cost, "f"),
        "real_spend_usd": format(real_cost, "f"),
        "input_usd": format(input_cost, "f"),
        "output_usd": format(output_cost, "f"),
        "output_cost_share": round(float(output_share), 6),
        "cost_per_accepted_claim_usd": format(cost_per_claim, "f"),
        "post_promotion_cost_per_accepted_claim_usd": format(post_cost_per_claim, "f"),
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
        "papers": paper_rows,
        "latency_ms": {
            "mean": statistics.fmean(latencies) if latencies else 0.0,
            "p95": _percentile(latencies, 0.95),
        },
        "config": {
            "provider": provider,
            "model": model,
            "prompt_version": prompt_version,
            "thinking_level": thinking_level,
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
            "billing": billing,
            "price_versions": price_versions,
        },
        "rate_limits": {
            "rpm": rate.rpm,
            "tpm": rate.tpm,
            "rpd": rate.rpd,
            "daily_margin": rate.daily_margin,
            "daily_cap": rate.daily_cap,
            "min_interval_s": rate.min_interval_s,
            "source": rate_table.source,
            "checked": rate_table.checked,
        },
        "requests_by_day": requests_by_day,
        "requests_today": requests_today,
        "daily_cap": rate.daily_cap,
        "resume_after": next_midnight_pacific(today),
        "stopped_reason": run.stopped_reason,
        "provider_failure_detail": error_detail,
        "candidates_path": str(run.candidates_path),
        "claims_path": str(run.claims_path),
        "manifest_path": str(run.manifest_path),
        "audit_export": audit_summary,
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
        f"- Provider/model: `{provider}` / `{model}`",
        f"- Config: thinking `{thinking_level}`, temperature `{temperature}`, "
        f"max output `{max_output_tokens}`, billing `{billing}`",
        f"- Prompt version: `{prompt_version}`",
        f"- Papers processed: **{run.papers_processed}**",
        f"- Accepted silver candidate claims: **{run.claims}**",
        f"- Failures: **{run.failures}** (structured output: {parse_failures}; "
        f"span not verbatim: {span_failures})",
        f"- Evidence-span verbatim rate (accepted / extracted): **{verbatim_rate:.1%}**",
        f"- Strict pre-normalization rate: **{strict_rate:.1%}** "
        f"({run.normalization_fixes} fixed by normalization)",
        f"- Calls: **{len(completed)} succeeded**, **{failed_calls} failed** "
        f"(cache hits: {cache_hits})",
        f"- Tokens: prompt **{prompt_tokens:,}**, completion **{completion_tokens:,}** "
        f"(reasoning **{reasoning_tokens:,}**), total **{prompt_tokens + completion_tokens:,}**",
        f"- List-price cost at call-date price: **${cost:.6f}**; post-promotion: "
        f"**${post_cost:.6f}**; real spend: **${real_cost:.6f}**",
        f"- Cost per accepted claim (includes rejected-claim tokens): **${cost_per_claim:.6f}** "
        f"(post-promotion **${post_cost_per_claim:.6f}**)",
        f"- Output-token share of list price (incl. thinking): **{output_share:.1%}**",
        f"- Prompt-token gap vs chars/4 estimate: **{gap:+.1%}** "
        f"({estimate_prompt_tokens:,} estimated)",
        f"- Free-tier requests today: **{requests_today}/{rate.daily_cap}** "
        f"(RPD {rate.rpd}, margin {rate.daily_margin}); resume after "
        f"**{next_midnight_pacific(today)}** if stopped.",
        "",
        "## Per paper",
        "",
        "| Metric | Mean | Median | p95 |",
        "| :-- | --: | --: | --: |",
        f"| Prompt tokens | {report['per_paper']['mean_prompt_tokens']:,.0f} | — | — |",
        f"| Completion tokens | {report['per_paper']['mean_completion_tokens']:,.0f} | — | — |",
        f"| Reasoning tokens | {report['per_paper']['mean_reasoning_tokens']:,.0f} | — | — |",
        f"| Total tokens | {report['per_paper']['mean_total_tokens']:,.0f} | — | — |",
        f"| USD (call-date) | {report['per_paper']['mean_usd']:.6f} | "
        f"{report['per_paper']['median_usd']:.6f} | {report['per_paper']['p95_usd']:.6f} |",
        "",
        "## Per-paper records",
        "",
        "| Paper | Calls | Prompt | Completion | Reasoning | Total | USD | "
        "Post-promo USD | Latency ms |",
        "| :-- | --: | --: | --: | --: | --: | --: | --: | --: |",
        *[
            f"| `{row['paper_id']}` | {row['calls']} | {row['prompt_tokens']:,} | "
            f"{row['completion_tokens']:,} | {row['reasoning_tokens']:,} | "
            f"{row['total_tokens']:,} | {row['usd']} | {row['post_promotion_usd']} | "
            f"{row['latency_ms']:.0f} |"
            for row in report["papers"]
        ],
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
        *(
            [
                "Audit export: "
                f"`{report['audit_export']['path']}` "
                f"({report['audit_export']['status']}; "
                f"{report['audit_export'].get('claims', '?')} claims, "
                f"{report['audit_export'].get('papers', '?')} papers).",
                "",
            ]
            if report["audit_export"]
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
    parser.add_argument("--thinking-level", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--billing", choices=("free_tier", "paid"), default=None)
    parser.add_argument("--rate-limits", type=Path, default=DEFAULT_RATE_LIMITS_PATH)
    parser.add_argument("--audit-out", type=Path, default=DEFAULT_AUDIT_OUT)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="call the approved Gemini adapter through LLMClient (free-tier run)",
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
    billing = args.billing or settings.llm_billing
    thinking_level = args.thinking_level or settings.llm_thinking_level
    temperature = args.temperature if args.temperature is not None else settings.llm_temperature
    settings = settings.model_copy(update={"llm_billing": billing})
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
        print("AXION_DRY_RUN is true; set it to false for the owner-approved run", flush=True)
        return 1
    if not settings.llm_large_model:
        print("LLM_LARGE_MODEL is not configured", flush=True)
        return 1
    if not settings.llm_provider_chain or settings.llm_provider_chain[0] != "gemini":
        print("LLM_PROVIDER_CHAIN must start with 'gemini' for this baseline", flush=True)
        return 1

    try:
        rate_table = load_rate_limits(args.rate_limits)
        rate = rate_table.require(settings.llm_large_model)
    except (PacingConfigError, ValueError) as exc:
        print(f"pacing error: {exc}", flush=True)
        return 1

    ledger = SQLiteLedger(settings.resolved_ledger_path)
    today = datetime.now(UTC).astimezone(PACIFIC).date()
    already_spent = ledger.report("stage").total_usd
    already_post_spent = sum(
        (
            call.usd_post_promotion or Decimal("0")
            for call in ledger.calls_for_model(settings.llm_large_model)
        ),
        Decimal("0"),
    )
    already_real = ledger.total_real_usd()
    try:
        projection = _worst_case_projection(
            plans,
            pricing_path=settings.resolved_pricing_path,
            model=settings.llm_large_model,
            max_output_tokens=args.max_output_tokens,
            already_spent=already_spent,
            already_post_spent=already_post_spent,
            on_date=today,
        )
    except ValueError as exc:
        print(f"pricing error: {exc}", flush=True)
        return 1
    print(
        f"worst-case list-price projection=${projection.total_usd:.6f} "
        f"(post-promotion ${projection.post_total_usd:.6f}) for {len(plans)} calls; "
        f"real spend=${already_real:.6f} of ${args.budget_usd:.2f} cap",
        flush=True,
    )
    if billing == "paid" and projection.total_usd > args.budget_usd:
        print("projected paid spend exceeds the owner cap; refusing to start", flush=True)
        return 1
    if billing == "free_tier":
        print("free-tier run: list price is recorded, real spend stays $0", flush=True)

    run_id = args.run_id or f"p1-10-{settings.llm_provider_chain[0]}-s{args.seed}-n{args.sample}"
    try:
        client = _build_client(settings, max_output_tokens=args.max_output_tokens)
    except ValueError as exc:
        print(f"provider error: {exc}", flush=True)
        return 1

    model_calls = ledger.calls_for_model(settings.llm_large_model)
    pacer = RequestPacer.from_calls(rate, model_calls)
    print(
        f"pacing: {rate.rpm} RPM, {rate.rpd} RPD, margin {rate.daily_margin}, "
        f"cap {rate.daily_cap}/day, {pacer.requests_today} used today",
        flush=True,
    )
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
        thinking_level=thinking_level,
        temperature=temperature,
        pacer=pacer,
    )
    audit_summary = _maybe_export_audit(run, out_path=args.audit_out)
    report_path = _write_run_report(
        run=run,
        plans=plans,
        ledger=ledger,
        run_id=run_id,
        estimate_prompt_tokens=estimate_prompt_tokens,
        out_dir=args.silver_dir,
        model=settings.llm_large_model,
        provider=settings.llm_provider_chain[0],
        prompt_version=args.prompt_version,
        thinking_level=thinking_level,
        temperature=temperature,
        max_output_tokens=args.max_output_tokens,
        billing=billing,
        rate=rate,
        rate_table=rate_table,
        audit_summary=audit_summary,
    )
    total_list = ledger.report("stage").total_usd
    total_real = ledger.total_real_usd()
    print(
        f"run={run_id} papers={run.papers_processed} claims={run.claims} "
        f"failures={run.failures} calls={run.calls} stopped={run.stopped_reason}",
        flush=True,
    )
    print(f"run report: {report_path}", flush=True)
    print(
        f"P1 cumulative list-price cost: ${total_list:.6f}; real spend: ${total_real:.6f}",
        flush=True,
    )
    if audit_summary:
        print(f"audit export: {audit_summary['path']} ({audit_summary['status']})", flush=True)
        print("open the labeling tool:", flush=True)
        print(
            '  start "" "D:\\Axion-v2\\axion-v2\\eval\\audit\\claim_audit_tool.html"',
            flush=True,
        )
        print(f"  then load {Path(str(audit_summary['path'])).resolve()}", flush=True)
    if run.stopped_reason == "daily_quota_reached":
        print(
            f"daily quota reached; resume after {next_midnight_pacific(today)} "
            "(midnight America/Los_Angeles)",
            flush=True,
        )
    if total_real > args.budget_usd:
        print("REAL-SPEND CAP EXCEEDED; stop and report to the owner", flush=True)
        return 1
    return 0 if run.stopped_reason is None else 2


if __name__ == "__main__":
    raise SystemExit(main())
