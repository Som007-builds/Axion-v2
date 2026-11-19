"""P3-08 cost accounting scaffold and the SILVER PLAN sizing (no calls, no training).

Two jobs, both from committed files:

``--section cost``    cost per context, escalation rate ``e``, student share ``s`` and
                      dollars per retraction analysed at list price, with the corpus
                      projection labelled **PROJECTED** and its assumptions spelled out.
``--section silver``  size and cost of teacher-labelling the non-gold, non-test-source
                      contexts for a later distilled student. Planning numbers only;
                      nothing is run and no label is created.

Every price comes from ``src/axion/config/pricing.yaml`` and the token count is the
project's ``ceil(chars/4)`` heuristic, labelled as such.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from collections import Counter
from decimal import Decimal
from pathlib import Path

from axion.config.pricing import estimate_cost_details, load_pricing
from axion.config.settings import Settings
from scripts.dependency_baselines import load_rows, scored_rows, spec_rows
from scripts.dependency_llm_v2 import estimate
from scripts.dependency_sample import SEED as SAMPLE_SEED
from scripts.dependency_sample import _assign_splits

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "audit" / "p3-05"
CANDIDATES = ROOT / "data" / "p3-03" / "candidates.json"
COST_REPORT = ROOT / "docs" / "reports" / "P3-08-cost-scaffold.md"
SILVER_REPORT = ROOT / "docs" / "reports" / "P3-05-silver-plan.md"
COST_SUMMARY = OUT / "p3-08-cost.json"
SILVER_SUMMARY = OUT / "p3-05-silver-plan.json"
DETECTOR_SUMMARY = OUT / "p3-05-dev-detector.json"

MODEL = "gemini-3.5-flash-lite"
WAVES = (
    ROOT / "eval" / "audit" / "p3-03" / "p3-03-wave1-manifest.csv",
    ROOT / "eval" / "audit" / "p3-03" / "p3-03-wave2-manifest.csv",
)
# ADR-0023: the split is by source paper and frozen. Every context of a test source
# is off-limits for silver labelling, not just the sampled rows.
TEST_SPLIT_LABEL = "test"
PILOT_PER_CALL_TOKENS_OUT = 80  # v2 completion estimate, same as the calibration run
DAILY_REQUEST_CAP = 450  # gemini-3.5-flash-lite free-tier runner cap (rate_limits.yaml)
CITER_SOURCES = 285
CORPUS_SOURCES = 792
CORPUS_CONTEXTS = 6117


class CostError(Exception):
    """The scaffold cannot compute its numbers."""


def read_candidates(path: Path = CANDIDATES) -> list[dict[str, str]]:
    if not path.exists():
        raise CostError(f"candidate file not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["context_rows"]
    if not rows:
        raise CostError("candidate file has no context rows")
    return rows


def split_sources(
    contexts: list[dict[str, str]], wave_manifests: tuple[Path, ...] = WAVES
) -> dict[str, str]:
    """Source -> split, from the frozen assignment in ``dependency_sample``.

    The wave manifests only name the sources that happened to be sampled (97 of 258),
    so re-deriving the assignment from the whole candidate pool is the only way to
    know which sources are test sources. The manifests are then used as a
    cross-check, not as the source of truth.
    """
    by_source = Counter(row["source_pmcid"] for row in contexts)
    split = dict(_assign_splits(by_source, SAMPLE_SEED))
    for path in wave_manifests:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                declared = row.get("split")
                known = split.get(row["source_pmcid"])
                if declared and known and declared != known:
                    raise CostError(
                        f"manifest {path.name} says {row['source_pmcid']} is {declared}, "
                        f"but the frozen assignment says {known}"
                    )
    return split


def gold_row_ids() -> set[str]:
    """Every gold context id, from both waves' manifests."""
    ids: set[str] = set()
    for path in WAVES:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                ctx_id = row.get("ctx_id")
                if ctx_id:
                    ids.add(ctx_id)
    return ids


def silver_pool(
    contexts: list[dict[str, str]], split: dict[str, str], gold: set[str]
) -> tuple[list[dict[str, str]], dict[str, int]]:
    """Contexts eligible for teacher labelling now.

    Excluded, per the brief: every gold row (dev and test) and every context whose
    source is in the test split - not only the sampled ones, because a student must
    never see test-source material.
    """
    eligible: list[dict[str, str]] = []
    excluded = Counter()
    for row in contexts:
        ctx_id = row["ctx_id"]
        source = row["source_pmcid"]
        if ctx_id in gold:
            excluded["gold_row"] += 1
            continue
        if split.get(source) == TEST_SPLIT_LABEL:
            excluded["test_source_context"] += 1
            continue
        if not (row.get("text") or "").strip():
            excluded["empty_context_text"] += 1
            continue
        eligible.append(row)
    return eligible, dict(excluded)


def token_estimate(contexts: list[dict[str, str]]) -> dict[str, object]:
    """Prompt tokens from the real text with the project's chars/4 heuristic."""
    per_row = [math.ceil((len(row.get("text") or "") + 700) / 4.0) for row in contexts]
    total_in = sum(per_row)
    total_out = PILOT_PER_CALL_TOKENS_OUT * len(contexts)
    return {
        "rows": len(contexts),
        "prompt_tokens": total_in,
        "completion_tokens": total_out,
        "mean_prompt_tokens": round(total_in / len(contexts), 1) if contexts else 0.0,
        "max_prompt_tokens": max(per_row) if per_row else 0,
        "token_count_is": "heuristic ceil((context chars + 700 template chars) / 4)",
    }


def price(tokens: dict[str, object], pricing_path: Path) -> dict[str, object]:
    pricing = load_pricing(pricing_path)
    cost = estimate_cost_details(
        pricing,
        MODEL,
        int(tokens["prompt_tokens"]),
        int(tokens["completion_tokens"]),
        dry_run=True,
    )
    rows = int(tokens["rows"])
    per_call = (cost.usd / rows) if (cost.usd is not None and rows) else Decimal("0")
    return {
        "model": MODEL,
        "list_price_usd": str(cost.usd) if cost.usd is not None else None,
        "list_price_per_call_usd": str(per_call),
        "billing": "free_tier (list price recorded, no charge)",
    }


def ledger_run(ledger_path: Path, stage: str = "dependency_llm_v2") -> dict[str, object]:
    """Real ledger totals for the v2 dev run, straight from ``llm_calls``."""
    if not ledger_path.exists():
        raise CostError(f"ledger not found: {ledger_path}")
    with sqlite3.connect(ledger_path) as connection:
        row = connection.execute(
            """
            SELECT count(*),
                   sum(case when error is null then 1 else 0 end),
                   sum(case when error is not null then 1 else 0 end),
                   sum(cache_hit),
                   sum(prompt_tokens),
                   sum(completion_tokens),
                   sum(usd),
                   min(ts),
                   max(ts)
            FROM llm_calls WHERE stage = ?
            """,
            (stage,),
        ).fetchone()
    if row is None or not row[0]:
        raise CostError(f"no ledger rows for stage {stage!r}")
    attempts, ok, errors, cached, prompt_tokens, completion_tokens, usd, first, last = row
    return {
        "stage": stage,
        "attempts": int(attempts),
        "succeeded": int(ok or 0),
        "errors": int(errors or 0),
        "cache_hits": int(cached or 0),
        "prompt_tokens": int(prompt_tokens or 0),
        "completion_tokens": int(completion_tokens or 0),
        "list_price_usd": str(usd),
        "first_attempt": first,
        "last_attempt": last,
    }


def reconcile(ledger: dict[str, object], estimate_block: dict[str, object]) -> dict[str, object]:
    """Compare the pre-run estimate with the ledger totals and name the gap."""
    est_prompt = int(estimate_block["prompt_tokens_estimate"])
    est_completion = int(estimate_block["completion_tokens_estimate"])
    act_prompt = int(ledger["prompt_tokens"])
    act_completion = int(ledger["completion_tokens"])
    est_usd = Decimal(str(estimate_block["list_price_usd"] or "0"))
    act_usd = Decimal(str(ledger["list_price_usd"] or "0"))
    return {
        "prompt_tokens_estimate": est_prompt,
        "prompt_tokens_actual": act_prompt,
        "prompt_token_delta_pct": round((act_prompt - est_prompt) / est_prompt, 4)
        if est_prompt
        else None,
        "completion_tokens_estimate": est_completion,
        "completion_tokens_actual": act_completion,
        "completion_token_delta_pct": round((act_completion - est_completion) / est_completion, 4)
        if est_completion
        else None,
        "list_price_estimate_usd": str(est_usd),
        "list_price_actual_usd": str(act_usd),
        "list_price_delta_usd": str(act_usd - est_usd),
        "note": (
            "the completion estimate assumed 80 tokens per reply; the JSON answers are about "
            "half that, so the estimate overshoots on output and is close on input"
        ),
    }


def cost_section(
    detector_summary: Path,
    pricing_path: Path,
    *,
    ledger_path: Path | None = None,
    dev_rows: int = 151,
) -> dict[str, object]:
    if not detector_summary.exists():
        raise CostError(f"detector summary not found: {detector_summary}; run p3_05_staged.py")
    summary = json.loads(detector_summary.read_text(encoding="utf-8"))
    dev = summary["dev"]
    escalation = float(dev["candidate_rate"])
    sample = token_estimate([{"text": "B uses A's reported effect size in its model [1]."}])
    unit = price(sample, pricing_path)
    per_call_estimate = Decimal(str(unit["list_price_per_call_usd"]))

    ledger_block: dict[str, object] | None = None
    reconciliation: dict[str, object] | None = None
    if ledger_path is not None and ledger_path.exists():
        ledger_block = ledger_run(ledger_path)
        # The estimate must be the one that was stated before the run: the same prompt
        # over the same real dev rows, not a scaled one-row sample.
        dev_rows_actual = spec_rows(scored_rows(load_rows()), "dev")
        estimate_block = estimate(dev_rows_actual, pricing_path)
        reconciliation = reconcile(ledger_block, estimate_block)

    succeeded = int(ledger_block["succeeded"]) if ledger_block else dev_rows
    per_call = (
        Decimal(str(ledger_block["list_price_usd"])) / Decimal(succeeded)
        if ledger_block and succeeded
        else per_call_estimate
    )
    cost_per_context = per_call * Decimal(str(escalation))
    contexts_per_retraction = Decimal(CORPUS_CONTEXTS) / Decimal(CITER_SOURCES)
    return {
        "escalation_rate_e": escalation,
        "ledger": ledger_block,
        "reconciliation": reconciliation,
        "stage1_share": round(1 - escalation, 4),
        "student_share_s": None,
        "student_share_note": (
            "no student exists in P3-05 (P2-03b not built), so s is not applicable; "
            "reporting a number here would invent a stage that was never run"
        ),
        "list_price_per_llm_call_usd": str(per_call.quantize(Decimal("0.00000001"))),
        "list_price_per_context_usd": str(cost_per_context.quantize(Decimal("0.00000001"))),
        "contexts_per_retraction": float(round(contexts_per_retraction, 2)),
        "list_price_per_retraction_usd": str(
            (cost_per_context * contexts_per_retraction).quantize(Decimal("0.00000001"))
        ),
        "projection": {
            "label": "PROJECTED",
            "assumptions": {
                "citer_sources": CITER_SOURCES,
                "corpus_sources": CORPUS_SOURCES,
                "corpus_contexts": CORPUS_CONTEXTS,
                "citer_coverage": f"{CITER_SOURCES} of {CORPUS_SOURCES} sources",
                "escalation_rate_source": "dev candidate rate from the staged detector",
                "prices": "pricing.yaml list prices, model " + MODEL,
                "real_spend": "zero on the free tier; list price is the comparable number",
            },
            "corpus_list_price_usd": str(cost_per_context * CORPUS_CONTEXTS),
            "corpus_requests": round(escalation * CORPUS_CONTEXTS, 1),
            "free_tier_days_at_450_per_day": round(
                escalation * CORPUS_CONTEXTS / DAILY_REQUEST_CAP, 1
            ),
        },
    }


def write_cost_report(block: dict[str, object]) -> None:
    projection = block["projection"]
    assert isinstance(projection, dict)
    assumptions = projection["assumptions"]
    assert isinstance(assumptions, dict)
    lines = [
        "# P3-08 cost accounting scaffold",
        "",
        "Generated by `python scripts/p3_08_cost.py --section cost`; every number is its output.",
        "",
        "## Measured inputs",
        "",
        "| Quantity | Value |",
        "| :-- | --: |",
        f"| Escalation rate `e` (dev) | **{float(block['escalation_rate_e']):.1%}** |",
        f"| Stage-1 share (`1 - e`) | {float(block['stage1_share']):.1%} |",
        f"| Student share `s` | **n/a** - {block['student_share_note']} |",
        f"| List price per LLM call | ${block['list_price_per_llm_call_usd']} |",
        f"| List price per context | ${block['list_price_per_context_usd']} |",
        f"| Contexts per retraction | {block['contexts_per_retraction']} |",
        f"| List price per retraction analysed | **${block['list_price_per_retraction_usd']}** |",
        "",
        "## Ledger reconciliation (real `llm_calls` rows)",
        "",
    ]
    ledger = block.get("ledger")
    reconciliation = block.get("reconciliation")
    if isinstance(ledger, dict) and isinstance(reconciliation, dict):
        lines += [
            f"- Run stage `{ledger['stage']}`: **{ledger['attempts']} attempts**, "
            f"{ledger['succeeded']} succeeded, {ledger['errors']} errored, "
            f"{ledger['cache_hits']} cache hits ({ledger['first_attempt']} to "
            f"{ledger['last_attempt']}).",
            f"- Ledger tokens: **{ledger['prompt_tokens']:,} prompt**, "
            f"{ledger['completion_tokens']:,} completion.",
            f"- Ledger list price: **${ledger['list_price_usd']}** "
            "(real spend $0 on the free tier).",
            "",
            "| Quantity | Pre-run estimate | Ledger actual | Delta |",
            "| :-- | --: | --: | --: |",
            f"| Prompt tokens | {reconciliation['prompt_tokens_estimate']:,} | "
            f"{reconciliation['prompt_tokens_actual']:,} | "
            f"{float(reconciliation['prompt_token_delta_pct']):+.1%} |",
            f"| Completion tokens | {reconciliation['completion_tokens_estimate']:,} | "
            f"{reconciliation['completion_tokens_actual']:,} | "
            f"{float(reconciliation['completion_token_delta_pct']):+.1%} |",
            f"| List price | ${reconciliation['list_price_estimate_usd']} | "
            f"${reconciliation['list_price_actual_usd']} | "
            f"${reconciliation['list_price_delta_usd']} |",
            "",
            f"**Mismatch, stated plainly:** {reconciliation['note']}.",
            "",
            "The per-context and per-retraction figures below use the **ledger** price per",
            "successful call, not the estimate.",
            "",
        ]
    else:
        lines += ["No ledger rows were found for the v2 run; figures below use the estimate.", ""]
    lines += [
        "## PROJECTED corpus totals",
        "",
        "Not measured. This is arithmetic on the assumptions below, which is why it is labelled.",
        "",
        "| Assumption | Value |",
        "| :-- | :-- |",
        *[f"| {key} | {value} |" for key, value in assumptions.items()],
        "",
        f"- Corpus list price at `e` = {float(block['escalation_rate_e']):.1%}: "
        f"**${projection['corpus_list_price_usd']}**.",
        f"- LLM requests: **{projection['corpus_requests']}**; at the free-tier runner cap of "
        f"{DAILY_REQUEST_CAP}/day that is **{projection['free_tier_days_at_450_per_day']} days**.",
        "",
        "## What is not accounted for here",
        "",
        "- No student exists, so there is no distillation cost line and no `s`.",
        "- Retrieval/linking (P3-06) and propagation (P3-07) are not in scope.",
        "- The escalation rate is a dev estimate on 151 rows; it will move on test.",
        "",
    ]
    COST_REPORT.parent.mkdir(parents=True, exist_ok=True)
    COST_REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def write_silver_report(block: dict[str, object]) -> None:
    tokens = block["tokens"]
    assert isinstance(tokens, dict)
    priced = block["price"]
    assert isinstance(priced, dict)
    excluded = block["excluded"]
    assert isinstance(excluded, dict)
    lines = [
        "# P3-05 SILVER PLAN - sizing only, nothing run",
        "",
        "Generated by `python scripts/p3_08_cost.py --section silver`. **No teacher call was",
        "made, no label was created, and no student was trained.** These are planning numbers.",
        "",
        "## Eligible pool",
        "",
        f"- Candidate contexts in the corpus: **{CORPUS_CONTEXTS}**.",
        f"- Excluded gold rows (dev and test): **{excluded.get('gold_row', 0)}**.",
        f"- Excluded contexts whose source is in the frozen **test** split: "
        f"**{excluded.get('test_source_context', 0)}** (the whole source, not just sampled rows).",
        f"- Excluded empty context text: {excluded.get('empty_context_text', 0)}.",
        f"- **Eligible for teacher labelling: {tokens['rows']} contexts.**",
        "",
        "## Cost at list price",
        "",
        "| Quantity | Value |",
        "| :-- | --: |",
        f"| Prompt tokens (heuristic) | {tokens['prompt_tokens']:,} |",
        f"| Completion tokens (80/call assumption) | {tokens['completion_tokens']:,} |",
        f"| Mean prompt tokens per call | {tokens['mean_prompt_tokens']} |",
        f"| List price, whole pool | **${priced['list_price_usd']}** |",
        f"| List price per call | ${priced['list_price_per_call_usd']} |",
        f"| Model | `{priced['model']}` ({priced['billing']}) |",
        "| Token count basis | " + str(tokens["token_count_is"]) + " |",
        "",
        f"- Requests needed: **{tokens['rows']}**; at {DAILY_REQUEST_CAP}/day on the free tier "
        f"that is **{round(tokens['rows'] / DAILY_REQUEST_CAP, 1)} days**.",
        "- Real spend on the free tier is $0; the list price is what makes it comparable to a",
        "  paid run later.",
        "",
        "## What this plan deliberately does not do",
        "",
        "- It does not include the gold dev rows. They are the only honest dev evaluation set;",
        "  training a student on them and then scoring it there would be circular.",
        "- It does not include **any** context from a test-split source, sampled or not, so a",
        "  distilled student cannot inherit test material through silver labels.",
        "- It does not propose a student architecture, label budget or stopping rule for the",
        "  teacher; those need the owner's go-ahead first.",
        "",
    ]
    SILVER_REPORT.parent.mkdir(parents=True, exist_ok=True)
    SILVER_REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--section", choices=("cost", "silver"), default="cost")
    parser.add_argument("--pricing", type=Path, default=None)
    args = parser.parse_args(argv)
    pricing_path = args.pricing or (ROOT / "src" / "axion" / "config" / "pricing.yaml")

    if args.section == "cost":
        block = cost_section(
            DETECTOR_SUMMARY, pricing_path, ledger_path=Settings().resolved_ledger_path
        )
        COST_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
        COST_SUMMARY.write_text(
            json.dumps(block, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        write_cost_report(block)
        print(json.dumps(block, indent=2))
        return 0

    contexts = read_candidates()
    split = split_sources(contexts)
    eligible, excluded = silver_pool(contexts, split, gold_row_ids())
    tokens = token_estimate(eligible)
    priced = price(tokens, pricing_path)
    block = {"tokens": tokens, "price": priced, "excluded": excluded}
    SILVER_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SILVER_SUMMARY.write_text(json.dumps(block, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_silver_report(block)
    print(json.dumps(block, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
