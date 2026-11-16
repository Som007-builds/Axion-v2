"""Configurable section targeting: the P2-02 ablation lever.

The P1 baseline sends every parsed section that is not on the owner's exclusion
list. Section targeting keeps only sections whose title or path matches a named
set, which shortens the prompt (cost) and drops sections that never produced a
gold-scored claim (precision).

The filter runs before the prompt is rendered. That matters: a claim naming a
section the model never saw is an ``unknown_section`` failure in
``verify_claims``, so the lever needs no second enforcement path.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from axion.extract.claims import BaselineDocument, BaselineSection

DEFAULT_SECTION_SETS_PATH = Path(__file__).resolve().parents[1] / "config" / "section_sets.yaml"


class SectionSetError(Exception):
    """Raised when the section-set file cannot be loaded or a name is unknown."""


class SectionSet(BaseModel):
    """One named, configurable section selection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    # Filled in from the mapping key by ``SectionSetTable.require``.
    name: str = ""
    description: str = ""
    include: tuple[str, ...] = ()


class SectionSetTable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    sets: dict[str, SectionSet]

    def require(self, name: str) -> SectionSet:
        try:
            section_set = self.sets[name]
        except KeyError:
            available = ", ".join(sorted(self.sets)) or "none"
            raise SectionSetError(f"unknown section set {name!r}; available: {available}") from None
        return section_set.model_copy(update={"name": name})


def load_section_sets(path: Path = DEFAULT_SECTION_SETS_PATH) -> SectionSetTable:
    """Load and validate the named section sets."""
    if not path.exists():
        raise SectionSetError(f"missing section-set file: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - malformed owner config
        raise SectionSetError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise SectionSetError(f"{path} must contain a mapping with a 'sets' key")
    try:
        table = SectionSetTable.model_validate(raw)
    except ValidationError as exc:
        raise SectionSetError(f"invalid section-set file {path}: {exc}") from exc
    if "all" not in table.sets:
        raise SectionSetError(f"{path} must define an 'all' set (the frozen baseline)")
    return table


def section_sets_sha256(path: Path = DEFAULT_SECTION_SETS_PATH) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def matches_section(section: BaselineSection, include: tuple[str, ...]) -> bool:
    """True when the section belongs to the set (an empty set matches everything)."""
    if not include:
        return True
    haystack = " ".join((*section.path, section.label)).casefold()
    return any(pattern.casefold() in haystack for pattern in include)


def restrict_document(document: BaselineDocument, include: tuple[str, ...]) -> BaselineDocument:
    """Keep only the sections matching ``include``; an empty set keeps all."""
    if not include:
        return document
    kept = tuple(section for section in document.sections if matches_section(section, include))
    return document.model_copy(update={"sections": kept})
