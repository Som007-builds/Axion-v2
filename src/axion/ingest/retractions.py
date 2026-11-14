"""Load and link the Retraction Watch database distributed by Crossref.

The database is CC0 (Crossref Metadata Retrieval page, verified 2026-11-14)
but raw CSV files are never committed. This module reads a local snapshot,
normalizes identifiers, links records to DOIs/PMIDs/PMCIDs, and emits
ID-only manifests with snapshot provenance.

Citations and full text are not this module's job: linking answers whether a
work is retracted, not how many papers cite it.
"""

from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

SOURCE = "Retraction Watch database, distributed by Crossref"
LICENCE = "CC0"
LICENCE_URL = "https://www.crossref.org/documentation/retrieve-metadata/"

_UNAVAILABLE = frozenset({"", "unavailable", "0", "n/a", "na", "none", "-", "null"})
_DOI_PREFIXES = ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:")
_DATE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})")
_REQUIRED_COLUMNS = frozenset(
    {
        "Record ID",
        "Title",
        "Journal",
        "Subject",
        "RetractionDate",
        "RetractionDOI",
        "RetractionPubMedID",
        "OriginalPaperDate",
        "OriginalPaperDOI",
        "OriginalPaperPubMedID",
        "RetractionNature",
        "Reason",
        "Paywalled",
    }
)


class RetractionDataError(Exception):
    """Raised when the Retraction Watch snapshot is malformed."""


@dataclass(frozen=True)
class RetractionRecord:
    """One normalized Retraction Watch row."""

    record_id: str
    title: str
    journal: str
    subjects: tuple[str, ...]
    nature: str
    original_doi: str | None
    original_pmid: str | None
    retraction_doi: str | None
    retraction_pmid: str | None
    retraction_date: date | None
    original_date: date | None
    reasons: tuple[str, ...]
    paywalled: bool | None

    @property
    def is_retraction(self) -> bool:
        return self.nature.casefold() == "retraction"


@dataclass(frozen=True)
class LinkMatch:
    """Retraction records matching one work, and which identifiers matched."""

    records: tuple[RetractionRecord, ...]
    matched_by: tuple[str, ...]
    conflict: bool = False

    @property
    def is_retracted(self) -> bool:
        return bool(self.records)


class RetractionIndex:
    """In-memory DOI/PMID index over a Retraction Watch snapshot."""

    def __init__(self, records: Iterable[RetractionRecord]) -> None:
        self.records: tuple[RetractionRecord, ...] = tuple(records)
        self._by_doi: dict[str, list[RetractionRecord]] = defaultdict(list)
        self._by_pmid: dict[str, list[RetractionRecord]] = defaultdict(list)
        for record in self.records:
            if record.original_doi:
                self._by_doi[record.original_doi].append(record)
            if record.original_pmid:
                self._by_pmid[record.original_pmid].append(record)

    def __len__(self) -> int:
        return len(self.records)

    @classmethod
    def from_csv(cls, path: Path) -> RetractionIndex:
        return cls(load_retraction_watch_csv(path))

    def link(self, *, doi: str | None = None, pmid: str | None = None) -> LinkMatch:
        """Link a work by DOI and/or PMID.

        A DOI and PMID that point at different retraction records are marked
        as a conflict instead of being silently merged.
        """
        normalized_doi = normalize_doi(doi) if doi else None
        normalized_pmid = normalize_pmid(pmid) if pmid else None
        matched: dict[str, RetractionRecord] = {}
        matched_by: list[str] = []
        doi_records = self._by_doi.get(normalized_doi, []) if normalized_doi else []
        pmid_records = self._by_pmid.get(normalized_pmid, []) if normalized_pmid else []
        if doi_records:
            matched_by.append("doi")
        if pmid_records:
            matched_by.append("pmid")
        for record in (*doi_records, *pmid_records):
            matched[record.record_id] = record
        conflict = bool(
            normalized_doi
            and normalized_pmid
            and doi_records
            and pmid_records
            and {record.record_id for record in doi_records}.isdisjoint(
                record.record_id for record in pmid_records
            )
        )
        ordered = tuple(sorted(matched.values(), key=lambda record: record.record_id))
        return LinkMatch(records=ordered, matched_by=tuple(matched_by), conflict=conflict)

    def link_pmcid(
        self,
        pmcid: str,
        lookup: Callable[[str], tuple[str | None, str | None]],
    ) -> LinkMatch:
        """Link a PMCID by resolving it to a DOI/PMID pair first.

        The Retraction Watch snapshot has no PMCID column, so the caller
        supplies the Europe PMC resolution (``lookup`` returns ``(doi, pmid)``).
        """
        doi, pmid = lookup(pmcid)
        if not doi and not pmid:
            return LinkMatch(records=(), matched_by=())
        return self.link(doi=doi, pmid=pmid)


def normalize_doi(value: str | None) -> str | None:
    """Normalize a DOI, treating Retraction Watch's blanks as missing."""
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in _UNAVAILABLE:
        return None
    for prefix in _DOI_PREFIXES:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
    return normalized or None


def normalize_pmid(value: str | None) -> str | None:
    """Return a digits-only PMID, or ``None`` for blank/0/unavailable."""
    if value is None:
        return None
    normalized = value.strip()
    if normalized.lower() in _UNAVAILABLE:
        return None
    return normalized if normalized.isdigit() else None


def _split_list(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(part.strip() for part in value.split(";") if part.strip())


def _parse_date(value: str | None) -> date | None:
    match = _DATE.match((value or "").strip())
    if not match:
        return None
    month, day, year = (int(group) for group in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_paywalled(value: str | None) -> bool | None:
    normalized = (value or "").strip().casefold()
    if normalized == "yes":
        return True
    if normalized == "no":
        return False
    return None


def _record_from_row(row: dict[str, str]) -> RetractionRecord:
    return RetractionRecord(
        record_id=(row.get("Record ID") or "").strip(),
        title=(row.get("Title") or "").strip(),
        journal=(row.get("Journal") or "").strip(),
        subjects=_split_list(row.get("Subject")),
        nature=(row.get("RetractionNature") or "").strip(),
        original_doi=normalize_doi(row.get("OriginalPaperDOI")),
        original_pmid=normalize_pmid(row.get("OriginalPaperPubMedID")),
        retraction_doi=normalize_doi(row.get("RetractionDOI")),
        retraction_pmid=normalize_pmid(row.get("RetractionPubMedID")),
        retraction_date=_parse_date(row.get("RetractionDate")),
        original_date=_parse_date(row.get("OriginalPaperDate")),
        reasons=_split_list(row.get("Reason")),
        paywalled=_parse_paywalled(row.get("Paywalled")),
    )


def iter_retraction_watch_csv(path: Path) -> Iterator[RetractionRecord]:
    """Stream normalized rows from a Retraction Watch CSV snapshot."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or ())
        missing = sorted(_REQUIRED_COLUMNS - columns)
        if missing:
            raise RetractionDataError(
                f"{path}: missing Retraction Watch columns: {', '.join(missing)}"
            )
        for line_number, row in enumerate(reader, start=2):
            if not (row.get("Record ID") or "").strip():
                continue
            try:
                yield _record_from_row(row)
            except (KeyError, TypeError) as exc:
                raise RetractionDataError(f"{path}:{line_number}: {exc}") from exc


def load_retraction_watch_csv(path: Path) -> list[RetractionRecord]:
    """Load a snapshot, rejecting duplicate record ids."""
    records: list[RetractionRecord] = []
    seen: set[str] = set()
    for record in iter_retraction_watch_csv(path):
        if record.record_id in seen:
            raise RetractionDataError(f"{path}: duplicate Record ID {record.record_id!r}")
        seen.add(record.record_id)
        records.append(record)
    return records


def build_manifest(
    records: Iterable[RetractionRecord],
    *,
    snapshot_commit: str,
    snapshot_date: str,
    csv_sha256: str,
    csv_bytes: int,
    record_ids: Iterable[str] | None = None,
) -> dict[str, object]:
    """Build an ID-only provenance manifest (never raw rows)."""
    materialized = list(records)
    natures: dict[str, int] = defaultdict(int)
    for record in materialized:
        natures[record.nature] += 1
    manifest: dict[str, object] = {
        "schema_version": 1,
        "source": SOURCE,
        "licence": LICENCE,
        "licence_url": LICENCE_URL,
        "snapshot_commit": snapshot_commit,
        "snapshot_date": snapshot_date,
        "csv_sha256": csv_sha256,
        "csv_bytes": csv_bytes,
        "rows": len(materialized),
        "natures": dict(sorted(natures.items())),
        "with_original_doi": sum(1 for record in materialized if record.original_doi),
        "with_original_pmid": sum(1 for record in materialized if record.original_pmid),
        "with_retraction_doi": sum(1 for record in materialized if record.retraction_doi),
    }
    if record_ids is not None:
        manifest["record_ids"] = sorted(set(record_ids))
    return manifest


def write_manifest(path: Path, manifest: dict[str, object]) -> None:
    """Write a manifest deterministically (sorted keys, trailing newline)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
