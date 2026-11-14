"""Regenerate the JATS golden expectations from the current parser.

Usage:
    python scripts/build_jats_golden.py
    python scripts/build_jats_golden.py --fixtures tests/fixtures/jats \
        --out tests/fixtures/jats/expected.json

The output is a regression guard. Review the diff before committing: a change
in counts or in the first-context text is a parser behaviour change.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from axion.parse.jats import paper_coverage, parse_jats_file


def build_entry(path: Path) -> dict[str, object]:
    paper = parse_jats_file(path)
    coverage = paper_coverage(paper)
    first_context = paper.citation_contexts[0] if paper.citation_contexts else None
    first_reference_with_doi = next(
        (reference for reference in paper.references if reference.doi), None
    )
    return {
        "journal": paper.journal,
        "year": paper.year,
        "sections": coverage.sections,
        "paragraphs": coverage.paragraphs,
        "references": coverage.references,
        "references_with_doi": coverage.references_with_doi,
        "references_with_pmid": coverage.references_with_pmid,
        "references_with_title": coverage.references_with_title,
        "references_with_year": coverage.references_with_year,
        "bibr_markers": coverage.bibr_markers,
        "contexts": coverage.contexts,
        "contexts_resolved": coverage.contexts_resolved,
        "warnings": list(paper.warnings),
        "top_level_sections": [section.title for section in paper.sections],
        "first_context": None
        if first_context is None
        else {
            "ref_id": first_context.ref_id,
            "section": list(first_context.section),
            "text": first_context.text,
        },
        "first_reference_with_doi": None
        if first_reference_with_doi is None
        else {
            "ref_id": first_reference_with_doi.ref_id,
            "doi": first_reference_with_doi.doi,
            "year": first_reference_with_doi.year,
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=Path("tests/fixtures/jats"))
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("tests/fixtures/jats/expected.json"),
    )
    args = parser.parse_args(argv)

    paths = sorted(args.fixtures.glob("*.xml.gz"))
    if not paths:
        print(f"no fixtures found in {args.fixtures}", file=sys.stderr)
        return 1

    expected = {path.name.split(".")[0]: build_entry(path) for path in paths}
    args.out.write_text(json.dumps(expected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {len(expected)} entries to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
