"""Ingest the P1 corpus: resumable, batched, and checkpointed.

Zero LLM cost. The committed output is an ID-only manifest bundle (papers,
cites, summary); full text stays in the untracked Europe PMC cache.

Usage:
    python scripts/ingest_corpus.py
    python scripts/ingest_corpus.py --config src/axion/config/corpus/infectious-disease.yaml

Stages checkpoint under ``data/corpus/<corpus_id>/``. Re-running after a crash,
sleep, or interrupted download resumes from the last completed batch. Europe
PMC requests are polite (1 request/second by default), and the contact email is
read from ``EUROPEPMC_CONTACT_EMAIL``.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

from axion.config.settings import Settings
from axion.ingest.corpus import (
    CorpusCite,
    CorpusConfig,
    CorpusCounts,
    CorpusFiles,
    CorpusManifest,
    CorpusPaper,
    JsonlCheckpoint,
    ResourceUsage,
    canonical_config_sha256,
    load_corpus_config,
    sha256_file,
    utc_now_iso,
    write_cites_csv,
    write_manifest,
    write_papers_csv,
)
from axion.ingest.europepmc import (
    EuropePmcClient,
    EuropePmcError,
    EuropePmcNotFoundError,
    EuropePmcRecord,
)
from axion.ingest.retractions import (
    RetractionRecord,
    load_retraction_watch_csv,
    normalize_doi,
)
from axion.link.citations import SourceIndex, SourceTarget
from axion.parse.jats import JatsParseError, parse_jats

BATCH_SIZE = 50
DEFAULT_CONFIG = Path("src/axion/config/corpus/infectious-disease.yaml")
DEFAULT_RW_CSV = Path("data/retraction-watch/retraction_watch.csv")
DEFAULT_RW_MANIFEST = Path("docs/reports/P1-retraction-manifest.json")
DEFAULT_OUT_PREFIX = Path("docs/reports/P1-corpus")
MIN_SOURCES = 30
MIN_CONTEXTS = 300


@dataclass(frozen=True)
class SourcePaper:
    pmcid: str
    pmid: str | None
    doi: str | None
    title: str | None
    year: int | None
    rw_record_ids: tuple[str, ...]
    order: int


@dataclass(frozen=True)
class CiterPaper:
    pmcid: str
    pmid: str
    doi: str | None
    title: str | None
    year: int | None


class IngestError(Exception):
    """Raised when the corpus cannot be built safely."""


def peak_rss_mb() -> float:
    """Best-effort process peak RSS, in MiB, using only the standard library."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        class ProcessMemoryCounters(ctypes.Structure):
            _fields_: ClassVar[list[tuple[str, Any]]] = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(ProcessMemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        handle = kernel32.GetCurrentProcess()
        if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
            return float(counters.PeakWorkingSetSize) / (1024 * 1024)
    if sys.platform.startswith("linux"):
        try:
            for line in Path("/proc/self/status").read_text(encoding="utf-8").splitlines():
                if line.startswith("VmHWM:"):
                    return int(line.split()[1]) / 1024
        except OSError:
            pass
    try:
        import resource

        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except (ImportError, OSError):
        return 0.0


def record_from_row(row: dict[str, Any]) -> EuropePmcRecord:
    return EuropePmcRecord(
        pmcid=row.get("pmcid"),
        pmid=row.get("pmid"),
        doi=row.get("doi"),
        title=row.get("title"),
        journal_title=row.get("journal"),
        year=row.get("year"),
        is_open_access=row.get("is_open_access"),
        has_full_text=row.get("has_full_text"),
        cited_by_count=int(row.get("cited_by_count") or 0),
    )


def record_row(record: EuropePmcRecord) -> dict[str, Any]:
    return {
        "pmcid": record.pmcid,
        "pmid": record.pmid,
        "doi": record.doi,
        "title": record.title,
        "journal": record.journal_title,
        "year": record.year,
        "is_open_access": record.is_open_access,
        "has_full_text": record.has_full_text,
        "cited_by_count": record.cited_by_count,
    }


def _chunks(values: list[str], size: int = BATCH_SIZE) -> list[list[str]]:
    return [values[start : start + size] for start in range(0, len(values), size)]


def resolve_by_dois(client: EuropePmcClient, dois: list[str]) -> dict[str, EuropePmcRecord]:
    found: dict[str, EuropePmcRecord] = {}
    unique = sorted({normalize_doi(doi) for doi in dois if normalize_doi(doi)})
    for chunk in _chunks(unique):
        query = "(" + " OR ".join(f'DOI:"{doi}"' for doi in chunk) + ")"
        page = client.search(query, page_size=min(1000, len(chunk) * 2))
        for record in page.records:
            doi = normalize_doi(record.doi)
            if doi:
                found[doi] = record
    return found


def resolve_by_pmids(client: EuropePmcClient, pmids: list[str]) -> dict[str, EuropePmcRecord]:
    found: dict[str, EuropePmcRecord] = {}
    unique = sorted({pmid for pmid in pmids if pmid}, key=int)
    for chunk in _chunks(unique):
        query = "EXT_ID:(" + " OR ".join(chunk) + ") AND SRC:MED"
        page = client.search(query, page_size=min(1000, len(chunk) * 2))
        for record in page.records:
            if record.pmid:
                found[record.pmid] = record
    return found


def _resolve_doi_chunk(
    client: EuropePmcClient, chunk: list[RetractionRecord]
) -> list[dict[str, Any]]:
    found = resolve_by_dois(
        client, [record.original_doi for record in chunk if record.original_doi]
    )
    rows: list[dict[str, Any]] = []
    for record in chunk:
        match = found.get(normalize_doi(record.original_doi) or "")
        if match is None:
            rows.append({"record_id": record.record_id, "found": False})
        else:
            rows.append({"record_id": record.record_id, "found": True, **record_row(match)})
    return rows


def _resolve_pmid_chunk(
    client: EuropePmcClient, chunk: list[RetractionRecord]
) -> list[dict[str, Any]]:
    found = resolve_by_pmids(
        client, [record.original_pmid for record in chunk if record.original_pmid]
    )
    rows: list[dict[str, Any]] = []
    for record in chunk:
        match = found.get(record.original_pmid or "")
        if match is None:
            rows.append({"record_id": record.record_id, "found": False})
        else:
            rows.append({"record_id": record.record_id, "found": True, **record_row(match)})
    return rows


def resolve_sources(
    client: EuropePmcClient,
    records: list[RetractionRecord],
    work_dir: Path,
    *,
    workers: int = 1,
) -> dict[str, dict[str, Any]]:
    """Resolve retraction records to Europe PMC, DOI first, then PMID."""
    doi_checkpoint = JsonlCheckpoint(work_dir / "sources_doi.jsonl", "record_id")
    pmid_checkpoint = JsonlCheckpoint(work_dir / "sources_pmid.jsonl", "record_id")
    doi_rows = doi_checkpoint.load()
    pmid_rows = pmid_checkpoint.load()

    missing_doi = [
        record for record in records if record.original_doi and record.record_id not in doi_rows
    ]
    doi_chunks = _chunks(missing_doi)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_resolve_doi_chunk, client, chunk) for chunk in doi_chunks]
        for index, future in enumerate(as_completed(futures), start=1):
            rows = future.result()
            doi_checkpoint.append(rows)
            doi_rows.update({str(row["record_id"]): row for row in rows})
            print(f"sources/DOI: {index}/{len(doi_chunks)} chunks", flush=True)

    missing_pmid = [
        record
        for record in records
        if record.original_pmid
        and not doi_rows.get(record.record_id, {}).get("found", False)
        and record.record_id not in pmid_rows
    ]
    pmid_chunks = _chunks(missing_pmid)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_resolve_pmid_chunk, client, chunk) for chunk in pmid_chunks]
        for index, future in enumerate(as_completed(futures), start=1):
            rows = future.result()
            pmid_checkpoint.append(rows)
            pmid_rows.update({str(row["record_id"]): row for row in rows})
            print(f"sources/PMID: {index}/{len(pmid_chunks)} chunks", flush=True)

    resolved: dict[str, dict[str, Any]] = {}
    for record in records:
        row = doi_rows.get(record.record_id)
        if not row or not row.get("found"):
            row = pmid_rows.get(record.record_id)
        if row and row.get("found"):
            resolved[record.record_id] = row
    return resolved


def source_papers(
    records: list[RetractionRecord],
    resolved: dict[str, dict[str, Any]],
    *,
    filters: Any,
) -> tuple[dict[str, SourcePaper], int, int, int, int]:
    non_oa = 0
    no_full_text = 0
    no_pmcid = 0
    without_pmid = 0
    by_pmcid: dict[str, SourcePaper] = {}
    for order, record in enumerate(records):
        row = resolved.get(record.record_id)
        if row is None:
            continue
        match = record_from_row(row)
        if filters.open_access and not match.is_open_access:
            non_oa += 1
            continue
        if filters.full_text and not match.has_full_text:
            no_full_text += 1
            continue
        if filters.require_pmcid and not match.pmcid:
            no_pmcid += 1
            continue
        if not match.pmcid:
            no_pmcid += 1
            continue
        existing = by_pmcid.get(match.pmcid)
        if existing is not None:
            by_pmcid[match.pmcid] = SourcePaper(
                pmcid=existing.pmcid,
                pmid=existing.pmid,
                doi=existing.doi,
                title=existing.title,
                year=existing.year,
                rw_record_ids=(*existing.rw_record_ids, record.record_id),
                order=existing.order,
            )
            continue
        if not match.pmid:
            without_pmid += 1
        by_pmcid[match.pmcid] = SourcePaper(
            pmcid=match.pmcid,
            pmid=match.pmid,
            doi=match.doi or record.original_doi,
            title=match.title or record.title,
            year=match.year or (record.original_date.year if record.original_date else None),
            rw_record_ids=(record.record_id,),
            order=order,
        )
    return by_pmcid, non_oa, no_full_text, no_pmcid, without_pmid


def _citation_row(
    client: EuropePmcClient, source: SourcePaper, config: CorpusConfig
) -> dict[str, Any]:
    assert source.pmid is not None
    med_ids: set[str] = set()
    ppr_ids: set[str] = set()
    hit_count = 0
    try:
        for page_number in range(1, config.citation_max_pages + 1):
            page = client.citations(
                source.pmid,
                page=page_number,
                page_size=config.citation_page_size,
            )
            hit_count = page.hit_count
            for record in page.records:
                if record.source == "MED":
                    med_ids.add(record.identifier)
                elif record.source == "PPR":
                    ppr_ids.add(record.identifier)
            if not page.records or len(med_ids) + len(ppr_ids) >= hit_count:
                break
    except EuropePmcNotFoundError:
        hit_count = 0
    return {
        "source_pmid": source.pmid,
        "hit_count": hit_count,
        "med_ids": sorted(med_ids, key=int),
        "ppr_ids": sorted(ppr_ids),
    }


def fetch_citations(
    client: EuropePmcClient,
    sources: list[SourcePaper],
    config: CorpusConfig,
    work_dir: Path,
    *,
    workers: int = 1,
) -> dict[str, dict[str, Any]]:
    checkpoint = JsonlCheckpoint(work_dir / "citations.jsonl", "source_pmid")
    rows = checkpoint.load()
    targets = [source for source in sources if source.pmid and source.pmid not in rows]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_citation_row, client, source, config) for source in targets]
        for index, future in enumerate(as_completed(futures), start=1):
            row = future.result()
            checkpoint.append([row])
            rows[str(row["source_pmid"])] = row
            if index % 50 == 0 or index == len(targets):
                print(f"citations: {index}/{len(targets)}", flush=True)
    return rows


def _resolve_citer_chunk(client: EuropePmcClient, chunk: list[str]) -> list[dict[str, Any]]:
    found = resolve_by_pmids(client, chunk)
    rows: list[dict[str, Any]] = []
    for pmid in chunk:
        match = found.get(pmid)
        if match is None:
            rows.append({"pmid": pmid, "found": False})
        else:
            rows.append({"pmid": pmid, "found": True, **record_row(match)})
    return rows


def resolve_citers(
    client: EuropePmcClient,
    citation_rows: dict[str, dict[str, Any]],
    work_dir: Path,
    *,
    workers: int = 1,
) -> dict[str, dict[str, Any]]:
    checkpoint = JsonlCheckpoint(work_dir / "citers.jsonl", "pmid")
    rows = checkpoint.load()
    med_ids = {
        str(identifier) for row in citation_rows.values() for identifier in row.get("med_ids", [])
    }
    missing = sorted(med_ids - set(rows), key=int)
    chunks = _chunks(missing)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_resolve_citer_chunk, client, chunk) for chunk in chunks]
        for index, future in enumerate(as_completed(futures), start=1):
            new_rows = future.result()
            checkpoint.append(new_rows)
            rows.update({str(row["pmid"]): row for row in new_rows})
            print(f"citers: {index}/{len(chunks)} chunks", flush=True)
    return rows


def citer_papers(
    med_ids: set[str],
    rows: dict[str, dict[str, Any]],
    *,
    filters: Any,
) -> tuple[dict[str, CiterPaper], int, int, int, int, int]:
    resolved = 0
    not_found = 0
    non_oa = 0
    no_full_text = 0
    no_pmcid = 0
    by_pmcid: dict[str, CiterPaper] = {}
    for pmid in sorted(med_ids, key=int):
        row = rows.get(pmid)
        if not row or not row.get("found"):
            not_found += 1
            continue
        resolved += 1
        match = record_from_row(row)
        if filters.open_access and not match.is_open_access:
            non_oa += 1
            continue
        if filters.full_text and not match.has_full_text:
            no_full_text += 1
            continue
        if not match.pmcid:
            no_pmcid += 1
            continue
        if match.pmcid not in by_pmcid:
            by_pmcid[match.pmcid] = CiterPaper(
                pmcid=match.pmcid,
                pmid=pmid,
                doi=match.doi,
                title=match.title,
                year=match.year,
            )
    return by_pmcid, resolved, not_found, non_oa, no_full_text, no_pmcid


def build_edges(
    sources: dict[str, SourcePaper],
    citations: dict[str, dict[str, Any]],
    citers: dict[str, CiterPaper],
) -> dict[str, set[str]]:
    """Return citer PMCID -> source PMCIDs."""
    citer_by_pmid = {citer.pmid: pmcid for pmcid, citer in citers.items()}
    edges: dict[str, set[str]] = {}
    for source in sources.values():
        if not source.pmid:
            continue
        row = citations.get(source.pmid, {})
        for pmid in row.get("med_ids", []):
            citer_pmcid = citer_by_pmid.get(str(pmid))
            if citer_pmcid is not None:
                edges.setdefault(citer_pmcid, set()).add(source.pmcid)
    return edges


def select_citers(
    citers: dict[str, CiterPaper],
    edges: dict[str, set[str]],
    source_order: dict[str, int],
    cap: int,
) -> tuple[list[CiterPaper], list[CiterPaper]]:
    eligible = [citer for citer in citers.values() if citer.pmcid in edges]
    eligible.sort(
        key=lambda citer: (
            min(source_order[source] for source in edges[citer.pmcid]),
            int(citer.pmid),
            citer.pmcid,
        )
    )
    remaining = cap - len(source_order)
    if remaining < 0:
        raise IngestError(
            f"{len(source_order)} sources exceed the total corpus cap of {cap}; "
            "the owner must raise the cap or narrow the sub-topic"
        )
    included = eligible[:remaining]
    return included, eligible[remaining:]


def cache_size(fulltext_dir: Path) -> tuple[int, int]:
    files = list(fulltext_dir.glob("*.xml")) if fulltext_dir.exists() else []
    return len(files), sum(path.stat().st_size for path in files)


def estimate_disk_mb(fulltext_dir: Path, papers: int) -> float:
    files = list(fulltext_dir.glob("*.xml")) if fulltext_dir.exists() else []
    sample = [path.stat().st_size for path in files[:200]]
    median = statistics.median(sample) if sample else 250_000
    return median * papers / (1024 * 1024)


def download_full_text(
    client: EuropePmcClient,
    papers: list[CorpusPaper],
    *,
    workers: int,
) -> tuple[dict[str, int], list[CorpusPaper], dict[str, int]]:
    """Cache full text for each paper; return byte sizes and failures.

    Europe PMC full-text responses can take ~20 seconds. A small thread pool
    hides that latency, while the client's global throttle still caps the
    request rate at one per second.
    """
    sizes: dict[str, int] = {}
    failures: dict[str, int] = {"source": 0, "citer": 0}
    available: list[CorpusPaper] = []
    downloaded = 0
    hits = 0

    def fetch_one(paper: CorpusPaper) -> tuple[CorpusPaper, int | None, bool, str | None]:
        path = client.cache_dir / "fulltext" / f"{paper.pmcid}.xml"
        existed = path.exists()
        try:
            text = client.fetch_full_text(paper.pmcid)
        except EuropePmcError as exc:
            return paper, None, existed, type(exc).__name__
        return paper, len(text.encode("utf-8")), existed, None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fetch_one, paper) for paper in papers]
        for index, future in enumerate(as_completed(futures), start=1):
            paper, size, existed, error = future.result()
            if size is None:
                failures[paper.role] += 1
                print(
                    f"fulltext failure {paper.pmcid}: {error or 'unknown'}",
                    flush=True,
                )
            else:
                sizes[paper.pmcid] = size
                available.append(paper)
                if existed:
                    hits += 1
                else:
                    downloaded += 1
            if index % 100 == 0 or index == len(papers):
                print(f"fulltext: {index}/{len(papers)}", flush=True)
    return sizes, available, {**failures, "downloaded": downloaded, "hits": hits}


def count_contexts(
    client: EuropePmcClient,
    sources: dict[str, SourcePaper],
    citers: dict[str, CiterPaper],
    edges: dict[str, set[str]],
) -> tuple[dict[tuple[str, str], int], int, int]:
    targets = [
        SourceTarget(
            key=source.pmcid,
            doi=source.doi,
            pmid=source.pmid,
            title=source.title,
            year=source.year,
        )
        for source in sources.values()
    ]
    index = SourceIndex(targets)
    parsed = 0
    failures = 0
    contexts: dict[tuple[str, str], int] = {}
    for citer in citers.values():
        try:
            text = client.fetch_full_text(citer.pmcid)
            paper = parse_jats(text, paper_id=citer.pmcid)
        except (EuropePmcError, JatsParseError):
            failures += 1
            continue
        parsed += 1
        counts = index.count_contexts(paper)
        for source_pmcid in edges.get(citer.pmcid, set()):
            contexts[(citer.pmcid, source_pmcid)] = counts.get(source_pmcid, 0)
    return contexts, parsed, failures


def render_report(
    config: CorpusConfig,
    manifest: CorpusManifest,
    *,
    rw_rows: int,
    report_path: Path,
) -> str:
    counts = manifest.counts
    resources = manifest.resources
    lines = [
        "# P1 corpus ingest",
        "",
        f"Generated by `scripts/ingest_corpus.py` at {manifest.created_at}.",
        "Every number below comes from the run; no LLM calls were made.",
        "",
        "## Definition",
        "",
        f"- Corpus: `{config.corpus_id}` ({config.sub_topic_key})",
        f"- Retraction Watch subject: `{config.retraction_subject}`",
        f"- Snapshot commit: `{manifest.retraction_snapshot['snapshot_commit']}` "
        f"({manifest.retraction_snapshot['snapshot_date']})",
        f"- CSV SHA-256: `{manifest.retraction_snapshot['csv_sha256']}`",
        f"- Cap: {config.cap:,} papers total, including citers (ADR-0013)",
        "- Full text: Europe PMC OA JATS, untracked; the committed manifest is ID-only",
        f"- RW retraction rows in snapshot: {rw_rows:,}; rows in this subject: "
        f"{counts.rw_retractions_in_subject:,}",
        "",
        "## Exact counts vs CONTEXT §4 minimums",
        "",
        "| Measure | Count | Minimum | Result |",
        "| :-- | --: | --: | :-- |",
        f"| Retracted OA source papers | {counts.sources_total:,} | {MIN_SOURCES} | "
        f"{'PASS' if counts.sources_total >= MIN_SOURCES else 'FAIL'} |",
        f"| Citation contexts | {counts.contexts_total:,} | {MIN_CONTEXTS} | "
        f"{'PASS' if counts.contexts_total >= MIN_CONTEXTS else 'FAIL'} |",
        "",
        "## Corpus",
        "",
        "| Stage | Count |",
        "| :-- | --: |",
        f"| RW retractions in subject | {counts.rw_retractions_in_subject:,} |",
        f"| RW linkable (DOI or PMID) | {counts.rw_linkable:,} |",
        f"| RW unlinkable | {counts.rw_unlinkable:,} |",
        f"| Sources resolved to Europe PMC | {counts.sources_resolved:,} |",
        f"| Sources not found | {counts.sources_not_found:,} |",
        f"| Sources non-OA | {counts.sources_non_oa:,} |",
        f"| Sources without full text | {counts.sources_without_full_text:,} |",
        f"| Sources without PMCID | {counts.sources_without_pmcid:,} |",
        f"| **Unique source papers** | **{counts.sources_total:,}** |",
        f"| Sources with PMID | {counts.sources_with_pmid:,} |",
        f"| Sources without PMID | {counts.sources_without_pmid:,} |",
        f"| Unique MEDLINE citers discovered | {counts.citers_med_unique:,} |",
        f"| PPR citers skipped | {counts.citers_ppr_skipped:,} |",
        f"| Citers resolved | {counts.citers_resolved:,} |",
        f"| Citers not found | {counts.citers_not_found:,} |",
        f"| Citers non-OA | {counts.citers_non_oa:,} |",
        f"| Citers without full text | {counts.citers_without_full_text:,} |",
        f"| Citers without PMCID | {counts.citers_without_pmcid:,} |",
        f"| Citers eligible | {counts.citers_eligible:,} |",
        f"| **Citers included** | **{counts.citers_included:,}** |",
        f"| Citers truncated by cap | {counts.citers_truncated:,} |",
        f"| **Papers total** | **{counts.papers_total:,}** |",
        f"| Papers in both roles (source and citer) | {counts.papers_both_roles:,} |",
        f"| Papers with PMID | {counts.papers_with_pmid:,} |",
        f"| Papers without PMID | {counts.papers_without_pmid:,} |",
        f"| Edges with contexts | {counts.edges_with_contexts:,} |",
        f"| Edges without contexts | {counts.edges_without_contexts:,} |",
        f"| Full-text failures | {counts.fulltext_failures:,} |",
        "",
        "## PMID gap and blast-radius limit",
        "",
        f"Europe PMC's citations endpoint is MEDLINE-only (`MED/<pmid>/citations`). "
        f"{counts.papers_without_pmid:,} of {counts.papers_total:,} corpus papers have no "
        f"PMID ({counts.papers_without_pmid_sources:,} sources, "
        f"{counts.papers_without_pmid_citers:,} citers). A source without a PMID has no "
        "discoverable citers through this endpoint, so blast-radius recall is capped by "
        "this source; PMID-less papers are also invisible as MEDLINE citers.",
        "",
        "## Resources",
        "",
        "| Metric | Estimate | Actual |",
        "| :-- | --: | --: |",
        f"| Disk (MiB) | {resources.estimated_disk_mb:,.1f} | {resources.disk_mb:,.1f} |",
        f"| Full-text cache (MiB) | — | {resources.fulltext_cache_bytes / (1024 * 1024):,.1f} |",
        f"| Peak RSS (MiB) | — | {resources.peak_rss_mb:,.1f} |",
        f"| Wall time (s) | — | {resources.wall_time_s:,.1f} |",
        "",
        f"Full-text cache: {resources.fulltext_cache_files:,} files; "
        f"{resources.fulltext_downloaded:,} downloaded, "
        f"{resources.fulltext_cache_hits:,} cache hits. Wall time split: metadata "
        f"{resources.metadata_wall_time_s:,.1f}s, full text "
        f"{resources.fulltext_wall_time_s:,.1f}s, parse/context "
        f"{resources.parse_wall_time_s:,.1f}s. Peak RSS is measured with the platform "
        "process API (not an estimate); disk includes the untracked full-text cache and "
        "checkpoints.",
        "",
        "## Files",
        "",
        f"- `{manifest.files.papers_csv}` ({manifest.files.papers_rows:,} rows, "
        f"SHA-256 `{manifest.files.papers_sha256}`)",
        f"- `{manifest.files.cites_csv}` ({manifest.files.cites_rows:,} rows, "
        f"SHA-256 `{manifest.files.cites_sha256}`)",
        f"- `{report_path}`",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {limitation}" for limitation in manifest.limitations)
    lines.append("")
    return "\n".join(lines)


def _load_rw_manifest(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    required = {"snapshot_commit", "snapshot_date", "csv_sha256", "csv_bytes"}
    if not required.issubset(raw):
        raise IngestError(f"RW manifest missing keys: {sorted(required - set(raw))}")
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--rw-csv", type=Path, default=DEFAULT_RW_CSV)
    parser.add_argument("--rw-manifest", type=Path, default=DEFAULT_RW_MANIFEST)
    parser.add_argument("--work-dir", type=Path, default=None)
    parser.add_argument("--out-prefix", type=Path, default=DEFAULT_OUT_PREFIX)
    parser.add_argument(
        "--max-sources",
        type=int,
        default=None,
        help="diagnostic smoke limit; never use for the committed P1 manifest",
    )
    args = parser.parse_args(argv)

    started = time.perf_counter()
    config = load_corpus_config(args.config)
    work_dir = args.work_dir or Path("data") / "corpus" / config.corpus_id
    work_dir.mkdir(parents=True, exist_ok=True)

    rw_manifest = _load_rw_manifest(args.rw_manifest)
    csv_sha = sha256_file(args.rw_csv)
    if csv_sha != rw_manifest["csv_sha256"]:
        raise IngestError(
            "Retraction Watch CSV hash does not match the committed provenance manifest"
        )
    if args.rw_csv.stat().st_size != int(rw_manifest["csv_bytes"]):
        raise IngestError("Retraction Watch CSV size does not match the provenance manifest")

    settings = Settings()
    client = EuropePmcClient.from_settings(settings)
    records = [
        record
        for record in load_retraction_watch_csv(args.rw_csv)
        if record.is_retraction and config.retraction_subject in record.subjects
    ]
    records.sort(key=lambda record: int(record.record_id) if record.record_id.isdigit() else 0)
    if args.max_sources is not None:
        if args.max_sources < 1:
            raise IngestError("--max-sources must be at least 1")
        records = records[: args.max_sources]
    rw_retractions = len(records)
    rw_linkable = sum(1 for record in records if record.original_doi or record.original_pmid)
    print(f"RW subject rows: {rw_retractions:,}; linkable: {rw_linkable:,}", flush=True)

    resolved = resolve_sources(client, records, work_dir, workers=config.metadata_workers)
    sources, sources_non_oa, sources_no_ft, sources_no_pmcid, _ = source_papers(
        records, resolved, filters=config.filters
    )
    print(f"sources: {len(sources):,}", flush=True)

    citations = fetch_citations(
        client, list(sources.values()), config, work_dir, workers=config.metadata_workers
    )
    med_ids = {
        str(identifier) for row in citations.values() for identifier in row.get("med_ids", [])
    }
    ppr_ids = {
        str(identifier) for row in citations.values() for identifier in row.get("ppr_ids", [])
    }
    citer_rows = resolve_citers(client, citations, work_dir, workers=config.metadata_workers)
    citers, citers_resolved, citers_not_found, citers_non_oa, citers_no_ft, citers_no_pmcid = (
        citer_papers(med_ids, citer_rows, filters=config.filters)
    )
    edges = build_edges(sources, citations, citers)
    source_order = {pmcid: source.order for pmcid, source in sources.items()}
    included_citers, truncated_citers = select_citers(citers, edges, source_order, config.cap)
    included_pmcids = {citer.pmcid for citer in included_citers}
    included_citers_map = {citer.pmcid: citer for citer in included_citers}
    edges = {
        citer: {source for source in targets if source in sources}
        for citer, targets in edges.items()
        if citer in included_pmcids
    }
    metadata_elapsed = time.perf_counter() - started
    print(
        f"citers eligible: {len(citers):,}; included: {len(included_citers):,}; "
        f"truncated: {len(truncated_citers):,}",
        flush=True,
    )

    sources_sorted = sorted(sources.values(), key=lambda source: source.order)
    papers = [
        CorpusPaper(
            pmcid=source.pmcid,
            pmid=source.pmid,
            doi=source.doi,
            role="source",
            rw_record_ids=source.rw_record_ids,
        )
        for source in sources_sorted
    ] + [
        CorpusPaper(
            pmcid=citer.pmcid,
            pmid=citer.pmid,
            doi=citer.doi,
            role="citer",
        )
        for citer in included_citers
        if citer.pmcid not in sources
    ]

    fulltext_dir = client.cache_dir / "fulltext"
    estimated_disk_mb = estimate_disk_mb(fulltext_dir, len(papers))
    fulltext_started = time.perf_counter()
    sizes, available, download_stats = download_full_text(
        client, papers, workers=config.fulltext_workers
    )
    fulltext_elapsed = time.perf_counter() - fulltext_started

    available_pmcids = {paper.pmcid for paper in available}
    failed_sources = {pmcid for pmcid in sources if pmcid not in available_pmcids}
    failed_citers = {pmcid for pmcid in included_citers_map if pmcid not in available_pmcids}
    sources = {pmcid: source for pmcid, source in sources.items() if pmcid in available_pmcids}
    included_citers_map = {
        pmcid: citer for pmcid, citer in included_citers_map.items() if pmcid in available_pmcids
    }
    edges = {
        citer: {source for source in targets if source in sources}
        for citer, targets in edges.items()
        if citer in included_citers_map
    }
    papers = [paper for paper in papers if paper.pmcid in available_pmcids]

    parse_started = time.perf_counter()
    contexts, parsed, parse_failures = count_contexts(client, sources, included_citers_map, edges)
    parse_elapsed = time.perf_counter() - parse_started
    cites = [
        CorpusCite(
            citer_pmcid=citer_pmcid,
            source_pmcid=source_pmcid,
            contexts=contexts.get((citer_pmcid, source_pmcid), 0),
        )
        for citer_pmcid in sorted(edges)
        for source_pmcid in sorted(edges[citer_pmcid])
    ]

    papers_csv = Path(f"{args.out_prefix}-papers.csv")
    cites_csv = Path(f"{args.out_prefix}-cites.csv")
    manifest_path = Path(f"{args.out_prefix}-manifest.json")
    report_path = Path(f"{args.out_prefix}.md")
    papers_rows = write_papers_csv(papers_csv, papers)
    cites_rows = write_cites_csv(cites_csv, cites)
    if papers_rows != len(papers) or cites_rows != len(cites):
        raise IngestError("CSV row counts diverged from in-memory rows")

    checkpoint_bytes = sum(path.stat().st_size for path in work_dir.glob("*.jsonl"))
    output_bytes = sum(path.stat().st_size for path in (papers_csv, cites_csv) if path.exists())
    cache_bytes = sum(sizes.values())
    disk_mb = (cache_bytes + checkpoint_bytes + output_bytes) / (1024 * 1024)

    papers_with_pmid = sum(1 for paper in papers if paper.pmid)
    contexts_total = sum(cite.contexts for cite in cites)
    limitations = (
        "Citer discovery uses Europe PMC's MEDLINE citations endpoint "
        "(MED/<pmid>/citations), which is PMID-based. Papers without a PMID are "
        "invisible as citers and their own citers cannot be discovered, so blast-radius "
        "recall is capped by this source.",
        "A citation context is counted only when the citing JATS reference matches a "
        "source by DOI, PMID, or normalized title plus a ±1 year window. Unresolved or "
        "ambiguous references are not counted.",
        "Full text is Europe PMC OA JATS and is stored in the untracked raw cache; the "
        "committed manifest contains identifiers and counts only.",
    )
    if truncated_citers:
        limitations += (
            f"{len(truncated_citers):,} eligible citers were truncated by the "
            f"{config.cap:,}-paper total cap; context counts are a lower bound.",
        )
    counts = CorpusCounts(
        rw_retractions_in_subject=rw_retractions,
        rw_linkable=rw_linkable,
        rw_unlinkable=rw_retractions - rw_linkable,
        sources_resolved=len(resolved),
        sources_not_found=len(records) - len(resolved),
        sources_non_oa=sources_non_oa,
        sources_without_full_text=sources_no_ft,
        sources_without_pmcid=sources_no_pmcid,
        sources_total=len(sources),
        sources_with_pmid=sum(1 for source in sources.values() if source.pmid),
        sources_without_pmid=len([source for source in sources.values() if not source.pmid]),
        citation_targets_with_pmid=sum(1 for source in sources.values() if source.pmid),
        citation_targets_without_pmid=len(
            [source for source in sources.values() if not source.pmid]
        ),
        citers_med_unique=len(med_ids),
        citers_ppr_skipped=len(ppr_ids),
        citers_resolved=citers_resolved,
        citers_not_found=citers_not_found,
        citers_non_oa=citers_non_oa,
        citers_without_full_text=citers_no_ft,
        citers_without_pmcid=citers_no_pmcid,
        citers_eligible=len(citers),
        citers_included=len(included_citers_map),
        citers_truncated=len(truncated_citers),
        papers_total=len(papers),
        papers_both_roles=len(set(sources) & set(included_citers_map)),
        papers_with_pmid=papers_with_pmid,
        papers_without_pmid=len(papers) - papers_with_pmid,
        papers_without_pmid_sources=len([source for source in sources.values() if not source.pmid]),
        papers_without_pmid_citers=len(
            [citer for citer in included_citers_map.values() if not citer.pmid]
        ),
        papers_parsed=parsed,
        parse_failures=parse_failures,
        fulltext_failures=download_stats["source"] + download_stats["citer"],
        sources_fulltext_failed=len(failed_sources),
        citers_fulltext_failed=len(failed_citers),
        contexts_total=contexts_total,
        edges_with_contexts=sum(1 for cite in cites if cite.contexts > 0),
        edges_without_contexts=sum(1 for cite in cites if cite.contexts == 0),
    )
    manifest = CorpusManifest(
        corpus_id=config.corpus_id,
        created_at=utc_now_iso(),
        config_path=str(args.config),
        config_sha256=canonical_config_sha256(config),
        sub_topic={
            "key": config.sub_topic_key,
            "subject": config.retraction_subject,
            "description": config.description,
        },
        retraction_snapshot={
            "snapshot_commit": str(rw_manifest["snapshot_commit"]),
            "snapshot_date": str(rw_manifest["snapshot_date"]),
            "csv_sha256": str(rw_manifest["csv_sha256"]),
            "csv_bytes": int(rw_manifest["csv_bytes"]),
            "licence": str(rw_manifest.get("licence", "CC0")),
            "licence_url": str(rw_manifest.get("licence_url", "")),
        },
        europe_pmc={
            "base_url": settings.europepmc_base_url,
            "citation_endpoint": "MED/<pmid>/citations",
            "retrieved_at": utc_now_iso(),
        },
        cap=config.cap,
        filters=config.filters,
        counts=counts,
        files=CorpusFiles(
            papers_csv=str(papers_csv),
            papers_sha256=sha256_file(papers_csv),
            papers_rows=papers_rows,
            cites_csv=str(cites_csv),
            cites_sha256=sha256_file(cites_csv),
            cites_rows=cites_rows,
        ),
        resources=ResourceUsage(
            wall_time_s=time.perf_counter() - started,
            metadata_wall_time_s=metadata_elapsed,
            fulltext_wall_time_s=fulltext_elapsed,
            parse_wall_time_s=parse_elapsed,
            peak_rss_mb=peak_rss_mb(),
            disk_mb=disk_mb,
            estimated_disk_mb=estimated_disk_mb,
            fulltext_cache_files=len(sizes),
            fulltext_cache_bytes=cache_bytes,
            fulltext_downloaded=download_stats["downloaded"],
            fulltext_cache_hits=download_stats["hits"],
            checkpoint_bytes=checkpoint_bytes,
        ),
        limitations=limitations,
    )
    write_manifest(manifest_path, manifest)
    report_path.write_text(
        render_report(
            config,
            manifest,
            rw_rows=int(rw_manifest.get("rows", 0)),
            report_path=report_path,
        ),
        encoding="utf-8",
        newline="\n",
    )

    print(
        f"papers={counts.papers_total:,} sources={counts.sources_total:,} "
        f"citers={counts.citers_included:,} contexts={counts.contexts_total:,}",
        flush=True,
    )
    print(f"manifest: {manifest_path}", flush=True)
    if counts.sources_total < MIN_SOURCES or counts.contexts_total < MIN_CONTEXTS:
        print(
            "BELOW CONTEXT §4 MINIMUMS: stop and propose a fallback via a new "
            "Proposed ADR; do not proceed silently.",
            file=sys.stderr,
            flush=True,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
