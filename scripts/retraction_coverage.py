"""Measure Retraction Watch coverage against Europe PMC (P1-06).

Usage:
    python scripts/retraction_coverage.py \
        --csv data/retraction-watch/retraction_watch.csv \
        --snapshot-commit 560ad745cb621e240501422ad485bd81b4590860 \
        --snapshot-date 2026-11-13 \
        --out docs/reports/P1-retraction-coverage.md \
        --manifest-out docs/reports/P1-retraction-manifest.json

The full CSV has ~74k rows; resolving every DOI/PMID live would hammer Europe
PMC. This script reports exact snapshot-level counts and a seeded sample of
retraction records resolved against Europe PMC (with Wilson 95% CIs). Raw CSV
rows are never written: the manifest is ID-only plus snapshot hashes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from axion.config.settings import Settings
from axion.ingest.europepmc import EuropePmcClient, EuropePmcError, EuropePmcRecord
from axion.ingest.retractions import (
    RetractionIndex,
    RetractionRecord,
    build_manifest,
    load_retraction_watch_csv,
    write_manifest,
)

DEFAULT_SEED = 20261114


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


@dataclass
class SampleRow:
    record_id: str
    nature: str
    has_doi: bool
    has_pmid: bool
    found: bool = False
    pmcid: str | None = None
    is_open_access: bool | None = None
    in_epmc: bool | None = None
    pmid: str | None = None
    cited_by_count: int | None = None
    citations_checked: bool = False
    error: str | None = None


@dataclass
class Coverage:
    total_rows: int = 0
    natures: Counter[str] = field(default_factory=Counter)
    retractions: int = 0
    with_doi: int = 0
    with_pmid: int = 0
    with_either: int = 0
    sample: list[SampleRow] = field(default_factory=list)

    @property
    def resolved(self) -> list[SampleRow]:
        return [row for row in self.sample if row.found]

    @property
    def with_full_text(self) -> list[SampleRow]:
        return [row for row in self.resolved if row.in_epmc]

    @property
    def open_access(self) -> list[SampleRow]:
        return [row for row in self.resolved if row.is_open_access]


def file_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def summarize_snapshot(records: list[RetractionRecord]) -> Coverage:
    coverage = Coverage(total_rows=len(records))
    for record in records:
        coverage.natures[record.nature] += 1
        if record.original_doi:
            coverage.with_doi += 1
        if record.original_pmid:
            coverage.with_pmid += 1
        if record.original_doi or record.original_pmid:
            coverage.with_either += 1
        if record.is_retraction:
            coverage.retractions += 1
    return coverage


def resolve_sample(
    records: list[RetractionRecord],
    client: EuropePmcClient,
    *,
    size: int,
    seed: int,
    check_citations: bool = True,
) -> list[SampleRow]:
    linkable = [
        record
        for record in records
        if record.is_retraction and (record.original_doi or record.original_pmid)
    ]
    if size > len(linkable):
        raise ValueError(f"sample size {size} exceeds {len(linkable)} linkable retractions")
    chosen = sorted(
        random.Random(seed).sample(sorted(linkable, key=lambda record: record.record_id), size),
        key=lambda record: record.record_id,
    )
    rows: list[SampleRow] = []
    for record in chosen:
        row = SampleRow(
            record_id=record.record_id,
            nature=record.nature,
            has_doi=bool(record.original_doi),
            has_pmid=bool(record.original_pmid),
        )
        try:
            match = None
            if record.original_doi:
                match = client.find_by_doi(record.original_doi)
            if match is None and record.original_pmid:
                match = client.find_by_pmid(record.original_pmid)
        except (EuropePmcError, OSError) as exc:
            row.error = type(exc).__name__
            rows.append(row)
            continue
        if isinstance(match, EuropePmcRecord):
            row.found = True
            row.pmcid = match.pmcid
            row.is_open_access = match.is_open_access
            row.in_epmc = match.has_full_text
            row.pmid = match.pmid or record.original_pmid
            row.cited_by_count = match.cited_by_count
        rows.append(row)

    if check_citations:
        for row in rows:
            if not row.found or not row.pmid:
                continue
            try:
                page = client.citations(row.pmid, page_size=1)
            except (EuropePmcError, OSError):
                continue
            row.cited_by_count = page.hit_count
            row.citations_checked = True
    return rows


def _percent(numerator: int, denominator: int) -> str:
    if denominator == 0:
        return "—"
    return f"{numerator / denominator * 100:.1f}%"


def _ci(successes: int, total: int) -> str:
    if total == 0:
        return "—"
    low, high = wilson(successes, total)
    return f"{low * 100:.1f} to {high * 100:.1f}%"


def render(
    coverage: Coverage,
    *,
    snapshot_commit: str,
    snapshot_date: str,
    csv_sha256: str,
    csv_bytes: int,
    sample_size: int,
    seed: int,
    live: bool,
) -> str:
    sample = coverage.sample
    resolved = coverage.resolved
    errors = [row for row in sample if row.error]
    oa = coverage.open_access
    full_text = coverage.with_full_text
    checked = [row for row in sample if row.citations_checked]
    cited = [row for row in checked if (row.cited_by_count or 0) > 0]
    counts = [row.cited_by_count or 0 for row in checked]

    lines = [
        "# Retraction Watch coverage (P1-06)",
        "",
        "Generated by `python scripts/retraction_coverage.py`. Numbers come from the snapshot",
        "and the Europe PMC response cache; no value is hand-entered.",
        "",
        "## Source and licence",
        "",
        "- **Source:** Retraction Watch database, distributed by Crossref.",
        "- **Licence:** CC0. Crossref Metadata Retrieval states "
        "“Open Funder Registry, Retraction Watch database — CC0”: "
        "<https://www.crossref.org/documentation/retrieve-metadata/> (verified 2026-11-14).",
        f"- **Snapshot commit:** `{snapshot_commit}` ({snapshot_date}).",
        f"- **CSV SHA-256:** `{csv_sha256}` ({csv_bytes:,} bytes).",
        "- The raw CSV stays under `data/` and is never committed; the manifest is ID-only.",
        "",
        "## Full snapshot",
        "",
        "| Metric | Count | Share of rows |",
        "| :-- | --: | --: |",
        f"| Rows | {coverage.total_rows:,} | 100% |",
        f"| Retraction (nature = Retraction) | {coverage.retractions:,} | "
        f"{_percent(coverage.retractions, coverage.total_rows)} |",
        f"| Any original DOI | {coverage.with_doi:,} | "
        f"{_percent(coverage.with_doi, coverage.total_rows)} |",
        f"| Any original PMID | {coverage.with_pmid:,} | "
        f"{_percent(coverage.with_pmid, coverage.total_rows)} |",
        f"| DOI or PMID (linkable) | {coverage.with_either:,} | "
        f"{_percent(coverage.with_either, coverage.total_rows)} |",
        "",
        "### Rows by nature",
        "",
        "| Nature | Rows |",
        "| :-- | --: |",
    ]
    for nature, count in sorted(coverage.natures.items()):
        lines.append(f"| {nature or '(blank)'} | {count:,} |")

    lines += [
        "",
        "## Europe PMC resolution sample",
        "",
        f"Seeded uniform sample of **{sample_size}** linkable retractions "
        f"(seed `{seed}`, {'live' if live else 'cache-only'}).",
        "",
        "| Metric | Count | Share of sample | Wilson 95% CI |",
        "| :-- | --: | --: | --: |",
        f"| Sampled retractions | {len(sample):,} | 100% | — |",
        f"| Found in Europe PMC | {len(resolved):,} | {_percent(len(resolved), len(sample))} | "
        f"{_ci(len(resolved), len(sample))} |",
        f"| Open access (`isOpenAccess`) | {len(oa):,} | {_percent(len(oa), len(resolved))} | "
        f"{_ci(len(oa), len(resolved))} |",
        f"| Full text in Europe PMC (`inEPMC`) | {len(full_text):,} | "
        f"{_percent(len(full_text), len(resolved))} | {_ci(len(full_text), len(resolved))} |",
        f"| Has a PMCID | {sum(1 for row in resolved if row.pmcid):,} | "
        f"{_percent(sum(1 for row in resolved if row.pmcid), len(resolved))} | "
        f"{_ci(sum(1 for row in resolved if row.pmcid), len(resolved))} |",
        f"| Resolution errors (not counted as missing) | {len(errors):,} | — | — |",
        "",
        "## Citers",
        "",
        f"Citation lists were checked for **{len(checked)}** resolved records with a PMID.",
        f"**{len(cited)}** ({_percent(len(cited), len(checked))}) have at least one citing paper.",
    ]
    if counts:
        lines += [
            f"Median citations per checked record: **{statistics.median(counts):.0f}**; "
            f"maximum: **{max(counts)}**.",
        ]
    lines += [
        "",
        "## Method and limitations",
        "",
        "- Snapshot counts are exact for the CSV at the recorded commit.",
        "- Europe PMC rates are sample estimates: only the sampled records were queried, "
        "so the CIs describe sampling uncertainty, not Europe PMC indexing error.",
        "- A record missing here may still have full text elsewhere; this measures "
        "Europe PMC availability, which is what the corpus can ingest.",
        "- Retraction Watch lists the *original paper* identifiers in the fields used "
        "(`OriginalPaperDOI` / `OriginalPaperPubMedID`); retraction notices are separate.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--snapshot-commit", required=True)
    parser.add_argument("--snapshot-date", required=True)
    parser.add_argument("--out", type=Path, default=Path("docs/reports/P1-retraction-coverage.md"))
    parser.add_argument(
        "--manifest-out",
        type=Path,
        default=Path("docs/reports/P1-retraction-manifest.json"),
    )
    parser.add_argument("--sample-size", type=int, default=150)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--offline", action="store_true", help="use only the response cache")
    args = parser.parse_args(argv)

    try:
        records = load_retraction_watch_csv(args.csv)
        coverage = summarize_snapshot(records)
        csv_sha256, csv_bytes = file_digest(args.csv)
        settings = Settings()
        client = EuropePmcClient.from_settings(settings)
        coverage.sample = resolve_sample(
            records,
            client,
            size=args.sample_size,
            seed=args.seed,
            check_citations=not args.offline,
        )
        index = RetractionIndex(records)
        if len(index) != len(records):  # pragma: no cover - constructor is 1:1
            raise RuntimeError("index size mismatch")

        report = render(
            coverage,
            snapshot_commit=args.snapshot_commit,
            snapshot_date=args.snapshot_date,
            csv_sha256=csv_sha256,
            csv_bytes=csv_bytes,
            sample_size=args.sample_size,
            seed=args.seed,
            live=not args.offline,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")

        manifest = build_manifest(
            [record for record in records if record.is_retraction],
            snapshot_commit=args.snapshot_commit,
            snapshot_date=args.snapshot_date,
            csv_sha256=csv_sha256,
            csv_bytes=csv_bytes,
            record_ids=[row.record_id for row in coverage.sample],
        )
        manifest["sample_seed"] = args.seed
        manifest["sample_size"] = args.sample_size
        manifest["report"] = str(args.out).replace("\\", "/")
        write_manifest(args.manifest_out, manifest)
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "rows": coverage.total_rows,
                "retractions": coverage.retractions,
                "sample": len(coverage.sample),
                "resolved": len(coverage.resolved),
                "full_text": len(coverage.with_full_text),
                "report": str(args.out),
                "manifest": str(args.manifest_out),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
