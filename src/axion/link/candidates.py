"""Deterministic P3-02 candidate-context generator.

For every retracted or flagged source paper A, collect each in-corpus citation
context whose JATS ``bibr`` xref resolves to A. The parser's context ID is the
stable candidate key. A source-claim proxy is also extracted from A's abstract
with a fixed rule; it is a placeholder for P3-06 claim linking, not a gold
claim, a model output, or a dependency label.

The generator makes no network, model, or ledger calls. It also produces the
paper, notice, and cite rows needed to make the candidate graph loadable on a
fresh Neo4j instance. Running it twice with the same inputs produces identical
rows and graph counts.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from axion.ingest.corpus import CorpusCite, CorpusPaper
from axion.link.citations import SourceIndex, SourceTarget
from axion.parse.jats import JatsParseError, ParsedPaper, parse_jats_file
from axion.store.base import GraphBackend, StoreError

_ABSTRACT_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
_ABSTRACT_MIN_CHARS = 60
_ABSTRACT_SKIP_PREFIXES = (
    "introduction",
    "background",
    "objective",
    "methods",
    "this article has been withdrawn",
    "the full elsevier",
    "the publisher apologizes",
)


class CandidateError(StoreError):
    """Raised when corpus inputs cannot produce a consistent candidate set."""


@dataclass(frozen=True)
class SourceCount:
    """Per-source candidate coverage, including sources with zero contexts."""

    source_pmcid: str
    candidate_contexts: int
    citer_papers: int
    source_claim_id: str
    has_source_claim: bool

    def to_row(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class CandidateTotals:
    """Aggregate counts for the candidate set."""

    source_papers_with_citers: int
    source_papers_with_contexts: int
    source_papers_without_contexts: int
    candidate_contexts: int
    citer_papers: int
    source_claim_proxies: int
    contexts_with_source_claim: int
    contexts_without_source_claim: int


@dataclass(frozen=True)
class CandidateBundle:
    """All rows needed to persist the P3-02 candidate graph."""

    paper_rows: tuple[dict[str, object], ...]
    notice_rows: tuple[dict[str, object], ...]
    cite_rows: tuple[dict[str, object], ...]
    context_rows: tuple[dict[str, object], ...]
    source_claim_rows: tuple[dict[str, object], ...]
    source_counts: tuple[SourceCount, ...]
    totals: CandidateTotals


@dataclass(frozen=True)
class CandidateLoadResult:
    """Counts after an idempotent candidate load."""

    paper_rows: int
    notice_rows: int
    cite_rows: int
    candidate_rows: int
    source_claim_rows: int
    graph_counts: dict[str, int]


def source_claim_proxy_text(paper: ParsedPaper | None) -> str:
    """Return one substantive abstract sentence, or an empty string.

    This is the same deterministic rule used by the P3-01 pilot packet. It is
    deliberately a single sentence: the source-claim *proxy* keeps P3-02 free
    of LLM extraction. P3-06 is responsible for matching a relying context to a
    specific source claim.
    """
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
            for sentence in _ABSTRACT_SENTENCE_SPLIT.split(text):
                candidate = sentence.strip()
                lowered = candidate.lower()
                if len(candidate) < _ABSTRACT_MIN_CHARS:
                    continue
                if lowered.startswith(_ABSTRACT_SKIP_PREFIXES):
                    continue
                return candidate[:700]
    return ""


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


def _paper_row(
    paper: CorpusPaper,
    parsed: ParsedPaper | None,
    *,
    is_citer: bool,
) -> dict[str, object]:
    return {
        "pmcid": paper.pmcid,
        "pmid": (parsed.pmid if parsed and parsed.pmid else paper.pmid),
        "doi": (parsed.doi if parsed and parsed.doi else paper.doi),
        "title": parsed.title if parsed else None,
        "year": parsed.year if parsed else None,
        "journal": parsed.journal if parsed else None,
        "role": paper.role,
        "is_source": paper.role == "source",
        "is_citer": is_citer,
    }


def _notice_rows(papers: Sequence[CorpusPaper]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for paper in papers:
        for record_id in paper.rw_record_ids:
            key = (paper.pmcid, record_id)
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    "pmcid": paper.pmcid,
                    "notice_id": f"RW:{record_id}",
                    "record_id": record_id,
                    "source": "Retraction Watch",
                }
            )
    return rows


def _source_targets(
    source_ids: Sequence[str],
    papers_by_pmcid: Mapping[str, CorpusPaper],
    parsed_by_pmcid: Mapping[str, ParsedPaper | None],
) -> SourceIndex:
    targets: list[SourceTarget] = []
    for pmcid in source_ids:
        paper = papers_by_pmcid[pmcid]
        parsed = parsed_by_pmcid.get(pmcid)
        targets.append(
            SourceTarget(
                key=pmcid,
                doi=(parsed.doi if parsed and parsed.doi else paper.doi),
                pmid=(parsed.pmid if parsed and parsed.pmid else paper.pmid),
                title=parsed.title if parsed else None,
                year=parsed.year if parsed else None,
            )
        )
    return SourceIndex(targets)


def _relevant_ids(
    papers_by_pmcid: Mapping[str, CorpusPaper],
    cites: Sequence[CorpusCite],
) -> tuple[list[str], list[str]]:
    source_ids = sorted({cite.source_pmcid for cite in cites})
    citer_ids = sorted({cite.citer_pmcid for cite in cites})
    for pmcid in (*source_ids, *citer_ids):
        if pmcid not in papers_by_pmcid:
            raise CandidateError(f"cite row references a paper outside the manifest: {pmcid}")
    for source_pmcid in source_ids:
        if papers_by_pmcid[source_pmcid].role != "source":
            raise CandidateError(f"cite target is not a source paper: {source_pmcid}")
    return source_ids, citer_ids


def build_candidates(
    papers: Sequence[CorpusPaper],
    cites: Sequence[CorpusCite],
    *,
    cache_dir: Path,
    require_fulltext: bool = True,
    expected_contexts: int | None = None,
) -> CandidateBundle:
    """Build the candidate rows without touching a graph or vector store.

    ``expected_contexts`` is the P1 manifest's ``contexts_total`` when supplied;
    a mismatch fails loudly rather than silently reporting a different frame.
    """
    if not papers:
        raise CandidateError("corpus has no papers")
    papers_by_pmcid = {paper.pmcid: paper for paper in papers}
    if len(papers_by_pmcid) != len(papers):
        raise CandidateError("corpus paper list contains duplicate PMCIDs")
    source_ids, citer_ids = _relevant_ids(papers_by_pmcid, cites)
    if not source_ids:
        raise CandidateError("corpus has no cite edges")
    relevant_ids = sorted(set(source_ids) | set(citer_ids))

    parsed_by_pmcid: dict[str, ParsedPaper | None] = {}
    missing: list[str] = []
    for pmcid in relevant_ids:
        parsed = _parse_cached(pmcid, cache_dir, parsed_by_pmcid)
        if parsed is None:
            missing.append(pmcid)
    if require_fulltext and missing:
        raise CandidateError(
            f"{len(missing)} relevant papers have no parseable cached full text; "
            f"first: {missing[0]}"
        )

    source_claim_rows: list[dict[str, object]] = []
    source_claim_by_source: dict[str, str] = {}
    for source_pmcid in source_ids:
        proxy = source_claim_proxy_text(parsed_by_pmcid.get(source_pmcid))
        if not proxy:
            continue
        claim_id = f"rule:{source_pmcid}:abstract:1"
        source_claim_by_source[source_pmcid] = claim_id
        source_claim_rows.append(
            {
                "claim_id": claim_id,
                "source_pmcid": source_pmcid,
                "text": proxy,
                "evidence_span": proxy,
                "section": "Abstract",
                "claim_kind": "source_abstract_proxy",
            }
        )

    index = _source_targets(source_ids, papers_by_pmcid, parsed_by_pmcid)
    allowed = {(cite.citer_pmcid, cite.source_pmcid) for cite in cites}
    context_rows: list[dict[str, object]] = []
    seen_contexts: set[str] = set()
    for citer_pmcid in citer_ids:
        parsed = parsed_by_pmcid.get(citer_pmcid)
        if parsed is None:
            continue
        for context, source_pmcid in index.matched_contexts(parsed):
            if (citer_pmcid, source_pmcid) not in allowed:
                continue
            if context.context_id in seen_contexts:
                continue
            seen_contexts.add(context.context_id)
            context_rows.append(
                {
                    "ctx_id": context.context_id,
                    "text": context.text,
                    "paragraph_text": context.paragraph_text,
                    "section": " > ".join(context.section),
                    "paragraph_index": context.paragraph_index,
                    "sentence_index": context.sentence_index,
                    "marker": context.marker,
                    "ref_id": context.ref_id,
                    "citer_pmcid": citer_pmcid,
                    "source_pmcid": source_pmcid,
                    "source_claim_id": source_claim_by_source.get(source_pmcid, ""),
                }
            )

    actual_contexts = len(context_rows)
    if expected_contexts is not None and actual_contexts != expected_contexts:
        raise CandidateError(
            f"candidate contexts {actual_contexts} != manifest contexts_total "
            f"{expected_contexts}; the parser or matcher changed"
        )

    contexts_by_source: dict[str, int] = defaultdict(int)
    citers_by_source: dict[str, set[str]] = defaultdict(set)
    for row in context_rows:
        source_pmcid = str(row["source_pmcid"])
        contexts_by_source[source_pmcid] += 1
        citers_by_source[source_pmcid].add(str(row["citer_pmcid"]))

    source_counts = tuple(
        SourceCount(
            source_pmcid=source_pmcid,
            candidate_contexts=contexts_by_source.get(source_pmcid, 0),
            citer_papers=len(citers_by_source.get(source_pmcid, set())),
            source_claim_id=source_claim_by_source.get(source_pmcid, ""),
            has_source_claim=source_pmcid in source_claim_by_source,
        )
        for source_pmcid in source_ids
    )
    totals = CandidateTotals(
        source_papers_with_citers=len(source_ids),
        source_papers_with_contexts=sum(1 for row in source_counts if row.candidate_contexts > 0),
        source_papers_without_contexts=sum(
            1 for row in source_counts if row.candidate_contexts == 0
        ),
        candidate_contexts=actual_contexts,
        citer_papers=len({str(row["citer_pmcid"]) for row in context_rows}),
        source_claim_proxies=len(source_claim_rows),
        contexts_with_source_claim=sum(1 for row in context_rows if row["source_claim_id"]),
        contexts_without_source_claim=sum(1 for row in context_rows if not row["source_claim_id"]),
    )

    relevant_papers = [papers_by_pmcid[pmcid] for pmcid in relevant_ids]
    citer_set = set(citer_ids)
    paper_rows = [
        _paper_row(paper, parsed_by_pmcid.get(paper.pmcid), is_citer=paper.pmcid in citer_set)
        for paper in relevant_papers
    ]
    notice_rows = _notice_rows([papers_by_pmcid[pmcid] for pmcid in source_ids])
    cite_rows = [
        {
            "citer_pmcid": cite.citer_pmcid,
            "source_pmcid": cite.source_pmcid,
            "contexts": cite.contexts,
        }
        for cite in cites
    ]
    return CandidateBundle(
        paper_rows=tuple(paper_rows),
        notice_rows=tuple(notice_rows),
        cite_rows=tuple(cite_rows),
        context_rows=tuple(context_rows),
        source_claim_rows=tuple(source_claim_rows),
        source_counts=source_counts,
        totals=totals,
    )


def validate_source_counts(cites: Sequence[CorpusCite], bundle: CandidateBundle) -> None:
    """Fail if per-source candidate counts disagree with the P1 cite manifest."""
    expected: dict[str, int] = defaultdict(int)
    for cite in cites:
        expected[cite.source_pmcid] += cite.contexts
    actual = {row.source_pmcid: row.candidate_contexts for row in bundle.source_counts}
    mismatches = [
        (source_pmcid, actual.get(source_pmcid, 0), count)
        for source_pmcid, count in sorted(expected.items())
        if actual.get(source_pmcid, 0) != count
    ]
    if mismatches:
        first = mismatches[0]
        raise CandidateError(
            f"{len(mismatches)} source context counts disagree with the cite manifest; "
            f"first: {first[0]} actual {first[1]} expected {first[2]}"
        )


def load_candidates(
    bundle: CandidateBundle,
    *,
    graph: GraphBackend,
    run_id: str,
) -> CandidateLoadResult:
    """Load candidate rows idempotently into a graph backend."""
    graph.apply_schema()
    graph.upsert_papers(bundle.paper_rows, run_id=run_id)
    graph.upsert_notices(bundle.notice_rows, run_id=run_id)
    graph.upsert_cites(bundle.cite_rows, run_id=run_id)
    graph.upsert_source_claims(bundle.source_claim_rows, run_id=run_id)
    graph.upsert_candidates(bundle.context_rows, run_id=run_id)
    return CandidateLoadResult(
        paper_rows=len(bundle.paper_rows),
        notice_rows=len(bundle.notice_rows),
        cite_rows=len(bundle.cite_rows),
        candidate_rows=len(bundle.context_rows),
        source_claim_rows=len(bundle.source_claim_rows),
        graph_counts=graph.counts(),
    )


__all__ = [
    "CandidateBundle",
    "CandidateError",
    "CandidateLoadResult",
    "CandidateTotals",
    "SourceCount",
    "build_candidates",
    "load_candidates",
    "source_claim_proxy_text",
    "validate_source_counts",
]
