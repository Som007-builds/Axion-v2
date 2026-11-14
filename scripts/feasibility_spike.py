"""P1-07 feasibility spike: measure candidate sub-topics from real data.

Usage:
    python scripts/feasibility_spike.py \
        --csv data/retraction-watch/retraction_watch.csv \
        --out docs/reports/P1-feasibility.md \
        --json-out docs/reports/P1-feasibility.json

Method (all numbers from this script):

1. Candidate sub-topics are Retraction Watch subject categories, so the
   selection is reproducible and not chosen by topic appeal.
2. A seeded sample of linkable retractions per category is batch-resolved to
   Europe PMC (DOI query first, PMID fallback) to estimate the share that is
   open access with full text.
3. For a seeded sample of those OA papers, Europe PMC's citations endpoint
   lists citing papers. A seeded sample of citing MEDLINE ids is batch-
   resolved to measure how many citers are themselves OA full text.
4. For a seeded sample of OA citers, JATS is fetched and parsed; a context
   counts when its reference matches the source by DOI, PMID, or normalized
   title. Contexts-per-citer and citation counts scale the estimates.

The report separates MEASURED counts from ESTIMATED totals. Estimates use
independent Wilson bounds for each factor and are a range, not a joint CI.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from axion.config.settings import Settings
from axion.ingest.europepmc import EuropePmcClient, EuropePmcError, EuropePmcRecord
from axion.ingest.retractions import RetractionRecord, load_retraction_watch_csv
from axion.parse.jats import ParsedPaper, Reference, parse_jats

DEFAULT_SEED = 20261114
SAMPLE_PER_CATEGORY = 300
SOURCE_CITATIONS = 20
CITER_OA_SAMPLE = 200
CONTEXT_PAIRS = 10
BATCH_SIZE = 50
_TITLE_STRIP = re.compile(r"[^a-z0-9]+")
_DOI_IN_TEXT = re.compile(r"10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)


@dataclass(frozen=True)
class Candidate:
    key: str
    subject: str
    rationale: str


CANDIDATES = (
    Candidate(
        "oncology",
        "(HSC) Medicine - Oncology",
        "Largest biomedical retraction category; many oncology journals are OA.",
    ),
    Candidate(
        "cardiovascular",
        "(HSC) Medicine - Cardiovascular",
        "Large category with trial-heavy literature and retracted landmark papers.",
    ),
    Candidate(
        "infectious-disease",
        "(HSC) Medicine - Infectious Disease",
        "Large category that includes COVID-19-era retractions; high citation churn.",
    ),
    Candidate(
        "gastroenterology",
        "(HSC) Medicine - Gastroenterology",
        "Mid-size clinical category with substantial OA publication volume.",
    ),
    Candidate(
        "rehabilitation",
        "(HSC) Medicine - Rehabilitation/Therapy",
        "Less obvious candidate; tests whether a smaller clinical field still meets minimums.",
    ),
)


@dataclass
class SourcePaper:
    record_id: str
    doi: str | None
    pmid: str
    pmcid: str
    title: str | None
    year: int | None
    cited_by_count: int


@dataclass
class CategoryResult:
    candidate: Candidate
    linkable: int = 0
    sampled: int = 0
    resolved: int = 0
    oa_full_text: int = 0
    estimated_sources: float = 0.0
    estimated_sources_low: float = 0.0
    estimated_sources_high: float = 0.0
    source_sample: list[SourcePaper] = field(default_factory=list)
    citers_total: int = 0
    citers_measured: int = 0
    oa_citers: int = 0
    oa_share: float = 0.0
    oa_share_low: float = 0.0
    oa_share_high: float = 0.0
    context_pairs: int = 0
    contexts_found: int = 0
    contexts_per_pair: float = 0.0
    parse_failures: int = 0
    estimated_citers: float = 0.0
    estimated_citers_low: float = 0.0
    estimated_citers_high: float = 0.0
    estimated_contexts: float = 0.0
    estimated_contexts_low: float = 0.0
    estimated_contexts_high: float = 0.0
    errors: int = 0

    @property
    def passes(self) -> bool:
        return self.estimated_sources_low >= 30 and self.estimated_contexts_low >= 300

    @property
    def estimated_corpus(self) -> float:
        """Retracted sources plus OA citers: the papers P1-08 would ingest."""
        return self.estimated_sources + self.estimated_citers

    @property
    def fits_corpus_target(self) -> bool:
        return 2_000 <= self.estimated_corpus <= 5_000


def wilson(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    return _TITLE_STRIP.sub(" ", value.lower()).strip()


def reference_matches(reference: Reference, source: SourcePaper) -> bool:
    """True when a parsed reference points at the retracted source paper."""
    if source.doi and reference.doi and reference.doi.strip().lower() == source.doi.lower():
        return True
    if reference.pmid and reference.pmid.strip() == source.pmid:
        return True
    if reference.citation_text and source.doi:
        for candidate in _DOI_IN_TEXT.findall(reference.citation_text):
            if candidate.rstrip(".,;)").lower() == source.doi.lower():
                return True
    if reference.doi or reference.pmid:
        return False
    source_title = normalize_title(source.title)
    reference_title = normalize_title(reference.title)
    if not source_title or not reference_title:
        return False
    if source_title != reference_title:
        return False
    return not (source.year and reference.year and abs(source.year - reference.year) > 1)


def count_source_contexts(paper: ParsedPaper, source: SourcePaper) -> int:
    matching = {
        reference.ref_id for reference in paper.references if reference_matches(reference, source)
    }
    return sum(1 for context in paper.citation_contexts if context.ref_id in matching)


def seeded_sample(items: list[SourcePaper], size: int, seed: int) -> list[SourcePaper]:
    ordered = sorted(items, key=lambda item: item.pmid)
    if size >= len(ordered):
        return ordered
    return sorted(random.Random(seed).sample(ordered, size), key=lambda item: item.pmid)


def resolve_by_dois(client: EuropePmcClient, dois: list[str]) -> dict[str, EuropePmcRecord]:
    found: dict[str, EuropePmcRecord] = {}
    for start in range(0, len(dois), BATCH_SIZE):
        chunk = dois[start : start + BATCH_SIZE]
        query = "(" + " OR ".join(f'DOI:"{doi}"' for doi in chunk) + ")"
        page = client.search(query, page_size=min(1000, len(chunk) * 2))
        for record in page.records:
            if record.doi:
                found[record.doi.strip().lower()] = record
    return found


def resolve_by_pmids(client: EuropePmcClient, pmids: list[str]) -> dict[str, EuropePmcRecord]:
    found: dict[str, EuropePmcRecord] = {}
    for start in range(0, len(pmids), BATCH_SIZE):
        chunk = pmids[start : start + BATCH_SIZE]
        query = "EXT_ID:(" + " OR ".join(chunk) + ") AND SRC:MED"
        page = client.search(query, page_size=min(1000, len(chunk) * 2))
        for record in page.records:
            if record.pmid:
                found[record.pmid] = record
    return found


def resolve_records(
    client: EuropePmcClient, records: list[RetractionRecord]
) -> dict[str, EuropePmcRecord]:
    """Resolve retraction records by DOI first, then PMID."""
    by_doi = resolve_by_dois(
        client, [record.original_doi for record in records if record.original_doi]
    )
    unresolved = [record for record in records if record.original_pmid]
    by_pmid = resolve_by_pmids(
        client, [record.original_pmid for record in unresolved if record.original_pmid]
    )
    resolved: dict[str, EuropePmcRecord] = {}
    for record in records:
        match = by_doi.get((record.original_doi or "").lower()) if record.original_doi else None
        if match is None and record.original_pmid:
            match = by_pmid.get(record.original_pmid)
        if match is not None:
            resolved[record.record_id] = match
    return resolved


def to_source(record: RetractionRecord, match: EuropePmcRecord) -> SourcePaper | None:
    if not (match.pmcid and match.pmid and match.is_open_access and match.has_full_text):
        return None
    return SourcePaper(
        record_id=record.record_id,
        doi=match.doi or record.original_doi,
        pmid=match.pmid,
        pmcid=match.pmcid,
        title=match.title or record.title,
        year=match.year,
        cited_by_count=match.cited_by_count,
    )


def count_citers(client: EuropePmcClient, source: SourcePaper) -> tuple[int, list[str]]:
    identifiers: list[str] = []
    total = 0
    for page_number in range(1, 21):
        page = client.citations(source.pmid, page=page_number, page_size=1000)
        total = page.hit_count
        identifiers.extend(record.identifier for record in page.records if record.source == "MED")
        if len(identifiers) >= total or not page.records:
            break
    return total, identifiers


def estimate(result: CategoryResult, linkable: int) -> None:
    if result.sampled:
        share = result.oa_full_text / result.sampled
        low, high = wilson(result.oa_full_text, result.sampled)
        result.estimated_sources = share * linkable
        result.estimated_sources_low = low * linkable
        result.estimated_sources_high = high * linkable
    if result.citers_measured:
        result.oa_share = result.oa_citers / result.citers_measured
        result.oa_share_low, result.oa_share_high = wilson(result.oa_citers, result.citers_measured)
    mean_citers = result.citers_total / len(result.source_sample) if result.source_sample else 0.0
    result.estimated_citers = result.estimated_sources * mean_citers * result.oa_share
    result.estimated_citers_low = result.estimated_sources_low * mean_citers * result.oa_share_low
    result.estimated_citers_high = (
        result.estimated_sources_high * mean_citers * result.oa_share_high
    )
    if result.context_pairs:
        result.contexts_per_pair = result.contexts_found / result.context_pairs
    result.estimated_contexts = result.estimated_citers * result.contexts_per_pair
    result.estimated_contexts_low = result.estimated_citers_low * result.contexts_per_pair
    result.estimated_contexts_high = result.estimated_citers_high * result.contexts_per_pair


def measure_category(
    candidate: Candidate,
    records: list[RetractionRecord],
    client: EuropePmcClient,
    *,
    seed: int,
) -> CategoryResult:
    result = CategoryResult(candidate=candidate)
    subset = [
        record
        for record in records
        if record.is_retraction
        and candidate.subject in record.subjects
        and (record.original_doi or record.original_pmid)
    ]
    result.linkable = len(subset)
    chosen = sorted(
        random.Random(seed).sample(subset, min(SAMPLE_PER_CATEGORY, len(subset))),
        key=lambda record: record.record_id,
    )
    result.sampled = len(chosen)
    resolved = resolve_records(client, chosen)
    result.resolved = len(resolved)
    sources = [
        source
        for record in chosen
        if (match := resolved.get(record.record_id)) is not None
        and (source := to_source(record, match)) is not None
    ]
    result.oa_full_text = len(sources)
    result.source_sample = seeded_sample(sources, SOURCE_CITATIONS, seed + 1)
    estimate(result, result.linkable)

    pairs: list[tuple[SourcePaper, str]] = []
    for source in result.source_sample:
        try:
            total, identifiers = count_citers(client, source)
        except (EuropePmcError, OSError):
            result.errors += 1
            continue
        result.citers_total += total
        unique = sorted(set(identifiers))
        if unique:
            picked = seeded_ids(unique, CITER_OA_SAMPLE, seed + 2)
            citer_records = resolve_by_pmids(client, picked)
            result.citers_measured += len(picked)
            oa = [
                k
                for k, record in citer_records.items()
                if record.pmcid and record.is_open_access and record.has_full_text
            ]
            result.oa_citers += len(oa)
            for pmid in sorted(oa):
                pairs.append((source, pmid))

    pairs = seeded_pairs(pairs, CONTEXT_PAIRS, seed + 3)
    for source, pmid in pairs:
        record = client.find_by_pmid(pmid)
        if record is None or not record.pmcid:
            continue
        try:
            paper = parse_jats(client.fetch_full_text(record.pmcid))
        except (EuropePmcError, OSError, ValueError):
            result.parse_failures += 1
            result.context_pairs += 1
            continue
        result.context_pairs += 1
        result.contexts_found += count_source_contexts(paper, source)

    estimate(result, result.linkable)
    return result


def seeded_ids(items: list[str], size: int, seed: int) -> list[str]:
    ordered = sorted(items)
    if size >= len(ordered):
        return ordered
    return sorted(random.Random(seed).sample(ordered, size))


def seeded_pairs(
    items: list[tuple[SourcePaper, str]], size: int, seed: int
) -> list[tuple[SourcePaper, str]]:
    ordered = sorted(items, key=lambda pair: (pair[1], pair[0].pmid))
    if size >= len(ordered):
        return ordered
    return sorted(random.Random(seed).sample(ordered, size), key=lambda pair: pair[1])


def _percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _number(value: float) -> str:
    return f"{value:,.0f}"


def _range(low: float, high: float) -> str:
    return f"{_number(low)} to {_number(high)}"


def _percent_range(low: float, high: float) -> str:
    return f"{_percent(low)} to {_percent(high)}"


def render(results: list[CategoryResult], *, seed: int) -> str:
    lines = [
        "# P1 feasibility spike — candidate sub-topics",
        "",
        "Generated by `python scripts/feasibility_spike.py`. Every number below is",
        "computed from the Retraction Watch snapshot and live Europe PMC responses;",
        "nothing is hand-entered.",
        "",
        "## Criteria",
        "",
        "From CONTEXT §4: at least **30 retracted OA source papers with full text** and",
        "at least **300 citation contexts citing them**. Selection follows the measured",
        "minimums, not topic appeal. A category passes only if its **lower bound** clears",
        "both minimums.",
        "",
        "## Results",
        "",
        "| Candidate | Linkable retractions | OA+full-text (measured) | "
        "Est. OA sources [range] | Citers measured | OA citers | Contexts / pairs | "
        "Est. contexts [range] | Est. corpus | Passes |",
        "| :-- | --: | --: | --: | --: | --: | --: | --: | --: | :--: |",
    ]
    for result in results:
        lines.append(
            f"| {result.candidate.key} | {result.linkable:,} | "
            f"{result.oa_full_text}/{result.sampled} | "
            f"{_number(result.estimated_sources)} "
            f"[{_range(result.estimated_sources_low, result.estimated_sources_high)}] | "
            f"{result.citers_total:,} | {result.oa_citers}/{result.citers_measured} | "
            f"{result.contexts_found}/{result.context_pairs} | "
            f"{_number(result.estimated_contexts)} "
            f"[{_range(result.estimated_contexts_low, result.estimated_contexts_high)}] | "
            f"{_number(result.estimated_corpus)} | "
            f"{'yes' if result.passes else 'no'} |"
        )

    lines += [
        "",
        "## Per-candidate detail",
        "",
    ]
    for result in results:
        oa_share = _percent(result.oa_full_text / max(result.sampled, 1))
        mean_citers = (
            result.citers_total / len(result.source_sample) if result.source_sample else 0.0
        )
        lines += [
            f"### {result.candidate.key}",
            "",
            f"- RW subject: `{result.candidate.subject}` — {result.candidate.rationale}",
            f"- Linkable retraction rows: **{result.linkable:,}**; "
            f"sampled **{result.sampled}**; resolved in Europe PMC "
            f"**{result.resolved}**; OA with full text "
            f"**{result.oa_full_text}** ({oa_share}).",
            f"- Source papers sampled for citations: **{len(result.source_sample)}**; "
            f"mean citers per source **{mean_citers:.1f}**; "
            f"measured citers **{result.citers_total:,}**.",
            f"- Citer OA share: **{_percent(result.oa_share)}** "
            f"(Wilson {_percent_range(result.oa_share_low, result.oa_share_high)}).",
            f"- Context pairs parsed: **{result.context_pairs}**; contexts found "
            f"**{result.contexts_found}**; mean **{result.contexts_per_pair:.2f}** per pair; "
            f"JATS failures **{result.parse_failures}**.",
            f"- Estimated corpus (sources + OA citers): **{_number(result.estimated_corpus)}**; "
            f"{'inside' if result.fits_corpus_target else 'outside'} the 2,000-5,000 target.",
            "",
        ]
    passing = [result for result in results if result.passes]
    fitting = [result for result in passing if result.fits_corpus_target]
    winner = (
        max(
            fitting or passing,
            key=lambda result: (
                result.estimated_contexts_low,
                -result.estimated_corpus,
            ),
        )
        if passing
        else None
    )
    lines += [
        "## Recommendation",
        "",
    ]
    if winner:
        lines += [
            f"**{winner.candidate.key}** is the proposed sub-topic: its conservative",
            f"lower bound is {_number(winner.estimated_sources_low)} source papers and",
            f"{_number(winner.estimated_contexts_low)} contexts, clearing both minimums.",
            f"Its estimated corpus of {_number(winner.estimated_corpus)} papers "
            f"{'fits' if winner.fits_corpus_target else 'exceeds'} the PRD's 2,000-5,000 target.",
            "Among candidates that clear the minimums, the recommendation prefers a corpus",
            "that fits the target and then the widest context margin. The ADR records the",
            "alternatives and the estimate method; the owner makes the final choice.",
        ]
    else:
        lines += [
            "No candidate clears both minimums at the lower bound. Apply the CONTEXT §6",
            "pivot rule (broaden sub-topics or lower minimums) via ADR; do not fabricate",
            "labels or silently relax the criteria.",
        ]
    lines += [
        "",
        "## Method and limitations",
        "",
        f"- Fixed seed `{seed}`; samples are uniform over eligible records.",
        "- Source availability uses a sample of up to 300 linkable retractions per category "
        "because resolving all 68k rows live would be impolite.",
        "- Citer OA share uses a sample of up to 200 MEDLINE citers per category; preprints "
        "are excluded from context measurement.",
        "- Context counts come from fetched JATS only. A reference matches by DOI, PMID, or "
        "matched normalized title + year (±1); this is why reference-DOI coverage alone is "
        "not used.",
        "- Estimated totals multiply independent point estimates; the ranges combine "
        "independent Wilson bounds and are **not** a joint confidence interval.",
        "- Europe PMC's citations endpoint takes a PMID (`MED/<id>/citations`); a PMCID "
        "path returns 404. This was verified live and is used throughout.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("docs/reports/P1-feasibility.md"))
    parser.add_argument("--json-out", type=Path, default=Path("docs/reports/P1-feasibility.json"))
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--only", action="append", help="limit to a candidate key (repeatable)")
    args = parser.parse_args(argv)

    try:
        records = load_retraction_watch_csv(args.csv)
        client = EuropePmcClient.from_settings(Settings())
        selected = [
            candidate for candidate in CANDIDATES if not args.only or candidate.key in args.only
        ]
        if not selected:
            raise ValueError(f"unknown candidate filter: {args.only}")
        results = [
            measure_category(candidate, records, client, seed=args.seed) for candidate in selected
        ]
    except (EuropePmcError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render(results, seed=args.seed), encoding="utf-8")
    payload = {
        "seed": args.seed,
        "criteria": {"min_sources": 30, "min_contexts": 300},
        "candidates": [
            {
                "key": result.candidate.key,
                "subject": result.candidate.subject,
                "linkable": result.linkable,
                "sampled": result.sampled,
                "resolved": result.resolved,
                "oa_full_text": result.oa_full_text,
                "estimated_sources": result.estimated_sources,
                "estimated_sources_low": result.estimated_sources_low,
                "estimated_sources_high": result.estimated_sources_high,
                "citers_total": result.citers_total,
                "citers_measured": result.citers_measured,
                "oa_citers": result.oa_citers,
                "oa_share": result.oa_share,
                "context_pairs": result.context_pairs,
                "contexts_found": result.contexts_found,
                "contexts_per_pair": result.contexts_per_pair,
                "parse_failures": result.parse_failures,
                "estimated_citers": result.estimated_citers,
                "estimated_contexts": result.estimated_contexts,
                "estimated_contexts_low": result.estimated_contexts_low,
                "estimated_contexts_high": result.estimated_contexts_high,
                "estimated_corpus": result.estimated_corpus,
                "fits_corpus_target": result.fits_corpus_target,
                "passes": result.passes,
                "errors": result.errors,
            }
            for result in results
        ],
    }
    args.json_out.parent.mkdir(parents=True, exist_ok=True)
    args.json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
