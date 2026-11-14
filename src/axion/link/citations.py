"""Match citation contexts to known source papers.

A citing paper's JATS reference list is the local evidence for which source a
marker points at. References are matched by DOI, then PMID, then a normalized
title plus a ±1 year window; a DOI embedded in the citation text is a final
fallback. This keeps blast-radius linking deterministic and independent of how
complete a publisher's reference metadata is.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol

from axion.parse.jats import CitationContext, ParsedPaper, Reference

_TITLE_STRIP = re.compile(r"[^a-z0-9]+")
_DOI_IN_TEXT = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)


class CitationTarget(Protocol):
    """Minimal source-paper fields needed for reference matching."""

    doi: str | None
    pmid: str | None
    title: str | None
    year: int | None


@dataclass(frozen=True)
class SourceTarget:
    """One source paper keyed by its manifest identifier."""

    key: str
    doi: str | None
    pmid: str | None
    title: str | None
    year: int | None


def normalize_title(value: str | None) -> str:
    """Lowercase and strip punctuation so publisher title variants compare."""
    if not value:
        return ""
    return _TITLE_STRIP.sub(" ", value.lower()).strip()


def _normalize_doi(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "https://dx.doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :].strip()
    return normalized or None


def reference_matches(reference: Reference, target: CitationTarget) -> bool:
    """True when a parsed reference points at ``target``."""
    target_doi = _normalize_doi(target.doi)
    target_pmid = (target.pmid or "").strip() or None

    reference_doi = _normalize_doi(reference.doi)
    if target_doi and reference_doi and reference_doi == target_doi:
        return True
    if target_pmid and reference.pmid and reference.pmid.strip() == target_pmid:
        return True
    if reference_doi or reference.pmid:
        return False

    if reference.citation_text and target_doi:
        for candidate in _DOI_IN_TEXT.findall(reference.citation_text):
            if _normalize_doi(candidate.rstrip(".,;)")) == target_doi:
                return True

    source_title = normalize_title(target.title)
    reference_title = normalize_title(reference.title)
    if not source_title or not reference_title or source_title != reference_title:
        return False
    return not (target.year and reference.year and abs(target.year - reference.year) > 1)


class SourceIndex:
    """Lookup structure for matching references to many source papers."""

    def __init__(self, targets: Iterable[SourceTarget]) -> None:
        self._by_doi: dict[str, list[str]] = defaultdict(list)
        self._by_pmid: dict[str, list[str]] = defaultdict(list)
        self._by_title: dict[str, list[str]] = defaultdict(list)
        self._targets: dict[str, SourceTarget] = {}
        for target in targets:
            self._targets[target.key] = target
            doi = _normalize_doi(target.doi)
            if doi:
                self._by_doi[doi].append(target.key)
            if target.pmid:
                self._by_pmid[target.pmid].append(target.key)
            title = normalize_title(target.title)
            if title:
                self._by_title[title].append(target.key)

    def __len__(self) -> int:
        return len(self._targets)

    def match(self, reference: Reference) -> str | None:
        """Return one source key for a reference, or ``None`` when ambiguous."""
        reference_doi = _normalize_doi(reference.doi)
        if reference_doi and reference_doi in self._by_doi:
            keys = self._by_doi[reference_doi]
            return keys[0] if len(keys) == 1 else None
        if reference.pmid:
            keys = self._by_pmid.get(reference.pmid.strip(), [])
            if keys:
                return keys[0] if len(keys) == 1 else None
        if reference_doi or reference.pmid:
            return None

        if reference.citation_text:
            for candidate in _DOI_IN_TEXT.findall(reference.citation_text):
                doi = _normalize_doi(candidate.rstrip(".,;)"))
                keys = self._by_doi.get(doi or "", [])
                if keys:
                    return keys[0] if len(keys) == 1 else None

        title = normalize_title(reference.title)
        if not title:
            return None
        candidates = []
        for key in self._by_title.get(title, []):
            target_year = self._targets[key].year
            if target_year and reference.year and abs(target_year - reference.year) > 1:
                continue
            candidates.append(key)
        return candidates[0] if len(candidates) == 1 else None

    def matched_contexts(self, paper: ParsedPaper) -> list[tuple[CitationContext, str]]:
        """Return each context that points at a known source, with its key."""
        references: Mapping[str, Reference] = {
            reference.ref_id: reference for reference in paper.references
        }
        matched: list[tuple[CitationContext, str]] = []
        for context in paper.citation_contexts:
            reference = references.get(context.ref_id)
            if reference is None:
                continue
            key = self.match(reference)
            if key is not None:
                matched.append((context, key))
        return matched

    def count_contexts(self, paper: ParsedPaper) -> dict[str, int]:
        """Count context markers per matched source key."""
        counts: dict[str, int] = defaultdict(int)
        for _, key in self.matched_contexts(paper):
            counts[key] += 1
        return dict(counts)


def contexts_for_target(paper: ParsedPaper, target: CitationTarget) -> int:
    """Convenience wrapper for one target (used by the feasibility spike)."""
    matching = {
        reference.ref_id for reference in paper.references if reference_matches(reference, target)
    }
    return sum(1 for context in paper.citation_contexts if context.ref_id in matching)


__all__ = [
    "CitationTarget",
    "SourceIndex",
    "SourceTarget",
    "contexts_for_target",
    "normalize_title",
    "reference_matches",
]
