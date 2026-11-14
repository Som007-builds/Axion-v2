"""Regenerate docs/reports/P1-baseline.md from real artifacts.

Every value is read from a file or printed as NOT YET MEASURED. This script
never fabricates a number and never calls an LLM.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from axion.config.settings import Settings
from axion.eval.audit import AuditError, compute_metrics, read_audit
from axion.ingest.corpus import read_manifest
from axion.llm.ledger import SQLiteLedger

DEFAULT_MANIFEST = Path("docs/reports/P1-corpus-manifest.json")
DEFAULT_AUDIT = Path("eval/audit/claims_audit_v1.csv")
DEFAULT_OUT = Path("docs/reports/P1-baseline.md")
NOT_MEASURED = "NOT YET MEASURED"


def _corpus_section(manifest_path: Path) -> list[str]:
    if not manifest_path.exists():
        return [
            "## Corpus",
            "",
            f"- Corpus manifest: **{NOT_MEASURED}** (`{manifest_path}` not found)",
            "",
        ]
    manifest = read_manifest(manifest_path)
    counts = manifest.counts
    resources = manifest.resources
    coverage_path = manifest_path.parent / "P1-corpus-coverage.json"
    coverage: dict[str, object] | None = None
    if coverage_path.exists():
        coverage = json.loads(coverage_path.read_text(encoding="utf-8"))
    coverage_line = (
        f"- All-paper parse coverage: {coverage['parsed']:,}/"
        f"{coverage['papers']:,} parsed, {coverage['parse_failures']:,} failures; "
        f"{coverage['papers_with_contexts']:,} papers with ≥1 context "
        "(`docs/reports/P1-corpus-coverage.md`)"
        if coverage is not None
        else "- All-paper parse coverage: see `scripts/corpus_coverage.py`"
    )
    return [
        "## Corpus (ID-only manifest)",
        "",
        f"- Corpus: `{manifest.corpus_id}`; cap {manifest.cap:,}",
        f"- Papers: {counts.papers_total:,} ({counts.sources_total:,} sources, "
        f"{counts.citers_included:,} citers)",
        f"- Citation contexts: {counts.contexts_total:,}; edges with contexts: "
        f"{counts.edges_with_contexts:,}",
        f"- Papers parsed during the context stage: {counts.papers_parsed:,}; "
        f"parse failures: {counts.parse_failures:,}",
        coverage_line,
        f"- Papers without PMID: {counts.papers_without_pmid:,} "
        f"({counts.papers_without_pmid_sources:,} sources)",
        f"- Manifest wall time: {resources.wall_time_s:,.1f}s; peak RSS: "
        f"{resources.peak_rss_mb:,.1f} MiB; disk: {resources.disk_mb:,.1f} MiB",
        f"- Contexts per paper: {counts.contexts_total / max(counts.papers_total, 1):.2f}",
        "",
    ]


def _ledger_section(ledger_path: Path | None) -> list[str]:
    if ledger_path is None or not ledger_path.exists():
        return [
            "## Cost ledger",
            "",
            f"- Ledger: **{NOT_MEASURED}** (no ledger file found)",
            "",
        ]
    try:
        report = SQLiteLedger(ledger_path).report()
    except sqlite3.Error as exc:
        return ["## Cost ledger", "", f"- Ledger unreadable: `{exc}`", ""]
    if report.total_calls == 0:
        return [
            "## Cost ledger",
            "",
            "- No LLM calls recorded. Cost, tokens, and latency are " f"**{NOT_MEASURED}**.",
            "",
        ]
    return [
        "## Cost ledger (measured)",
        "",
        f"- Calls: {report.total_calls:,}; cache hits: {report.total_cache_hits:,}; "
        f"errors: {report.total_errors:,}",
        f"- Prompt tokens: {report.total_prompt_tokens:,}; completion tokens: "
        f"{report.total_completion_tokens:,}",
        f"- Total USD: {report.total_usd}",
        "",
        "| Group | Calls | Tokens | USD |",
        "| :-- | --: | --: | --: |",
        *[
            f"| {row.key} | {row.calls:,} | "
            f"{row.prompt_tokens + row.completion_tokens:,} | {row.usd} |"
            for row in report.rows
        ],
        "",
    ]


def _audit_section(audit_path: Path) -> list[str]:
    if not audit_path.exists():
        return [
            "## Claim audit",
            "",
            f"- Audit file `{audit_path}`: **{NOT_MEASURED}**.",
            "- Precision and Wilson CI cannot be reported until the owner labels "
            "≥200 claims and relabels 10% after ≥7 days.",
            "",
        ]
    try:
        metrics = compute_metrics(read_audit(audit_path))
    except AuditError as exc:
        return ["## Claim audit", "", f"- Audit not usable yet: {exc}", ""]
    overall = metrics["overall"]
    assert isinstance(overall, dict)
    return [
        "## Claim audit (measured)",
        "",
        f"- Labelled: {overall['n']}; correct: {overall['correct']}; "
        f"precision: {overall['precision'] * 100:.1f}% "
        f"(Wilson 95% {overall['ci_low'] * 100:.1f}-{overall['ci_high'] * 100:.1f}%)",
        f"- Unlabelled rows: {metrics['unlabelled']}",
        "",
    ]


def build_report(
    *,
    manifest_path: Path,
    audit_path: Path,
    ledger_path: Path | None,
    out_path: Path,
) -> str:
    corpus = read_manifest(manifest_path).counts if manifest_path.exists() else None
    lines = [
        "# P1 baseline report",
        "",
        "> Generated by `python scripts/build_p1_report.py` (`make report`).",
        "> Values are read from the corpus manifest, cost ledger, and audit file.",
        f"> Anything not produced yet is marked **{NOT_MEASURED}**.",
        "",
        "## Headline metrics",
        "",
        "| Metric | Value | Source |",
        "| :-- | :-- | :-- |",
        f"| Claim extraction precision (±95% CI) | {NOT_MEASURED} | audit |",
        f"| Cost per paper | {NOT_MEASURED} | ledger + manifest |",
        f"| Tokens per paper | {NOT_MEASURED} | ledger + manifest |",
        f"| p95 latency | {NOT_MEASURED} | ledger |",
        f"| Corpus claim coverage | "
        f"{'see corpus section' if corpus else NOT_MEASURED} | manifest |",
        "",
        *_corpus_section(manifest_path),
        *_ledger_section(ledger_path),
        *_audit_section(audit_path),
        "## Regeneration",
        "",
        "```",
        "python scripts/build_p1_report.py",
        "```",
        "",
    ]
    text = "\n".join(lines)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8", newline="\n")
    return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    parser.add_argument("--ledger", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    ledger_path = args.ledger
    if ledger_path is None:
        try:
            ledger_path = Settings().resolved_ledger_path
        except ValueError:
            ledger_path = None
    build_report(
        manifest_path=args.manifest,
        audit_path=args.audit,
        ledger_path=ledger_path,
        out_path=args.out,
    )
    print(f"report: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
