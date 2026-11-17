"""Tests for configurable section targeting (P2-02 lever)."""

from __future__ import annotations

from pathlib import Path

import pytest

from axion.extract.claims import BaselineDocument, BaselineSection
from axion.extract.sections import (
    DEFAULT_SECTION_SETS_PATH,
    SectionSetError,
    load_section_sets,
    matches_section,
    restrict_document,
    section_sets_sha256,
)


def _section(label: str, text: str = "Text.") -> BaselineSection:
    return BaselineSection(label=label, path=(label,), text=text)


def _document(*labels: str) -> BaselineDocument:
    return BaselineDocument(
        paper_id="PMC1",
        paper_title="A paper",
        sections=tuple(_section(label) for label in labels),
    )


def test_all_set_is_the_frozen_baseline() -> None:
    table = load_section_sets()
    all_set = table.require("all")
    assert all_set.include == ()
    assert section_sets_sha256() == section_sets_sha256(DEFAULT_SECTION_SETS_PATH)


def test_core_set_selects_abstract_results_conclusion() -> None:
    core = load_section_sets().require("core")
    document = _document("Abstract", "1. Introduction", "2. Methods", "3. Results")
    restricted = restrict_document(document, core.include)
    assert [section.label for section in restricted.sections] == ["Abstract", "3. Results"]


def test_empty_include_keeps_every_section() -> None:
    document = _document("Abstract", "Methods")
    assert restrict_document(document, ()).sections == document.sections


def test_restriction_is_case_insensitive_and_path_aware() -> None:
    nested = BaselineSection(label="Sub", path=("Results", "Sub"), text="Text.")
    assert matches_section(nested, ("results",))
    assert not matches_section(_section("Methods"), ("result",))


def test_restriction_can_empty_a_document() -> None:
    restricted = restrict_document(_document("Methods"), ("abstract",))
    assert restricted.sections == ()


def test_unknown_set_is_rejected() -> None:
    with pytest.raises(SectionSetError, match="unknown section set"):
        load_section_sets().require("nope")


def test_missing_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(SectionSetError, match="missing section-set file"):
        load_section_sets(tmp_path / "absent.yaml")


def test_table_without_all_set_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "sets.yaml"
    path.write_text(
        "version: 1\nsets:\n  only:\n    description: x\n    include: [abstract]\n",
        encoding="utf-8",
    )
    with pytest.raises(SectionSetError, match="must define an 'all' set"):
        load_section_sets(path)
