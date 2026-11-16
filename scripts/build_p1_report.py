"""Regenerate docs/reports/P1-baseline.md from real artifacts.

Every value is read from a file or printed as NOT YET MEASURED. This script
never fabricates a number and never calls an LLM.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

from axion.eval.audit import AuditError, compute_metrics, read_audit
from axion.ingest.corpus import read_manifest

DEFAULT_MANIFEST = Path("docs/reports/P1-corpus-manifest.json")
DEFAULT_AUDIT = Path("eval/audit/claims_audit_v1.csv")
DEFAULT_OVERLAP = Path("eval/audit/claims_audit_v1_overlap_labelled.csv")
DEFAULT_RUN_REPORT = Path("eval/silver/claims_v1/baseline_flashlite/run_report.json")
DEFAULT_OUT = Path("docs/reports/P1-baseline.md")
NOT_MEASURED = "NOT YET MEASURED"
GATE_PRECISION_FLOOR = 0.90


def _money(value: object) -> str:
    return f"${Decimal(str(value)):.6f}"


def _pct(value: object) -> str:
    return f"{Decimal(str(value)) * 100:.1f}%"


def _load_run_report(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _load_audit_metrics(
    audit_path: Path, overlap_path: Path | None
) -> tuple[list[dict[str, str]], dict[str, object]]:
    """Read primary labels and, when supplied, fold in second-labeler overlap."""
    rows = read_audit(audit_path)
    if overlap_path is not None and overlap_path.exists():
        overlap_rows = read_audit(overlap_path)
        by_id = {row.get("claim_id", ""): row for row in overlap_rows}
        primary_ids = {row.get("claim_id", "") for row in rows}
        extra = sorted(set(by_id) - primary_ids)
        if extra:
            raise AuditError(
                "overlap CSV contains claim ids not in the primary audit: " + ", ".join(extra[:5])
            )
        for row in rows:
            other = by_id.get(row.get("claim_id", ""))
            if other is None:
                continue
            label = (other.get("label") or "").strip()
            if label:
                if (row.get("relabel_label") or "").strip():
                    raise AuditError(f"{row.get('claim_id', '?')}: relabel_label already filled")
                row["relabel_label"] = label
    return rows, compute_metrics(rows)


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
    link_lines: list[str] = []
    if coverage is not None and "source_papers_with_incoming_edge" in coverage:
        link_lines = [
            f"- Retracted sources with ≥1 incoming citer edge: "
            f"{coverage['source_papers_with_incoming_edge']:,} of "
            f"{counts.sources_total:,} "
            f"({coverage['source_papers_without_incoming_edge']:,} have none)",
            f"- Citer papers without an outgoing edge: "
            f"{coverage['citer_papers_without_outgoing_edge']:,} of "
            f"{counts.citers_included:,}; papers with no edge at all: "
            f"{coverage['papers_without_any_edge']:,}",
        ]
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
        *link_lines,
        f"- Papers without PMID: {counts.papers_without_pmid:,} "
        f"({counts.papers_without_pmid_sources:,} sources)",
        f"- Manifest wall time: {resources.wall_time_s:,.1f}s; peak RSS: "
        f"{resources.peak_rss_mb:,.1f} MiB; disk: {resources.disk_mb:,.1f} MiB",
        f"- Contexts per paper: {counts.contexts_total / max(counts.papers_total, 1):.2f}",
        "",
    ]


def _run_sections(run: dict[str, object] | None) -> list[str]:
    if run is None:
        return [
            "## Baseline run",
            "",
            f"- Extraction run report: **{NOT_MEASURED}** (no run report found)",
            f"- Cost per paper: **{NOT_MEASURED}**",
            f"- Tokens per paper: **{NOT_MEASURED}**",
            f"- p95 latency: **{NOT_MEASURED}**",
            "",
        ]
    config = run.get("config") or {}
    assert isinstance(config, dict)
    latency = run.get("latency_ms") or {}
    assert isinstance(latency, dict)
    papers = int(run.get("papers_processed") or 0)
    claims = int(run.get("accepted_claims") or 0)
    total_tokens = int(run.get("total_tokens") or 0)
    cost = Decimal(str(run.get("list_price_usd") or 0))
    other_rejections = (
        int(run.get("failures") or 0)
        - int(run.get("evidence_span_failures") or 0)
        - int(run.get("parse_failures") or 0)
    )
    requests_by_day = run.get("requests_by_day") or {}
    assert isinstance(requests_by_day, dict)
    return [
        "## Baseline run and provenance",
        "",
        f"- Run id: `{run.get('run_id')}`",
        f"- Provider / model: `{config.get('provider')}` / `{config.get('model')}`",
        f"- Prompt: `{config.get('prompt_version')}`; thinking "
        f"`{config.get('thinking_level')}`; temperature {config.get('temperature')}; "
        f"max output {config.get('max_output_tokens')}",
        f"- Billing: `{config.get('billing')}`; real spend "
        f"{_money(run.get('real_spend_usd') or 0)}; retry attempts "
        f"{config.get('retry_max_attempts')}",
        f"- Papers processed: **{papers:,}**; accepted silver claims: **{claims:,}**; "
        f"claims per paper: {claims / max(papers, 1):.2f}",
        "- Requests by day: "
        + ", ".join(f"{day}: {count}" for day, count in sorted(requests_by_day.items())),
        f"- Daily cap: {run.get('daily_cap')} (rate limits checked "
        f"{(run.get('rate_limits') or {}).get('checked')})",
        "",
        "## Extraction quality",
        "",
        f"- Evidence-span verbatim rate: **{_pct(run.get('evidence_span_verbatim_rate') or 0)}** "
        f"({run.get('evidence_span_failures')} spans rejected)",
        f"- Strict pre-normalization rate: "
        f"**{_pct(run.get('strict_evidence_span_verbatim_rate') or 0)}** "
        f"({run.get('normalization_fixes')} fixed by normalization)",
        f"- Parse / structured-output failures: **{run.get('parse_failures')}**; "
        f"other rejected claims: {other_rejections}",
        f"- Total failures recorded: **{run.get('failures')}**; failed calls: "
        f"**{run.get('failed_calls')}** of {run.get('calls')}",
        f"- Prompt-token estimate vs real: **{_pct(run.get('prompt_token_gap_fraction') or 0)}** "
        f"({int(run.get('estimate_prompt_tokens') or 0):,} estimated)",
        "",
        "## Tokens and cost (list price; real spend is recorded separately)",
        "",
        f"- Prompt tokens: {int(run.get('prompt_tokens') or 0):,}; completion tokens: "
        f"{int(run.get('completion_tokens') or 0):,}; thinking tokens: "
        f"{int(run.get('reasoning_tokens') or 0):,}",
        f"- Tokens per paper: **{total_tokens / max(papers, 1):,.1f}** "
        f"(total {total_tokens:,})",
        f"- Cost per paper: **{_money(cost / max(papers, 1))}**; cost per accepted "
        f"claim: **{_money(run.get('cost_per_accepted_claim_usd') or 0)}**",
        f"- Total list price: **{_money(cost)}**; post-promotion: "
        f"{_money(run.get('post_promotion_usd') or cost)}",
        f"- Output (incl. thinking) share of cost: "
        f"**{_pct(run.get('output_cost_share') or 0)}**",
        "",
        "## Latency",
        "",
        f"- Mean: {int(float(latency.get('mean') or 0)):,} ms; p95: "
        f"**{int(float(latency.get('p95') or 0)):,} ms**",
        "",
    ]


def _audit_section(audit_path: Path, overlap_path: Path | None = None) -> list[str]:
    if not audit_path.exists():
        return [
            "## Claim audit",
            "",
            f"- Audit file `{audit_path}`: **{NOT_MEASURED}**.",
            "- Precision and Wilson CI cannot be reported until the owner labels "
            "≥200 claims and completes the agreement step.",
            "",
        ]
    try:
        rows, metrics = _load_audit_metrics(audit_path, overlap_path)
    except AuditError as exc:
        return ["## Claim audit", "", f"- Audit not usable yet: {exc}", ""]
    agreement_present = isinstance(metrics.get("agreement"), dict)
    use_overlap = overlap_path is not None and overlap_path.exists()
    agreement_kind = "independent" if use_overlap and agreement_present else "self"
    overall = metrics["overall"]
    assert isinstance(overall, dict)
    breakdown = metrics["breakdown"]
    assert isinstance(breakdown, dict)
    splits = Counter((row.get("split") or "(none)").strip() for row in rows)
    labelers = Counter((row.get("labeler") or "(none)").strip() for row in rows)
    papers = len({(row.get("paper_id") or "").strip() for row in rows})
    relabelled = sum(1 for row in rows if (row.get("relabel_label") or "").strip())
    lines = [
        "## Claim audit (measured)",
        "",
        f"- Labelled claims: **{overall['n']}** from {papers} papers; correct: "
        f"**{overall['correct']}**",
        f"- **Precision: {_pct(overall['precision'])}** "
        f"(Wilson 95% CI {_pct(overall['ci_low'])} to {_pct(overall['ci_high'])})",
        f"- Unlabelled rows: {metrics['unlabelled']}; labeler(s): "
        f"{', '.join(sorted(labelers))}; splits: "
        f"{', '.join(f'{name} {count}' for name, count in sorted(splits.items()))}",
        "- Failure breakdown: "
        + ", ".join(f"`{label}` {count}" for label, count in breakdown.items()),
    ]
    cluster = metrics.get("cluster_bootstrap")
    if isinstance(cluster, dict):
        lines.append(
            f"- Paper-level cluster bootstrap: {_pct(cluster['ci_low'])} to "
            f"{_pct(cluster['ci_high'])} ({cluster['clusters']} papers, "
            f"{cluster['resamples']} resamples)"
        )
    agreement = metrics.get("agreement")
    if isinstance(agreement, dict):
        label = "Independent agreement" if agreement_kind == "independent" else "Self-agreement"
        kappa = (
            f"{float(agreement['kappa']):.3f}"
            if agreement.get("kappa_defined", True)
            else "not estimable (degenerate)"
        )
        lines.append(
            f"- {label}: raw {_pct(agreement['raw_agreement'])}, "
            f"Cohen's κ {kappa} (n={agreement['n']})"
        )
        if not agreement.get("kappa_defined", True):
            lines.append(
                "- Agreement caveat: both label sets used a single label, so the "
                "overlap does not test agreement on the non-claim error class."
            )
    else:
        lines.append(
            "- Agreement: **pending** — "
            f"{relabelled} relabel rows filled; the blind overlap is still blank."
        )
    lines.append("")
    return lines


def _gate_section(metrics: dict[str, object] | None, *, agreement_kind: str = "self") -> list[str]:
    if metrics is None:
        return [
            "## Gate decision",
            "",
            f"- **Open** — audited precision is **{NOT_MEASURED}**.",
            "",
        ]
    overall = metrics["overall"]
    assert isinstance(overall, dict)
    precision = float(overall["precision"])
    agreement = metrics.get("agreement")
    verdict = "PASS" if precision >= GATE_PRECISION_FLOOR else "FAIL"
    action = "proceed to P2" if precision >= GATE_PRECISION_FLOOR else "fix extraction before P2"
    lines = [
        "## Gate decision",
        "",
        f"- **{verdict}** — audited precision {_pct(precision)} vs the "
        f"{_pct(GATE_PRECISION_FLOOR)} floor ({action}).",
        f"- Interval: Wilson {_pct(overall['ci_low'])} to {_pct(overall['ci_high'])}.",
    ]
    if not isinstance(agreement, dict):
        lines.append("- Caveat: agreement is still pending, so the figure is single-labeler.")
    else:
        kind = "inter-annotator" if agreement_kind == "independent" else "self"
        kappa = (
            f"{float(agreement['kappa']):.3f}"
            if agreement.get("kappa_defined", True)
            else "not estimable (degenerate)"
        )
        lines.append(
            f"- Agreement: {kind}, raw {_pct(agreement['raw_agreement'])}, "
            f"Cohen's κ {kappa} (n={agreement['n']})."
        )
        if not agreement.get("kappa_defined", True):
            lines.append(
                "- Caveat: the overlap contains only `CORRECT` labels, so it does not "
                "validate the 7 `NOT_A_CLAIM` calls; κ is undefined."
            )
    lines.append("")
    return lines


def build_report(
    *,
    manifest_path: Path,
    audit_path: Path,
    ledger_path: Path | None,
    out_path: Path,
    run_report_path: Path | None = DEFAULT_RUN_REPORT,
    overlap_path: Path | None = None,
) -> str:
    run = _load_run_report(run_report_path) if run_report_path else None
    metrics: dict[str, object] | None = None
    if audit_path.exists():
        try:
            _, metrics = _load_audit_metrics(audit_path, overlap_path)
        except AuditError:
            metrics = None
    corpus = read_manifest(manifest_path).counts if manifest_path.exists() else None

    precision_value = NOT_MEASURED
    precision_interval = NOT_MEASURED
    if metrics is not None:
        overall = metrics["overall"]
        assert isinstance(overall, dict)
        precision_value = _pct(overall["precision"])
        precision_interval = f"{_pct(overall['ci_low'])}-{_pct(overall['ci_high'])}"

    cost_per_paper = NOT_MEASURED
    tokens_per_paper = NOT_MEASURED
    p95_latency = NOT_MEASURED
    if run is not None:
        papers = max(int(run.get("papers_processed") or 0), 1)
        cost_per_paper = _money(Decimal(str(run.get("list_price_usd") or 0)) / papers)
        tokens_per_paper = f"{int(run.get('total_tokens') or 0) / papers:,.1f}"
        latency = run.get("latency_ms") or {}
        assert isinstance(latency, dict)
        p95_latency = f"{int(float(latency.get('p95') or 0)):,} ms"

    agreement = metrics.get("agreement") if metrics is not None else None
    agreement_kind = (
        "independent"
        if overlap_path is not None and overlap_path.exists() and isinstance(agreement, dict)
        else "self"
    )
    limitations = [
        "- The audit covers 200 claims from a seeded paper sample; claims within a "
        "paper are not independent, hence the paper-level cluster bootstrap.",
        "- Silver labels are teacher output and are never used for evaluation; gold "
        "labels live only in `eval/audit/`.",
        "- Generation config is fixed by ADR-0019 and not tuned against this audit.",
    ]
    if isinstance(agreement, dict):
        limitations.insert(
            0,
            "- Primary labels are from one labeler; agreement is reported on the "
            "seeded overlap subset.",
        )
        if not agreement.get("kappa_defined", True):
            limitations.insert(
                1,
                "- The overlap contains only `CORRECT` labels, so it does not validate "
                "the `NOT_A_CLAIM` calls and κ is undefined.",
            )
    else:
        limitations.insert(
            0,
            "- Single labeler until the agreement step lands; agreement is reported by "
            "`scripts/audit_validate.py`.",
        )

    lines = [
        "# P1 baseline report",
        "",
        "> Generated by `python scripts/build_p1_report.py` (`make report`).",
        "> Values are read from the run report, corpus manifest, audit file, and overlap file.",
        f"> Anything not produced yet is marked **{NOT_MEASURED}**.",
        "",
        *_gate_section(metrics, agreement_kind=agreement_kind),
        "## Headline metrics",
        "",
        "| Metric | Value | Source |",
        "| :-- | :-- | :-- |",
        f"| Claim extraction precision (Wilson 95% CI) | **{precision_value}** "
        f"({precision_interval}) | audit |",
        f"| Cost per paper | {cost_per_paper} | run report |",
        f"| Tokens per paper | {tokens_per_paper} | run report |",
        f"| p95 latency | {p95_latency} | run report |",
        f"| Corpus claim coverage | "
        f"{'see corpus section' if corpus else NOT_MEASURED} | manifest |",
        "",
        *_run_sections(run),
        *_audit_section(audit_path, overlap_path),
        *_corpus_section(manifest_path),
        "## Limitations",
        "",
        *limitations,
        "",
        "## Reproduction",
        "",
        "```",
        "python scripts/build_p1_report.py",
        "python scripts/run_baseline_extraction.py --sample 100 --execute "
        "--model gemini-3.5-flash-lite "
        "--out eval/silver/claims_v1/baseline_flashlite/estimate "
        "--silver-dir eval/silver/claims_v1/baseline_flashlite "
        "--run-id p1-10-flashlite-s20261114-n100",
        "python scripts/audit_validate.py --audit eval/audit/claims_audit_v1.csv "
        "--overlap eval/audit/claims_audit_v1_overlap_labelled.csv "
        "--out docs/reports/P1-audit.md",
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
    parser.add_argument("--overlap", type=Path, default=DEFAULT_OVERLAP)
    parser.add_argument("--run-report", type=Path, default=DEFAULT_RUN_REPORT)
    parser.add_argument("--ledger", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    build_report(
        manifest_path=args.manifest,
        audit_path=args.audit,
        ledger_path=args.ledger,
        out_path=args.out,
        run_report_path=args.run_report,
        overlap_path=args.overlap,
    )
    print(f"report: {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
