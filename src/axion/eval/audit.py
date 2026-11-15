"""Deterministic sampling and metrics for the P1 claim audit.

The audit measures claim-extraction precision with a human-labelled sample.
This module only prepares the export and computes the reported numbers; it
never invents labels. The procedure and label definitions live in
``docs/eval/AUDIT_RUBRIC.md``.

Input is a JSONL file of candidate claims (the future P1-10 output). The
schema is intentionally small so extraction can evolve without rewriting the
audit tooling:

    {"claim_id": "...", "paper_id": "...", "claim_text": "...",
     "evidence_span": "...", "section": "...", "paper_title": "...",
     "context_before": "...", "context_after": "..."}

Sampling is uniform over claims with a fixed seed, as required by the rubric;
stratification happens only at reporting time. The dev/test split is assigned
per **paper** so a paper can never straddle the split.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

RUBRIC_VERSION = "v2"
DEFAULT_SEED = 20261114
MIN_SAMPLE = 200
MIN_PAPERS = 40
MAX_CLAIMS_PER_PAPER = 5
BOOTSTRAP_RESAMPLES = 2000
DEV_FRACTION = 0.5
OVERLAP_FRACTION = 0.2

LABELS = (
    "CORRECT",
    "NOT_A_CLAIM",
    "DISTORTED",
    "UNSUPPORTED_SPAN",
    "DUPLICATE",
)

AUDIT_COLUMNS = (
    "claim_id",
    "paper_id",
    "paper_title",
    "section",
    "claim_text",
    "evidence_span",
    "context_before",
    "context_after",
    "label",
    "note",
    "labeler",
    "date",
    "rubric_version",
    "split",
    "relabel_label",
)


class AuditError(Exception):
    """Raised when audit input or labels are invalid."""


class ClaimRecord(BaseModel):
    """One candidate claim as exported for human labelling."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str
    paper_id: str
    claim_text: str
    evidence_span: str = ""
    section: str = ""
    paper_title: str = ""
    context_before: str = ""
    context_after: str = ""


def load_claims(path: Path) -> list[ClaimRecord]:
    """Load and validate a claim JSONL file; reject duplicate claim ids."""
    claims: list[ClaimRecord] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                claim = ClaimRecord.model_validate_json(line)
            except ValidationError as exc:
                raise AuditError(f"{path}:{line_number}: invalid claim: {exc}") from exc
            if claim.claim_id in seen:
                raise AuditError(f"{path}:{line_number}: duplicate claim_id {claim.claim_id!r}")
            seen.add(claim.claim_id)
            claims.append(claim)
    if not claims:
        raise AuditError(f"{path}: no claims found")
    return claims


def corpus_snapshot_id(claims: Iterable[ClaimRecord]) -> str:
    """Stable hash of the claim set, recorded alongside the sample seed."""
    canonical = sorted(
        json.dumps(
            [claim.claim_id, claim.paper_id, claim.claim_text],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        for claim in claims
    )
    digest = hashlib.sha256("\n".join(canonical).encode("utf-8"))
    return digest.hexdigest()


def sample_claims(
    claims: Sequence[ClaimRecord], size: int, seed: int = DEFAULT_SEED
) -> list[ClaimRecord]:
    """Draw a reproducible uniform sample, returned in claim-id order."""
    if size <= 0:
        raise AuditError("sample size must be positive")
    if size > len(claims):
        raise AuditError(f"sample size {size} exceeds the {len(claims)} available claims")
    ordered = sorted(claims, key=lambda claim: claim.claim_id)
    sample = random.Random(seed).sample(ordered, size)
    return sorted(sample, key=lambda claim: claim.claim_id)


def sample_claims_by_paper(
    claims: Sequence[ClaimRecord],
    *,
    target_claims: int = MIN_SAMPLE,
    max_per_paper: int = MAX_CLAIMS_PER_PAPER,
    min_papers: int = MIN_PAPERS,
    seed: int = DEFAULT_SEED,
) -> list[ClaimRecord]:
    """Draw a seeded audit sample capped at ``max_per_paper`` claims per paper.

    Claims within a paper are not independent, so an audit of 200 claims from
    five papers overstates its evidence. This sampler draws up to
    ``max_per_paper`` claims from each paper and keeps adding papers (in a
    seeded order) until both ``target_claims`` and ``min_papers`` are met.
    """
    if target_claims <= 0 or max_per_paper <= 0 or min_papers <= 0:
        raise AuditError("target claims, per-paper cap, and paper minimum must be positive")
    by_paper: dict[str, list[ClaimRecord]] = {}
    for claim in sorted(claims, key=lambda item: item.claim_id):
        by_paper.setdefault(claim.paper_id, []).append(claim)
    if len(by_paper) < min_papers:
        raise AuditError(
            f"audit needs at least {min_papers} papers with accepted claims; "
            f"got {len(by_paper)}"
        )
    if len(claims) < target_claims:
        raise AuditError(f"audit needs at least {target_claims} accepted claims; got {len(claims)}")

    papers = sorted(by_paper)
    random.Random(seed).shuffle(papers)
    chosen: list[ClaimRecord] = []
    papers_used = 0
    for paper in papers:
        pool = by_paper[paper]
        take = min(max_per_paper, len(pool))
        chosen.extend(random.Random(f"{seed}:{paper}").sample(pool, take))
        papers_used += 1
        if len(chosen) >= target_claims and papers_used >= min_papers:
            break
    if len(chosen) < target_claims or papers_used < min_papers:
        raise AuditError("could not reach the claim and paper minimums with the per-paper cap")
    return sorted(chosen, key=lambda claim: claim.claim_id)


def assign_paper_splits(
    paper_ids: Iterable[str], seed: int = DEFAULT_SEED, dev_fraction: float = DEV_FRACTION
) -> dict[str, str]:
    """Assign papers to dev/test deterministically, balancing the counts.

    Papers are ordered by a seeded hash and the first ``dev_fraction`` share
    goes to dev. Splitting by paper prevents a paper leaking across sets.
    """
    if not 0.0 < dev_fraction < 1.0:
        raise AuditError("dev_fraction must be strictly between 0 and 1")
    unique = sorted(set(paper_ids))
    if not unique:
        raise AuditError("cannot split an empty set of papers")

    def order(paper_id: str) -> tuple[str, str]:
        return (hashlib.sha256(f"{seed}:{paper_id}".encode()).hexdigest(), paper_id)

    ranked = sorted(unique, key=order)
    dev_count = min(max(round(len(ranked) * dev_fraction), 0), len(ranked))
    return {
        paper_id: ("dev" if index < dev_count else "test") for index, paper_id in enumerate(ranked)
    }


def export_rows(claims: Sequence[ClaimRecord], seed: int = DEFAULT_SEED) -> list[dict[str, str]]:
    """Build audit rows with blank label fields, ready for a human."""
    splits = assign_paper_splits((claim.paper_id for claim in claims), seed=seed)
    rows: list[dict[str, str]] = []
    for claim in claims:
        rows.append(
            {
                "claim_id": claim.claim_id,
                "paper_id": claim.paper_id,
                "paper_title": claim.paper_title,
                "section": claim.section,
                "claim_text": claim.claim_text,
                "evidence_span": claim.evidence_span,
                "context_before": claim.context_before,
                "context_after": claim.context_after,
                "label": "",
                "note": "",
                "labeler": "",
                "date": "",
                "rubric_version": RUBRIC_VERSION,
                "split": splits[claim.paper_id],
                "relabel_label": "",
            }
        )
    return rows


def select_overlap_rows(
    rows: Sequence[dict[str, str]],
    *,
    fraction: float = OVERLAP_FRACTION,
    seed: int = DEFAULT_SEED,
) -> list[dict[str, str]]:
    """Select a deterministic seeded subset for an independent second labeler.

    The subset is chosen by a seeded SHA-256 rank over ``claim_id``, so the same
    export always yields the same overlap without exporting a hidden column.
    """
    if not 0.0 < fraction <= 1.0:
        raise AuditError("overlap fraction must be in (0, 1]")
    if not rows:
        return []
    ranked = sorted(
        rows,
        key=lambda row: (
            hashlib.sha256(f"{seed}:{row['claim_id']}".encode()).hexdigest(),
            row["claim_id"],
        ),
    )
    count = max(1, round(len(ranked) * fraction))
    return ranked[:count]


def write_export(path: Path, rows: Sequence[dict[str, str]]) -> None:
    """Write the audit CSV with a stable column order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_audit(path: Path) -> list[dict[str, str]]:
    """Read a labelled audit CSV and validate its required columns."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [column for column in AUDIT_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise AuditError(f"{path}: missing columns: {', '.join(missing)}")
        return list(reader)


def wilson_interval(
    successes: int, total: int, z: float = 1.959963984540054
) -> tuple[float, float]:
    """Two-sided Wilson score interval for a binomial proportion."""
    if total <= 0:
        raise AuditError("Wilson interval needs at least one observation")
    if not 0 <= successes <= total:
        raise AuditError("successes must be between 0 and total")
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
        / denominator
    )
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def cluster_bootstrap_interval(
    rows: Sequence[dict[str, str]],
    *,
    cluster_key: str = "paper_id",
    resamples: int = BOOTSTRAP_RESAMPLES,
    seed: int = DEFAULT_SEED,
    confidence: float = 0.95,
) -> dict[str, object]:
    """Percentile interval from resampling whole papers, not claims.

    Claims from one paper share a source and a context, so a claim-level
    Wilson interval is too narrow. This resamples papers with replacement and
    recomputes precision on the pooled claims of each resampled paper.
    """
    if not rows:
        raise AuditError("cluster bootstrap needs at least one row")
    if resamples < 100:
        raise AuditError("cluster bootstrap needs at least 100 resamples")
    if not 0.0 < confidence < 1.0:
        raise AuditError("confidence must be strictly between 0 and 1")

    clusters: dict[str, list[int]] = {}
    for row in rows:
        key = (row.get(cluster_key) or "").strip() or "(none)"
        clusters.setdefault(key, []).append(1 if row.get("label") == "CORRECT" else 0)
    keys = sorted(clusters)
    if len(keys) < 2:
        raise AuditError("cluster bootstrap needs at least two papers")

    generator = random.Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        picked = [keys[generator.randrange(len(keys))] for _ in keys]
        outcomes = [value for key in picked for value in clusters[key]]
        estimates.append(sum(outcomes) / len(outcomes))
    estimates.sort()
    tail = (1.0 - confidence) / 2.0
    low_index = int(math.floor(tail * resamples))
    high_index = min(resamples - 1, int(math.ceil((1.0 - tail) * resamples)) - 1)
    return {
        "method": "paper-level cluster bootstrap (percentile)",
        "cluster_key": cluster_key,
        "clusters": len(keys),
        "resamples": resamples,
        "seed": seed,
        "confidence": confidence,
        "ci_low": estimates[low_index],
        "ci_high": estimates[high_index],
    }


def cohen_kappa(first: Sequence[str], second: Sequence[str]) -> float:
    """Cohen's kappa for two paired label sequences."""
    if len(first) != len(second):
        raise AuditError("paired labels must have equal length")
    if not first:
        raise AuditError("kappa needs at least one paired label")
    total = len(first)
    observed = sum(1 for a, b in zip(first, second, strict=True) if a == b) / total
    counts_first = Counter(first)
    counts_second = Counter(second)
    expected = sum(
        (counts_first[label] / total) * (counts_second[label] / total)
        for label in set(counts_first) | set(counts_second)
    )
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)


def _precision(rows: Sequence[dict[str, str]]) -> dict[str, object]:
    total = len(rows)
    correct = sum(1 for row in rows if row["label"] == "CORRECT")
    low, high = wilson_interval(correct, total)
    return {
        "n": total,
        "correct": correct,
        "precision": correct / total,
        "ci_low": low,
        "ci_high": high,
    }


def compute_metrics(rows: Sequence[dict[str, str]]) -> dict[str, object]:
    """Compute precision, Wilson CI, failure breakdown, and self-agreement.

    Rows without a ``label`` are treated as not yet labelled and excluded; the
    count is reported so a partial audit cannot silently look complete.
    """
    labelled: list[dict[str, str]] = []
    unknown: list[str] = []
    unlabelled = 0
    for row in rows:
        label = (row.get("label") or "").strip()
        if not label:
            unlabelled += 1
            continue
        if label not in LABELS:
            unknown.append(f"{row.get('claim_id', '?')}: {label}")
            continue
        labelled.append(row)
    if unknown:
        raise AuditError("unknown labels: " + "; ".join(unknown))
    if not labelled:
        raise AuditError("no labelled rows found")

    overall = _precision(labelled)
    breakdown = Counter(row["label"] for row in labelled)

    by_section: dict[str, dict[str, object]] = {}
    for section in sorted({row.get("section") or "(none)" for row in labelled}):
        subset = [row for row in labelled if (row.get("section") or "(none)") == section]
        by_section[section] = _precision(subset)

    by_paper: dict[str, dict[str, object]] = {}
    for paper in sorted({row.get("paper_id") or "(none)" for row in labelled}):
        subset = [row for row in labelled if (row.get("paper_id") or "(none)") == paper]
        by_paper[paper] = _precision(subset)

    try:
        cluster = cluster_bootstrap_interval(labelled, seed=DEFAULT_SEED)
    except AuditError:
        cluster = None

    relabelled = [
        row
        for row in labelled
        if (row.get("relabel_label") or "").strip()
        and (row["relabel_label"] or "").strip() in LABELS
    ]
    agreement: dict[str, object] | None = None
    if relabelled:
        first = [row["label"] for row in relabelled]
        second = [(row["relabel_label"] or "").strip() for row in relabelled]
        agreement = {
            "n": len(relabelled),
            "raw_agreement": sum(1 for a, b in zip(first, second, strict=True) if a == b)
            / len(relabelled),
            "kappa": cohen_kappa(first, second),
        }

    return {
        "rubric_version": RUBRIC_VERSION,
        "overall": overall,
        "breakdown": {label: breakdown.get(label, 0) for label in LABELS},
        "by_section": by_section,
        "by_paper": by_paper,
        "cluster_bootstrap": cluster,
        "agreement": agreement,
        "unlabelled": unlabelled,
    }


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def render_markdown(metrics: dict[str, object], *, source: str) -> str:
    """Render metrics as a report-ready Markdown section."""
    overall = metrics["overall"]
    assert isinstance(overall, dict)
    breakdown = metrics["breakdown"]
    assert isinstance(breakdown, dict)
    lines = [
        "# Claim audit metrics",
        "",
        f"Generated by `python scripts/audit_metrics.py {source}`.",
        "",
        "## Overall",
        "",
        f"- Labelled claims: **{overall['n']}**",
        f"- Correct: **{overall['correct']}**",
        f"- Precision: **{_percent(float(overall['precision']))}** "
        f"(Wilson 95% CI {_percent(float(overall['ci_low']))} to "
        f"{_percent(float(overall['ci_high']))})",
        f"- Not yet labelled: **{metrics['unlabelled']}**",
        "",
        "## Failure breakdown",
        "",
        "| Label | Count |",
        "| :-- | --: |",
    ]
    cluster = metrics.get("cluster_bootstrap")
    if isinstance(cluster, dict):
        lines += [
            "",
            "## Paper-level cluster bootstrap",
            "",
            "Claims within a paper are not independent. This interval resamples",
            "whole papers with replacement.",
            "",
            f"- Clusters (papers): **{cluster['clusters']}**",
            f"- Resamples: **{cluster['resamples']}** (seed {cluster['seed']})",
            f"- Precision CI: **{_percent(float(cluster['ci_low']))} to "
            f"{_percent(float(cluster['ci_high']))}**",
        ]

    for label in LABELS:
        lines.append(f"| `{label}` | {breakdown[label]} |")

    by_section = metrics["by_section"]
    assert isinstance(by_section, dict)
    lines += [
        "",
        "## Precision by section",
        "",
        "| Section | n | Precision |",
        "| :-- | --: | --: |",
    ]
    for section, stats in by_section.items():
        assert isinstance(stats, dict)
        lines.append(f"| {section} | {stats['n']} | {_percent(float(stats['precision']))} |")

    agreement = metrics["agreement"]
    if isinstance(agreement, dict):
        lines += [
            "",
            "## Self-agreement (≥7-day relabel)",
            "",
            f"- Paired claims: **{agreement['n']}**",
            f"- Raw agreement: **{_percent(float(agreement['raw_agreement']))}**",
            f"- Cohen's κ: **{float(agreement['kappa']):.3f}**",
        ]
    else:
        lines += ["", "## Self-agreement", "", "Not available: no relabel column filled yet."]

    lines += [
        "",
        "## Limitations",
        "",
        "- Single labeler; agreement is self-agreement, not inter-annotator agreement.",
        "- Precision only: no recall is measurable without an exhaustive gold set.",
        "- Claims within a paper are not independent: the Wilson interval treats them",
        "  as independent and is therefore too narrow. Report the paper-level cluster",
        "  bootstrap alongside it; it is still limited by the number of papers audited.",
        "- See `docs/eval/AUDIT_RUBRIC.md` for label definitions and sampling rules.",
        "",
    ]
    return "\n".join(lines)
