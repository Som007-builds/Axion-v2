"""In-memory graph and vector backends for offline tests and dry runs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any


class InMemoryGraph:
    """Idempotent in-memory stand-in for :class:`Neo4jBackend`."""

    def __init__(self) -> None:
        self.papers: dict[str, dict[str, object]] = {}
        self.notices: dict[str, dict[str, object]] = {}
        self.cites: dict[tuple[str, str], int] = {}
        self.contexts: dict[str, dict[str, object]] = {}
        self.source_claims: dict[str, dict[str, object]] = {}
        self.in_paper: set[tuple[str, str]] = set()
        self.points_to: set[tuple[str, str]] = set()
        self.retracted_by: set[tuple[str, str]] = set()
        self.extracted_from: set[tuple[str, str]] = set()

    def apply_schema(self) -> None:
        return None

    def upsert_papers(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None:
        for row in rows:
            pmcid = str(row["pmcid"])
            existing = self.papers.get(pmcid, {})
            merged = dict(existing)
            for key, value in row.items():
                if value is not None or key not in merged:
                    merged[key] = value
            merged["run_id"] = run_id
            self.papers[pmcid] = merged

    def upsert_notices(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None:
        for row in rows:
            notice_id = str(row["notice_id"])
            self.notices[notice_id] = {**row, "run_id": run_id}
            self.retracted_by.add((str(row["pmcid"]), notice_id))

    def upsert_cites(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None:
        for row in rows:
            key = (str(row["citer_pmcid"]), str(row["source_pmcid"]))
            self.cites[key] = int(str(row["contexts"]))

    def upsert_contexts(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None:
        for row in rows:
            ctx_id = str(row["ctx_id"])
            self.contexts[ctx_id] = {**row, "run_id": run_id}
            self.in_paper.add((ctx_id, str(row["citer_pmcid"])))
            self.points_to.add((ctx_id, str(row["source_pmcid"])))

    def upsert_source_claims(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None:
        for row in rows:
            claim_id = str(row["claim_id"])
            self.source_claims[claim_id] = {**row, "run_id": run_id}
            self.extracted_from.add((claim_id, str(row["source_pmcid"])))

    def upsert_candidates(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None:
        for row in rows:
            ctx_id = str(row["ctx_id"])
            self.contexts[ctx_id] = {**row, "run_id": run_id}
            self.in_paper.add((ctx_id, str(row["citer_pmcid"])))
            self.points_to.add((ctx_id, str(row["source_pmcid"])))

    def counts(self) -> dict[str, int]:
        return {
            "Paper": len(self.papers),
            "Claim": len(self.source_claims),
            "CitationContext": len(self.contexts),
            "RetractionNotice": len(self.notices),
            "CITES": len(self.cites),
            "IN_PAPER": len(self.in_paper),
            "POINTS_TO": len(self.points_to),
            "EXTRACTED_FROM": len(self.extracted_from),
            "RETRACTED_BY": len(self.retracted_by),
        }

    def close(self) -> None:
        return None


class InMemoryVectorStore:
    """Idempotent in-memory stand-in for the Chroma adapter."""

    def __init__(self) -> None:
        self.collections: dict[str, dict[str, dict[str, Any]]] = {}

    def ensure_collections(self, names: Iterable[str]) -> None:
        for name in names:
            self.collections.setdefault(name, {})

    def upsert(
        self,
        collection: str,
        *,
        ids: Sequence[str],
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, object]],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        if not (len(ids) == len(documents) == len(metadatas) == len(embeddings)):
            raise ValueError("vector upsert inputs must have equal length")
        target = self.collections.setdefault(collection, {})
        for item_id, document, metadata, embedding in zip(
            ids, documents, metadatas, embeddings, strict=True
        ):
            target[item_id] = {
                "document": document,
                "metadata": dict(metadata),
                "embedding": list(embedding),
            }

    def count(self, collection: str) -> int:
        return len(self.collections.get(collection, {}))


__all__ = ["InMemoryGraph", "InMemoryVectorStore"]
