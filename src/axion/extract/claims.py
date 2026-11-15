"""Claim schema, baseline section selection, and silver-label provenance.

Silver labels here are **candidate** machine labels. They train students and
never evaluate them; gold labels are human-audited and live separately.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from axion.parse.jats import Paragraph, ParsedPaper

PROMPT_VERSION = "claim-extraction-v1"

# Owner baseline definition (2026-11-14): every parsed section except these.
EXCLUDED_SECTION_PATTERNS: tuple[str, ...] = (
    "references",
    "reference list",
    "bibliography",
    "acknowledg",
    "funding",
    "financial support",
    "conflict of interest",
    "conflicts of interest",
    "competing interest",
    "competing interests",
    "supplementary",
    "supporting information",
)

ClaimType = Literal[
    "association",
    "effect",
    "prevalence",
    "diagnostic",
    "mechanism",
    "limitation",
    "other",
]
Direction = Literal["increase", "decrease", "no_difference", "mixed"]


class Claim(BaseModel):
    """One extracted assertion with its section and verbatim evidence span."""

    model_config = ConfigDict(extra="forbid")

    claim_text: str = Field(min_length=1)
    section: str = Field(min_length=1)
    evidence_span: str = Field(min_length=1)
    claim_type: ClaimType = "other"
    population: str | None = None
    intervention: str | None = None
    outcome: str | None = None
    direction: Direction | None = None


class ClaimExtraction(BaseModel):
    """The structured response expected from the teacher model."""

    model_config = ConfigDict(extra="forbid")

    claims: list[Claim] = Field(default_factory=list)


class ClaimFailure(BaseModel):
    """A rejected claim; kept so failures are recorded, never dropped."""

    model_config = ConfigDict(extra="forbid")

    paper_id: str
    claim_index: int
    reason: str
    detail: str
    claim_text: str | None = None


class SilverClaim(BaseModel):
    """A claim plus the provenance required for a silver-label manifest."""

    model_config = ConfigDict(extra="forbid")

    label_kind: Literal["silver"] = "silver"
    not_gold: Literal[True] = True
    run_id: str
    paper_id: str
    pmcid: str | None = None
    teacher_model: str
    prompt_version: str
    stage: Literal["teacher_label"] = "teacher_label"
    claim_index: int
    claim: Claim
    created_at: str


class SilverManifest(BaseModel):
    """ID/provenance-only manifest for one extraction run."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    run_id: str
    created_at: str
    label_kind: Literal["silver"] = "silver"
    not_gold: Literal[True] = True
    usable_for: tuple[str, ...] = ("student_training",)
    forbidden_for: tuple[str, ...] = ("evaluation", "reported_quality")
    teacher_model: str
    prompt_version: str
    seed: int
    sample_size: int
    papers_processed: int
    claims: int
    failures: int
    corpus_manifest_sha256: str
    papers_file: str
    papers_sha256: str
    failures_file: str


class CandidateClaim(BaseModel):
    """One silver claim in the audit-tool input shape.

    This is still a **silver candidate**, never a gold label. The context fields
    contain the paragraph before and after the evidence span so the audit tool
    can show a blind human the surrounding prose.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    paper_id: str
    claim_text: str
    evidence_span: str
    section: str
    paper_title: str = ""
    context_before: str = ""
    context_after: str = ""


class BaselineSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    path: tuple[str, ...]
    text: str


class BaselineDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    paper_id: str
    paper_title: str = ""
    sections: tuple[BaselineSection, ...]

    @property
    def text(self) -> str:
        blocks = []
        for section in self.sections:
            blocks.append(f"## {section.label}\n{section.text}")
        return "\n\n".join(blocks)


def _is_excluded(path: Sequence[str], title: str | None) -> bool:
    haystack = " ".join((*path, title or "")).casefold()
    return any(pattern in haystack for pattern in EXCLUDED_SECTION_PATTERNS)


def _paragraphs_for_section(parsed: ParsedPaper, path: tuple[str, ...]) -> list[Paragraph]:
    return [
        paragraph for paragraph in parsed.paragraphs if paragraph.section == path and paragraph.text
    ]


def _walk_sections(
    parsed: ParsedPaper,
    section: object,
    *,
    prefix: tuple[str, ...] = (),
) -> Iterable[BaselineSection]:
    # ``section`` is a jats.Section; typed duck-wise to keep this module small.
    title = getattr(section, "title", None)
    path = tuple(getattr(section, "path", prefix or (title or "",)))
    label = title or (path[-1] if path else "Body")
    if _is_excluded(path, title):
        return
    paragraphs = _paragraphs_for_section(parsed, path)
    if paragraphs:
        yield BaselineSection(
            label=label,
            path=path,
            text="\n".join(paragraph.text for paragraph in paragraphs),
        )
    for child in getattr(section, "subsections", ()):
        yield from _walk_sections(parsed, child, prefix=path)


def build_baseline_document(parsed: ParsedPaper) -> BaselineDocument:
    """Collect all parsed sections except the owner's exclusion list."""
    sections: list[BaselineSection] = []
    for section in parsed.sections:
        sections.extend(_walk_sections(parsed, section))
    # Fall back to paragraph section paths the tree walk missed.
    seen = {section.path for section in sections}
    by_path: dict[tuple[str, ...], list[str]] = {}
    for paragraph in parsed.paragraphs:
        if paragraph.text and paragraph.section not in seen:
            by_path.setdefault(paragraph.section, []).append(paragraph.text)
    for path, texts in by_path.items():
        if _is_excluded(path, None):
            continue
        sections.append(
            BaselineSection(label=path[-1] if path else "Body", path=path, text="\n".join(texts))
        )
    return BaselineDocument(
        paper_id=parsed.pmcid or parsed.paper_id or "",
        paper_title=parsed.title or "",
        sections=tuple(sections),
    )


def verify_claims(
    extraction: ClaimExtraction, document: BaselineDocument, *, paper_id: str
) -> tuple[list[Claim], list[ClaimFailure]]:
    """Keep only claims whose section exists and whose span is verbatim there."""
    by_label = {section.label.casefold(): section for section in document.sections}
    valid: list[Claim] = []
    failures: list[ClaimFailure] = []
    for index, claim in enumerate(extraction.claims):
        section = by_label.get(claim.section.casefold())
        if section is None:
            failures.append(
                ClaimFailure(
                    paper_id=paper_id,
                    claim_index=index,
                    reason="unknown_section",
                    detail=f"section {claim.section!r} is not in the baseline document",
                    claim_text=claim.claim_text,
                )
            )
            continue
        if claim.evidence_span not in section.text:
            failures.append(
                ClaimFailure(
                    paper_id=paper_id,
                    claim_index=index,
                    reason="evidence_span_not_verbatim",
                    detail=f"span not found verbatim in section {section.label!r}",
                    claim_text=claim.claim_text,
                )
            )
            continue
        valid.append(claim)
    return valid, failures


def audit_context(
    document: BaselineDocument, *, section_label: str, evidence_span: str
) -> tuple[str, str]:
    """Return the paragraph window containing a verbatim span.

    ``before`` is the previous paragraph plus the full paragraph containing the
    span; ``after`` is the next paragraph. The evidence span therefore appears
    verbatim inside ``before``, so a CSV-only viewer can both highlight it and
    flag a missing span without needing the source XML.
    """
    by_label = {section.label.casefold(): section for section in document.sections}
    section = by_label.get(section_label.casefold())
    if section is None:
        return "", ""
    paragraphs = section.text.split("\n")
    for index, paragraph in enumerate(paragraphs):
        if evidence_span not in paragraph:
            continue
        before_parts = paragraphs[max(0, index - 1) : index + 1]
        after_parts = paragraphs[index + 1 : index + 2]
        return "\n".join(before_parts), "\n".join(after_parts)

    # A span may cross a paragraph boundary; fall back to a section window.
    position = section.text.find(evidence_span)
    if position < 0:
        return "", ""
    before_text = section.text[: position + len(evidence_span)]
    after_text = section.text[position + len(evidence_span) :]
    before_break = before_text.rfind("\n\n")
    after_break = after_text.find("\n\n")
    if before_break >= 0:
        before_text = before_text[before_break + 2 :]
    if after_break >= 0:
        after_text = after_text[:after_break]
    return before_text, after_text


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _jsonl_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict):
            rows.append(raw)
    return rows


def _as_int(value: object, default: int = -1) -> int:
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return default


def append_silver_claims(path: Path, claims: Sequence[SilverClaim]) -> int:
    """Append new claims and fsync, so an interrupted run keeps finished papers.

    Re-appending the same ``(paper_id, claim_index)`` pair is a no-op. That makes
    a resumed run idempotent even if it stopped between two appends.
    """
    if not claims:
        return 0
    existing = {
        (str(row.get("paper_id")), _as_int(row.get("claim_index"))) for row in _jsonl_rows(path)
    }
    fresh = [claim for claim in claims if (claim.paper_id, claim.claim_index) not in existing]
    if not fresh:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for claim in fresh:
            handle.write(json.dumps(claim.model_dump(mode="json"), sort_keys=True))
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return len(fresh)


def append_candidate_claims(path: Path, claims: Sequence[CandidateClaim]) -> int:
    """Append audit-tool candidates once each, keyed by ``claim_id``."""
    if not claims:
        return 0
    existing = {str(row.get("claim_id")) for row in _jsonl_rows(path)}
    fresh = [claim for claim in claims if claim.claim_id not in existing]
    if not fresh:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for claim in fresh:
            handle.write(json.dumps(claim.model_dump(mode="json"), sort_keys=True))
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return len(fresh)


def append_processed_paper(path: Path, *, paper_id: str, claims: int, failures: int) -> None:
    """Mark a paper complete even when extraction returned zero claims."""
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"paper_id": paper_id, "claims": claims, "failures": failures, "at": utc_now_iso()}
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, sort_keys=True))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_processed_paper_ids(path: Path) -> set[str]:
    return {
        str(row["paper_id"])
        for row in _jsonl_rows(path)
        if isinstance(row.get("paper_id"), str) and row["paper_id"]
    }


def read_silver_paper_ids(path: Path) -> set[str]:
    """Paper ids already written by a previous run, for resume."""
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        paper_id = row.get("paper_id")
        if isinstance(paper_id, str):
            ids.add(paper_id)
    return ids


def write_failures(path: Path, failures: Sequence[ClaimFailure]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for failure in failures:
            handle.write(json.dumps(failure.model_dump(mode="json"), sort_keys=True))
            handle.write("\n")
    os.replace(temporary, path)


def write_silver_manifest(path: Path, manifest: SilverManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


__all__ = [
    "EXCLUDED_SECTION_PATTERNS",
    "PROMPT_VERSION",
    "BaselineDocument",
    "BaselineSection",
    "CandidateClaim",
    "Claim",
    "ClaimExtraction",
    "ClaimFailure",
    "SilverClaim",
    "SilverManifest",
    "append_candidate_claims",
    "append_processed_paper",
    "append_silver_claims",
    "audit_context",
    "build_baseline_document",
    "read_processed_paper_ids",
    "read_silver_paper_ids",
    "utc_now_iso",
    "verify_claims",
    "write_failures",
    "write_silver_manifest",
]
