"""Protocols shared by the Neo4j and Chroma adapters."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Protocol


class StoreError(Exception):
    """Base class for store failures."""


class StoreConfigurationError(StoreError):
    """Raised when a store dependency or connection setting is missing."""


class GraphBackend(Protocol):
    """The graph operations the corpus loader needs.

    Implementations must be idempotent: applying the same rows twice must not
    create duplicate nodes or relationships.
    """

    def apply_schema(self) -> None: ...

    def upsert_papers(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None: ...

    def upsert_notices(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None: ...

    def upsert_cites(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None: ...

    def upsert_contexts(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None: ...

    def counts(self) -> dict[str, int]: ...

    def close(self) -> None: ...


class VectorStore(Protocol):
    """The vector operations the corpus loader needs."""

    def ensure_collections(self, names: Iterable[str]) -> None: ...

    def upsert(
        self,
        collection: str,
        *,
        ids: Sequence[str],
        documents: Sequence[str],
        metadatas: Sequence[Mapping[str, object]],
        embeddings: Sequence[Sequence[float]],
    ) -> None: ...

    def count(self, collection: str) -> int: ...


__all__ = [
    "GraphBackend",
    "StoreConfigurationError",
    "StoreError",
    "VectorStore",
]
