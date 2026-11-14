"""Corpus definition models and deterministic, ID-only manifest output.

The P1 corpus is configuration, not code: a sub-topic is a YAML file naming a
Retraction Watch subject and the ingestion cap. The manifest deliberately
contains identifiers only (PMCID, PMID, DOI, record IDs) plus counts; full
text lives in the untracked raw cache and is never committed.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class CorpusError(Exception):
    """Raised when a corpus definition or manifest operation is invalid."""


class CorpusConfigError(CorpusError):
    """Raised when a corpus configuration file is malformed."""


class CorpusStateError(CorpusError):
    """Raised when a resumable checkpoint is corrupt."""


class CorpusFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    open_access: bool = True
    full_text: bool = True
    require_pmcid: bool = True


class CorpusConfig(BaseModel):
    """A sub-topic definition; adding a sub-topic is a config-only change."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    corpus_id: str = Field(min_length=1)
    sub_topic_key: str = Field(min_length=1)
    description: str = Field(min_length=1)
    retraction_subject: str = Field(min_length=1)
    cap: int = Field(default=5_000, ge=1, le=50_000)
    citation_page_size: int = Field(default=1_000, ge=1, le=1_000)
    citation_max_pages: int = Field(default=20, ge=1)
    metadata_workers: int = Field(default=8, ge=1, le=32)
    fulltext_workers: int = Field(default=12, ge=1, le=32)
    filters: CorpusFilters = Field(default_factory=CorpusFilters)


def load_corpus_config(path: Path) -> CorpusConfig:
    """Load and validate a corpus YAML file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CorpusConfigError(f"corpus config not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise CorpusConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise CorpusConfigError(f"corpus config must be a mapping: {path}")
    try:
        return CorpusConfig.model_validate(raw)
    except ValidationError as exc:
        raise CorpusConfigError(f"invalid corpus config {path}: {exc}") from exc


def canonical_config_sha256(config: CorpusConfig) -> str:
    """Stable hash of the effective config, for manifest provenance."""
    payload = json.dumps(
        config.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class CorpusPaper(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    pmcid: str
    pmid: str | None = None
    doi: str | None = None
    role: Literal["source", "citer"]
    rw_record_ids: tuple[str, ...] = ()


class CorpusCite(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    citer_pmcid: str
    source_pmcid: str
    contexts: int = Field(ge=0)


class CorpusFiles(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    papers_csv: str
    papers_sha256: str
    papers_rows: int
    cites_csv: str
    cites_sha256: str
    cites_rows: int


class CorpusCounts(BaseModel):
    """Exact counts; every field comes from the ingestion run, not a sample."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    rw_retractions_in_subject: int
    rw_linkable: int
    rw_unlinkable: int
    sources_resolved: int
    sources_not_found: int
    sources_non_oa: int
    sources_without_full_text: int
    sources_without_pmcid: int
    sources_total: int
    sources_with_pmid: int
    sources_without_pmid: int
    citation_targets_with_pmid: int
    citation_targets_without_pmid: int
    citers_med_unique: int
    citers_ppr_skipped: int
    citers_resolved: int
    citers_not_found: int
    citers_non_oa: int
    citers_without_full_text: int
    citers_without_pmcid: int
    citers_eligible: int
    citers_included: int
    citers_truncated: int
    papers_total: int
    papers_both_roles: int
    papers_with_pmid: int
    papers_without_pmid: int
    papers_without_pmid_sources: int
    papers_without_pmid_citers: int
    papers_parsed: int
    parse_failures: int
    fulltext_failures: int
    sources_fulltext_failed: int
    citers_fulltext_failed: int
    contexts_total: int
    edges_with_contexts: int
    edges_without_contexts: int


class ResourceUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    wall_time_s: float
    metadata_wall_time_s: float
    fulltext_wall_time_s: float
    parse_wall_time_s: float
    peak_rss_mb: float
    disk_mb: float
    estimated_disk_mb: float
    fulltext_cache_files: int
    fulltext_cache_bytes: int
    fulltext_downloaded: int
    fulltext_cache_hits: int
    checkpoint_bytes: int


class CorpusManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    corpus_id: str
    created_at: str
    config_path: str
    config_sha256: str
    sub_topic: dict[str, str]
    retraction_snapshot: dict[str, str | int]
    europe_pmc: dict[str, str]
    cap: int
    filters: CorpusFilters
    counts: CorpusCounts
    files: CorpusFiles
    resources: ResourceUsage
    limitations: tuple[str, ...] = ()


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def write_papers_csv(path: Path, papers: Iterable[CorpusPaper]) -> int:
    """Write the ID-only paper list in deterministic order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    rows = 0
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["pmcid", "pmid", "doi", "role", "rw_record_ids"])
        for paper in papers:
            writer.writerow(
                [
                    paper.pmcid,
                    paper.pmid or "",
                    paper.doi or "",
                    paper.role,
                    ";".join(paper.rw_record_ids),
                ]
            )
            rows += 1
    os.replace(temporary, path)
    return rows


def write_cites_csv(path: Path, cites: Iterable[CorpusCite]) -> int:
    """Write the ID-only citer -> source edge list in deterministic order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    rows = 0
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["citer_pmcid", "source_pmcid", "contexts"])
        for cite in cites:
            writer.writerow([cite.citer_pmcid, cite.source_pmcid, cite.contexts])
            rows += 1
    os.replace(temporary, path)
    return rows


def write_manifest(path: Path, manifest: CorpusManifest) -> None:
    """Write a deterministic, human-readable manifest."""
    payload = json.dumps(
        manifest.model_dump(mode="json"), indent=2, sort_keys=True, ensure_ascii=False
    )
    _atomic_write_text(path, payload + "\n")


def read_manifest(path: Path) -> CorpusManifest:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CorpusError(f"manifest not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CorpusError(f"invalid manifest JSON {path}: {exc}") from exc
    try:
        return CorpusManifest.model_validate(raw)
    except ValidationError as exc:
        raise CorpusError(f"invalid manifest {path}: {exc}") from exc


def read_papers_csv(path: Path) -> list[CorpusPaper]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"pmcid", "pmid", "doi", "role", "rw_record_ids"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise CorpusError(f"papers CSV missing columns: {path}")
        return [
            CorpusPaper(
                pmcid=row["pmcid"],
                pmid=row["pmid"] or None,
                doi=row["doi"] or None,
                role=cast(Literal["source", "citer"], row["role"]),
                rw_record_ids=tuple(part for part in row["rw_record_ids"].split(";") if part),
            )
            for row in reader
        ]


def read_cites_csv(path: Path) -> list[CorpusCite]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"citer_pmcid", "source_pmcid", "contexts"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise CorpusError(f"cites CSV missing columns: {path}")
        return [
            CorpusCite(
                citer_pmcid=row["citer_pmcid"],
                source_pmcid=row["source_pmcid"],
                contexts=int(row["contexts"]),
            )
            for row in reader
        ]


class JsonlCheckpoint:
    """Append-only JSONL state that survives a crash or sleep.

    A crash can leave at most one partial trailing line because every batch is
    flushed and fsynced. The reader ignores that trailing line; damage anywhere
    else is an error rather than silent data loss.
    """

    def __init__(self, path: Path, key: str) -> None:
        self.path = path
        self.key = key

    def load(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        lines = self.path.read_text(encoding="utf-8").splitlines()
        rows: dict[str, dict[str, object]] = {}
        for index, line in enumerate(lines):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                if index == len(lines) - 1:
                    break
                raise CorpusStateError(
                    f"corrupt checkpoint {self.path} at line {index + 1}"
                ) from exc
            if not isinstance(raw, dict):
                raise CorpusStateError(f"checkpoint {self.path} line {index + 1} is not an object")
            value = raw.get(self.key)
            if not isinstance(value, str) or not value:
                raise CorpusStateError(
                    f"checkpoint {self.path} line {index + 1} lacks {self.key!r}"
                )
            rows[value] = raw
        return rows

    def append(self, rows: Iterable[Mapping[str, object]]) -> None:
        materialized = list(rows)
        if not materialized:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            for row in materialized:
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())


def source_citation_targets(
    papers: Iterable[CorpusPaper],
) -> tuple[list[CorpusPaper], list[CorpusPaper]]:
    """Split sources into citation-queryable (PMID) and invisible (no PMID)."""
    sources = [paper for paper in papers if paper.role == "source"]
    with_pmid = [paper for paper in sources if paper.pmid]
    without_pmid = [paper for paper in sources if not paper.pmid]
    return with_pmid, without_pmid


__all__ = [
    "CorpusCite",
    "CorpusConfig",
    "CorpusConfigError",
    "CorpusCounts",
    "CorpusError",
    "CorpusFiles",
    "CorpusFilters",
    "CorpusManifest",
    "CorpusPaper",
    "CorpusStateError",
    "JsonlCheckpoint",
    "ResourceUsage",
    "canonical_config_sha256",
    "load_corpus_config",
    "read_cites_csv",
    "read_manifest",
    "read_papers_csv",
    "sha256_file",
    "source_citation_targets",
    "utc_now_iso",
    "write_cites_csv",
    "write_manifest",
    "write_papers_csv",
]
