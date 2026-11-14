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


class BaselineSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    path: tuple[str, ...]
    text: str


class BaselineDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    paper_id: str
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
        paper_id=parsed.pmcid or parsed.paper_id or "", sections=tuple(sections)
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


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def append_silver_claims(path: Path, claims: Sequence[SilverClaim]) -> int:
    """Append claims and fsync, so an interrupted run keeps finished papers."""
    if not claims:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for claim in claims:
            handle.write(json.dumps(claim.model_dump(mode="json"), sort_keys=True))
            handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return len(claims)


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
    "Claim",
    "ClaimExtraction",
    "ClaimFailure",
    "SilverClaim",
    "SilverManifest",
    "append_silver_claims",
    "build_baseline_document",
    "read_silver_paper_ids",
    "utc_now_iso",
    "verify_claims",
    "write_failures",
    "write_silver_manifest",
]
