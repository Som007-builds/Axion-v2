"""Dry-run size and token estimate for the P1-10 seeded baseline sample.

This script makes no LLM calls and contains no extractor. It parses the real
JATS text of a seeded, paper-level sample from the committed corpus manifest,
reports text sizes, and projects token counts for candidate sample sizes. Token
counts are a heuristic (characters / 4); every number is an ESTIMATE.

Usage:
    python scripts/p1_10_estimate.py --manifest docs/reports/P1-corpus-manifest.json
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from axion.config.settings import Settings
from axion.eval.cost_estimate import (
    CHARS_PER_TOKEN,
    DEFAULT_SEED,
    TextSummary,
    estimate_tokens,
    paper_text_stats,
    papers_for_claims,
    sample_papers,
    summarize,
)
from axion.ingest.corpus import CorpusManifest, read_manifest, read_papers_csv
from axion.parse.jats import JatsParseError, parse_jats_file

DEFAULT_MANIFEST = Path("docs/reports/P1-corpus-manifest.json")
DEFAULT_OUT = Path("docs/reports/P1-baseline-estimate")
PROMPT_OVERHEAD_TOKENS = 600
OUTPUT_TOKENS_PER_CLAIM = 120
CLAIMS_PER_PAPER = (5.0, 10.0, 20.0)
SAMPLE_SIZES = (100, 150, 200)


def _summary_rows(summary: TextSummary) -> list[str]:
    return [
        "| Measure | Mean | Median | p95 |",
        "| :-- | --: | --: | --: |",
        f"| Text tokens (estimate) | {summary.tokens_mean:,.0f} | "
        f"{summary.tokens_median:,.0f} | {summary.tokens_p95:,.0f} |",
        f"| Words | {summary.words_mean:,.0f} | — | {summary.words_p95:,.0f} |",
        f"| Characters | {summary.chars_mean:,.0f} | {summary.chars_median:,.0f} | "
        f"{summary.chars_p95:,.0f} |",
        f"| Sections | {summary.sections_mean:,.1f} | — | — |",
        f"| Paragraphs | {summary.paragraphs_mean:,.1f} | — | — |",
        f"| Sentences | {summary.sentences_mean:,.1f} | — | — |",
        f"| Citation contexts | {summary.contexts_mean:,.1f} | — | — |",
    ]


def _sizing_rows(summary: TextSummary) -> list[str]:
    rows = [
        "| Sample papers | Assumed claims/paper | Expected claims | Input tokens | "
        "Output tokens | Total tokens |",
        "| --: | --: | --: | --: | --: | --: |",
    ]
    for papers in SAMPLE_SIZES:
        for claims_per_paper in CLAIMS_PER_PAPER:
            estimate = estimate_tokens(
                summary,
                papers=papers,
                claims_per_paper=claims_per_paper,
                prompt_overhead_tokens=PROMPT_OVERHEAD_TOKENS,
                output_tokens_per_claim=OUTPUT_TOKENS_PER_CLAIM,
            )
            rows.append(
                f"| {papers:,} | {claims_per_paper:.0f} | {estimate.expected_claims:,.0f} | "
                f"{estimate.input_tokens:,.0f} | {estimate.output_tokens:,.0f} | "
                f"{estimate.total_tokens:,.0f} |"
            )
    return rows


def _report(
    manifest: CorpusManifest,
    summary: TextSummary,
    *,
    sample_size: int,
    seed: int,
    parsed: int,
    parse_failures: int,
) -> str:
    claims_rows = [
        "| Assumed claims/paper | Papers for 200 claims (1.5x margin) | "
        "Papers for 300 claims (1.5x margin) |",
        "| --: | --: | --: |",
    ]
    for claims_per_paper in CLAIMS_PER_PAPER:
        claims_rows.append(
            f"| {claims_per_paper:.0f} | {papers_for_claims(200, claims_per_paper):,} | "
            f"{papers_for_claims(300, claims_per_paper):,} |"
        )
    lines = [
        "# P1 baseline extraction — dry-run size and token estimate",
        "",
        "**This is an ESTIMATE, not a measurement.** No extractor code was run, no provider",
        "SDK was installed, and no LLM call was made. Token counts use the heuristic",
        f"`ceil(characters / {CHARS_PER_TOKEN:g})`, not a model tokenizer, so expect an error of",
        "roughly ±15% depending on the model's tokenizer.",
        "",
        "## Sample",
        "",
        f"- Corpus: `{manifest.corpus_id}` ({manifest.counts.papers_total:,} papers)",
        f"- Manifest bundle: `{manifest.files.papers_csv}`",
        f"- Sample: **{sample_size} papers**, uniform without replacement, "
        f"seed `{seed}` (paper-level)",
        f"- Parsed successfully: {parsed:,}; parse failures: {parse_failures:,}",
        "",
        "The sample is drawn from the ID-only paper list, then each paper's cached JATS is",
        "parsed locally. All parsed sections are counted (abstract plus body), which is an",
        "upper bound if the eventual extractor targets fewer sections.",
        "",
        "## Text size per paper",
        "",
        *_summary_rows(summary),
        "",
        "## Token projection for candidate sample sizes",
        "",
        f"Assumptions: {PROMPT_OVERHEAD_TOKENS} prompt/instruction tokens per paper and",
        f"{OUTPUT_TOKENS_PER_CLAIM} output tokens per extracted claim. Input tokens are the",
        "sample's mean text tokens plus the prompt overhead.",
        "",
        *_sizing_rows(summary),
        "",
        "## Papers needed for the audit minimum",
        "",
        "CONTEXT §6 requires ≥200 audited claims. The claims-per-paper rate is not measured",
        "until the extractor runs, so the table shows the rate as a scenario.",
        "",
        *claims_rows,
        "",
        "## Suggested sample (owner decision pending)",
        "",
        "Because the claims-per-paper rate is unknown, a **100-paper** sample is the smallest",
        "size that clears 200 claims comfortably at 5 claims/paper (expected 500 claims), and",
        "it is the suggestion in the P1-10 plan. The owner should confirm 100 papers (or choose",
        "150/200 for more margin) before any paid run. The seed is recorded above and must be",
        "reused when the actual sample is drawn.",
        "",
        "## Cost",
        "",
        "No dollar estimate is given: `src/axion/config/pricing.yaml` is intentionally blank.",
        "Use the token totals above and the formula",
        "`usd = input_tokens * input_price_per_Mtok / 1e6 "
        "+ output_tokens * output_price_per_Mtok / 1e6`",
        "once verified prices are supplied. The ledger, not this estimate, is the cost source",
        "of record.",
        "",
        "## What the owner must provide before P1-10",
        "",
        "1. Confirm the provider/hosting for the chosen large tier.",
        "2. Enter verified prices for both tiers in `src/axion/config/pricing.yaml` "
        "(no memory prices).",
        "3. Approve a paid budget cap in `_private/budget.md` for the P1 baseline run.",
        "4. Approve installing a provider SDK (currently deferred; no SDK is installed).",
        "5. Confirm the sample size (suggested 100 papers) and that all parsed sections are the",
        "   baseline target, or name the target sections explicitly.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--sample", type=int, default=50)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    if args.sample < 1:
        parser.error("--sample must be at least 1")

    manifest = read_manifest(args.manifest)
    papers = read_papers_csv(args.manifest.parent / Path(manifest.files.papers_csv).name)
    settings = Settings()
    cache_dir = args.cache_dir or settings.resolved_europepmc_cache_dir
    chosen = sample_papers(papers, args.sample, seed=args.seed)

    stats = []
    parse_failures = 0
    missing = 0
    for paper in chosen:
        path = cache_dir / "fulltext" / f"{paper.pmcid}.xml"
        if not path.exists():
            missing += 1
            continue
        try:
            parsed_paper = parse_jats_file(path, paper_id=paper.pmcid)
        except JatsParseError:
            parse_failures += 1
            continue
        stats.append(paper_text_stats(parsed_paper))
    if not stats:
        print("no sampled papers parsed; run the corpus ingest first", flush=True)
        return 1
    if missing:
        print(f"{missing} sampled papers have no cached full text", flush=True)

    summary = summarize(stats)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    report_path = Path(f"{args.out}.md")
    json_path = Path(f"{args.out}.json")
    report_path.write_text(
        _report(
            manifest,
            summary,
            sample_size=len(chosen),
            seed=args.seed,
            parsed=len(stats),
            parse_failures=parse_failures,
        ),
        encoding="utf-8",
        newline="\n",
    )
    payload: dict[str, Any] = {
        "kind": "estimate",
        "corpus_id": manifest.corpus_id,
        "corpus_papers": manifest.counts.papers_total,
        "sample_requested": args.sample,
        "sample_parsed": len(stats),
        "seed": args.seed,
        "token_method": f"ceil(chars/{CHARS_PER_TOKEN:g})",
        "prompt_overhead_tokens": PROMPT_OVERHEAD_TOKENS,
        "output_tokens_per_claim": OUTPUT_TOKENS_PER_CLAIM,
        "summary": {
            "tokens_mean": summary.tokens_mean,
            "tokens_median": summary.tokens_median,
            "tokens_p95": summary.tokens_p95,
            "words_mean": summary.words_mean,
            "words_p95": summary.words_p95,
            "chars_mean": summary.chars_mean,
            "sentences_mean": summary.sentences_mean,
            "contexts_mean": summary.contexts_mean,
        },
        "sizing": [
            {
                "papers": papers_count,
                "claims_per_paper": claims_per_paper,
                **estimate_tokens(
                    summary,
                    papers=papers_count,
                    claims_per_paper=claims_per_paper,
                    prompt_overhead_tokens=PROMPT_OVERHEAD_TOKENS,
                    output_tokens_per_claim=OUTPUT_TOKENS_PER_CLAIM,
                ).__dict__,
            }
            for papers_count in SAMPLE_SIZES
            for claims_per_paper in CLAIMS_PER_PAPER
        ],
        "per_paper": [
            {
                "pmcid": item.pmcid,
                "sections": item.sections,
                "paragraphs": item.paragraphs,
                "chars": item.chars,
                "words": item.words,
                "sentences": item.sentences,
                "contexts": item.contexts,
                "tokens_estimate": item.tokens,
            }
            for item in sorted(stats, key=lambda item: item.pmcid)
        ],
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"sample={len(stats)} mean_tokens={math.ceil(summary.tokens_mean):,}", flush=True)
    print(f"report: {report_path}", flush=True)
    print(f"json: {json_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
