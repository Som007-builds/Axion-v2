"""Build the seeded P3-01 dependency-labeling pilot packet.

The packet is deliberately unlabeled: the agent selects and records contexts, and
the owner fills ``label``. Sampling is stratified by source paper so one heavily
cited retraction cannot dominate the pilot. No LLM calls are made.

Usage:
    python scripts/dependency_pilot.py
"""

from __future__ import annotations

import argparse
import csv
import random
import re
from collections import defaultdict
from pathlib import Path

from axion.ingest.corpus import CorpusCite, CorpusPaper, read_cites_csv, read_papers_csv
from axion.link.citations import SourceIndex, SourceTarget
from axion.parse.jats import CitationContext, JatsParseError, ParsedPaper, parse_jats_file

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAPERS = ROOT / "docs" / "reports" / "P1-corpus-papers.csv"
DEFAULT_CITES = ROOT / "docs" / "reports" / "P1-corpus-cites.csv"
DEFAULT_CACHE = ROOT / "data" / "raw" / "europepmc"
DEFAULT_OUT = ROOT / "eval" / "audit" / "dependency_pilot_v1.csv"
DEFAULT_SEED = 20261118
DEFAULT_COUNT = 20

COLUMNS = (
    "pilot_id",
    "citer_pmcid",
    "citer_title",
    "source_pmcid",
    "source_title",
    "source_pmid",
    "source_doi",
    "retraction_record_ids",
    "context_id",
    "section",
    "marker",
    "ref_label",
    "context_text",
    "paragraph_text",
    "source_claim_text",
    "label",
    "note",
    "labeler",
    "date",
    "guideline_version",
)


class PilotError(Exception):
    """Raised when the corpus bundle cannot produce a pilot packet."""


def _parse_cached(
    pmcid: str,
    cache_dir: Path,
    parsed: dict[str, ParsedPaper | None],
) -> ParsedPaper | None:
    if pmcid in parsed:
        return parsed[pmcid]
    path = cache_dir / "fulltext" / f"{pmcid}.xml"
    try:
        paper = parse_jats_file(path, paper_id=pmcid)
    except (JatsParseError, OSError):
        paper = None
    parsed[pmcid] = paper
    return paper


def _source_claim_text(paper: ParsedPaper | None) -> str:
    """Return one short abstract sentence as a source-claim proxy, not a linked claim."""
    if paper is None:
        return ""
    for section in paper.sections:
        title = (section.title or "").lower()
        if "abstract" not in title:
            continue
        for paragraph in section.paragraphs:
            text = " ".join(paragraph.text.split())
            if not text:
                continue
            for sentence in re.split(r"(?<=[.!?])\s+", text):
                candidate = sentence.strip()
                lowered = candidate.lower()
                if len(candidate) < 60:
                    continue
                if lowered.startswith(("introduction", "background", "objective", "methods")):
                    continue
                if lowered.startswith(
                    (
                        "this article has been withdrawn",
                        "the full elsevier",
                        "the publisher apologizes",
                    )
                ):
                    continue
                return candidate[:700]
    return ""


def _source_targets(
    papers: list[CorpusPaper],
    cache_dir: Path,
) -> tuple[SourceIndex, dict[str, ParsedPaper | None]]:
    parsed: dict[str, ParsedPaper | None] = {}
    targets: list[SourceTarget] = []
    for paper in papers:
        if paper.role != "source":
            continue
        source = _parse_cached(paper.pmcid, cache_dir, parsed)
        targets.append(
            SourceTarget(
                key=paper.pmcid,
                doi=paper.doi,
                pmid=paper.pmid,
                title=source.title if source else None,
                year=source.year if source else None,
            )
        )
    return SourceIndex(targets), parsed


def _candidate_contexts(
    cite: CorpusCite,
    index: SourceIndex,
    cache_dir: Path,
    parsed: dict[str, ParsedPaper | None],
    source_pmcid: str,
) -> list[tuple[ParsedPaper, CitationContext]]:
    paper = _parse_cached(cite.citer_pmcid, cache_dir, parsed)
    if paper is None:
        return []
    matched: list[tuple[ParsedPaper, CitationContext]] = []
    for context, key in index.matched_contexts(paper):
        if key != source_pmcid:
            continue
        if not context.text.strip():
            continue
        matched.append((paper, context))
    return matched


def _pick_rows(
    cites: list[CorpusCite],
    papers: list[CorpusPaper],
    index: SourceIndex,
    cache_dir: Path,
    parsed: dict[str, ParsedPaper | None],
    *,
    count: int,
    seed: int,
) -> list[dict[str, str]]:
    paper_by_pmcid = {paper.pmcid: paper for paper in papers}
    by_source: dict[str, list[CorpusCite]] = defaultdict(list)
    for cite in cites:
        if cite.contexts > 0:
            by_source[cite.source_pmcid].append(cite)

    rng = random.Random(seed)
    source_ids = sorted(by_source)
    rng.shuffle(source_ids)
    rows: list[dict[str, str]] = []
    for source_pmcid in source_ids:
        candidates = list(by_source[source_pmcid])
        rng.shuffle(candidates)
        for cite in candidates:
            matches = _candidate_contexts(cite, index, cache_dir, parsed, source_pmcid)
            if not matches:
                continue
            citer, context = rng.choice(matches)
            source_paper = paper_by_pmcid.get(source_pmcid)
            if source_paper is None:
                continue
            source_parsed = parsed.get(source_pmcid)
            rows.append(
                {
                    "pilot_id": "",
                    "citer_pmcid": citer.paper_id or cite.citer_pmcid,
                    "citer_title": citer.title or "",
                    "source_pmcid": source_pmcid,
                    "source_title": (source_parsed.title or "") if source_parsed else "",
                    "source_pmid": source_paper.pmid or "",
                    "source_doi": source_paper.doi or "",
                    "retraction_record_ids": ";".join(source_paper.rw_record_ids),
                    "context_id": context.context_id,
                    "section": " > ".join(context.section),
                    "marker": context.marker,
                    "ref_label": context.ref_label or "",
                    "context_text": context.text,
                    "paragraph_text": context.paragraph_text,
                    "source_claim_text": _source_claim_text(source_parsed),
                    "label": "",
                    "note": "",
                    "labeler": "",
                    "date": "",
                    "guideline_version": "P3-v1",
                }
            )
            break
        if len(rows) >= count:
            break
    if len(rows) < count:
        raise PilotError(f"only {len(rows)} usable contexts found; wanted {count}")
    for number, row in enumerate(rows, start=1):
        row["pilot_id"] = f"P3P-{number:03d}"
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--papers", type=Path, default=DEFAULT_PAPERS)
    parser.add_argument("--cites", type=Path, default=DEFAULT_CITES)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    args = parser.parse_args(argv)

    papers = read_papers_csv(args.papers)
    cites = read_cites_csv(args.cites)
    index, parsed = _source_targets(papers, args.cache_dir)
    rows = _pick_rows(
        cites,
        papers,
        index,
        args.cache_dir,
        parsed,
        count=args.count,
        seed=args.seed,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    sources = len({row["source_pmcid"] for row in rows})
    print(
        f"wrote {len(rows)} blank-label rows across {sources} sources to {args.out} "
        f"(seed {args.seed})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
