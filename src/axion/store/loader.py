"""Idempotent corpus loader for Neo4j schema v2 and Chroma.

The loader accepts the ID-only P1 manifest bundle plus the untracked full-text
cache. It parses JATS locally, matches citation contexts to sources with the
same deterministic rule used by P1-08, and writes graph rows and vector rows
by stable IDs. Running it twice leaves the same counts.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from axion.ingest.corpus import CorpusCite, CorpusPaper, sha256_file
from axion.link.citations import SourceIndex, SourceTarget
from axion.parse.jats import JatsParseError, ParsedPaper, parse_jats_file
from axion.store.base import GraphBackend, StoreError, VectorStore
from axion.store.embeddings import Embedder

PAPERS_COLLECTION = "papers"
CLAIMS_COLLECTION = "claims"
CONTEXTS_COLLECTION = "citation_contexts"
COLLECTIONS = (PAPERS_COLLECTION, CLAIMS_COLLECTION, CONTEXTS_COLLECTION)
_EMBED_BATCH = 128


class CorpusLoadError(StoreError):
    """Raised when the manifest bundle and the local cache disagree."""


@dataclass(frozen=True)
class LoadResult:
    papers: int
    cites: int
    contexts: int
    notices: int
    parse_failures: int
    missing_fulltext: int
    graph_counts: dict[str, int]
    vector_counts: dict[str, int]


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


def _context_rows(
    cites: Sequence[CorpusCite],
    parsed_by_pmcid: Mapping[str, ParsedPaper],
    index: SourceIndex,
) -> list[dict[str, object]]:
    allowed = {(cite.citer_pmcid, cite.source_pmcid) for cite in cites}
    citers = sorted({cite.citer_pmcid for cite in cites})
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for citer_pmcid in citers:
        parsed = parsed_by_pmcid.get(citer_pmcid)
        if parsed is None:
            continue
        for context, source_pmcid in index.matched_contexts(parsed):
            if (citer_pmcid, source_pmcid) not in allowed:
                continue
            if context.context_id in seen:
                continue
            seen.add(context.context_id)
            rows.append(
                {
                    "ctx_id": context.context_id,
                    "text": context.text,
                    "section": " > ".join(context.section),
                    "marker": context.marker,
                    "ref_id": context.ref_id,
                    "citer_pmcid": citer_pmcid,
                    "source_pmcid": source_pmcid,
                }
            )
    return rows


def _metadata(row: Mapping[str, object], keys: Sequence[str]) -> dict[str, object]:
    return {key: row[key] for key in keys if row.get(key) is not None}


def _upsert_vectors(
    vectors: VectorStore,
    embedder: Embedder,
    collection: str,
    ids: Sequence[str],
    documents: Sequence[str],
    metadatas: Sequence[Mapping[str, object]],
) -> None:
    for start in range(0, len(ids), _EMBED_BATCH):
        end = start + _EMBED_BATCH
        batch_documents = list(documents[start:end])
        embeddings = embedder.embed(batch_documents)
        vectors.upsert(
            collection,
            ids=list(ids[start:end]),
            documents=batch_documents,
            metadatas=[dict(item) for item in metadatas[start:end]],
            embeddings=embeddings,
        )


def load_corpus(
    papers: Sequence[CorpusPaper],
    cites: Sequence[CorpusCite],
    *,
    graph: GraphBackend,
    vectors: VectorStore,
    embedder: Embedder,
    cache_dir: Path,
    run_id: str,
    require_fulltext: bool = True,
) -> LoadResult:
    """Load one corpus manifest bundle idempotently."""
    if not papers:
        raise CorpusLoadError("corpus has no papers")
    if len({paper.pmcid for paper in papers}) != len(papers):
        raise CorpusLoadError("corpus paper list contains duplicate PMCIDs")

    graph.apply_schema()
    vectors.ensure_collections(COLLECTIONS)

    parsed_by_pmcid: dict[str, ParsedPaper] = {}
    parse_failures = 0
    missing_fulltext = 0
    for paper in papers:
        path = cache_dir / "fulltext" / f"{paper.pmcid}.xml"
        if not path.exists():
            missing_fulltext += 1
            continue
        try:
            parsed_by_pmcid[paper.pmcid] = parse_jats_file(path, paper_id=paper.pmcid)
        except JatsParseError:
            parse_failures += 1
    if require_fulltext and missing_fulltext:
        raise CorpusLoadError(
            f"{missing_fulltext} papers have no cached full text under {cache_dir}; "
            "run scripts/ingest_corpus.py first"
        )

    citer_pmcids = {cite.citer_pmcid for cite in cites}
    paper_rows = [
        _paper_row(paper, parsed_by_pmcid.get(paper.pmcid), is_citer=paper.pmcid in citer_pmcids)
        for paper in papers
    ]
    graph.upsert_papers(paper_rows, run_id=run_id)
    notice_rows = _notice_rows(papers)
    graph.upsert_notices(notice_rows, run_id=run_id)
    cite_rows = [
        {
            "citer_pmcid": cite.citer_pmcid,
            "source_pmcid": cite.source_pmcid,
            "contexts": cite.contexts,
        }
        for cite in cites
    ]
    graph.upsert_cites(cite_rows, run_id=run_id)

    targets = [
        SourceTarget(
            key=paper.pmcid,
            doi=(
                parsed_by_pmcid[paper.pmcid].doi
                if paper.pmcid in parsed_by_pmcid and parsed_by_pmcid[paper.pmcid].doi
                else paper.doi
            ),
            pmid=(
                parsed_by_pmcid[paper.pmcid].pmid
                if paper.pmcid in parsed_by_pmcid and parsed_by_pmcid[paper.pmcid].pmid
                else paper.pmid
            ),
            title=(parsed_by_pmcid[paper.pmcid].title if paper.pmcid in parsed_by_pmcid else None),
            year=(parsed_by_pmcid[paper.pmcid].year if paper.pmcid in parsed_by_pmcid else None),
        )
        for paper in papers
        if paper.role == "source"
    ]
    index = SourceIndex(targets)
    context_rows = _context_rows(cites, parsed_by_pmcid, index)
    graph.upsert_contexts(context_rows, run_id=run_id)

    paper_ids = [f"paper:{paper.pmcid}" for paper in papers]
    paper_documents = [str(row.get("title") or row["pmcid"]) for row in paper_rows]
    paper_metadata = [
        _metadata(
            {**row, "run_id": run_id},
            ("pmcid", "pmid", "doi", "year", "journal", "role", "is_source", "is_citer", "run_id"),
        )
        for row in paper_rows
    ]
    _upsert_vectors(
        vectors, embedder, PAPERS_COLLECTION, paper_ids, paper_documents, paper_metadata
    )

    context_ids = [f"ctx:{row['ctx_id']}" for row in context_rows]
    context_documents = [str(row["text"]) for row in context_rows]
    context_metadata = [
        _metadata(
            {**row, "run_id": run_id},
            ("citer_pmcid", "source_pmcid", "section", "marker", "ref_id", "run_id"),
        )
        for row in context_rows
    ]
    _upsert_vectors(
        vectors,
        embedder,
        CONTEXTS_COLLECTION,
        context_ids,
        context_documents,
        context_metadata,
    )

    return LoadResult(
        papers=len(papers),
        cites=len(cites),
        contexts=len(context_rows),
        notices=len(notice_rows),
        parse_failures=parse_failures,
        missing_fulltext=missing_fulltext,
        graph_counts=graph.counts(),
        vector_counts={name: vectors.count(name) for name in COLLECTIONS},
    )


def load_bundle(
    manifest_path: Path,
    *,
    graph: GraphBackend,
    vectors: VectorStore,
    embedder: Embedder,
    cache_dir: Path,
    require_fulltext: bool = True,
) -> LoadResult:
    """Read and validate the ID-only bundle, then load it."""
    from axion.ingest.corpus import read_cites_csv, read_manifest, read_papers_csv

    manifest = read_manifest(manifest_path)
    papers_path = manifest_path.parent / Path(manifest.files.papers_csv).name
    cites_path = manifest_path.parent / Path(manifest.files.cites_csv).name
    if sha256_file(papers_path) != manifest.files.papers_sha256:
        raise CorpusLoadError(f"paper manifest hash mismatch: {papers_path}")
    if sha256_file(cites_path) != manifest.files.cites_sha256:
        raise CorpusLoadError(f"citation manifest hash mismatch: {cites_path}")
    papers = read_papers_csv(papers_path)
    cites = read_cites_csv(cites_path)
    run_id = f"p1-corpus-{manifest.config_sha256[:12]}"
    return load_corpus(
        papers,
        cites,
        graph=graph,
        vectors=vectors,
        embedder=embedder,
        cache_dir=cache_dir,
        run_id=run_id,
        require_fulltext=require_fulltext,
    )


def dump_result(result: LoadResult) -> str:
    return json.dumps(
        {
            "papers": result.papers,
            "cites": result.cites,
            "contexts": result.contexts,
            "notices": result.notices,
            "parse_failures": result.parse_failures,
            "missing_fulltext": result.missing_fulltext,
            "graph_counts": result.graph_counts,
            "vector_counts": result.vector_counts,
        },
        indent=2,
        sort_keys=True,
    )


__all__ = [
    "CLAIMS_COLLECTION",
    "COLLECTIONS",
    "CONTEXTS_COLLECTION",
    "PAPERS_COLLECTION",
    "CorpusLoadError",
    "LoadResult",
    "dump_result",
    "load_bundle",
    "load_corpus",
]
