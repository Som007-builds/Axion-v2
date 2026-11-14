"""Chroma persistent adapter for citation-context and claim collections."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from axion.store.base import StoreConfigurationError, StoreError

_UPSERT_BATCH = 500


class ChromaVectorStore:
    """Persistent Chroma client with explicit, precomputed embeddings.

    Passing embeddings explicitly keeps the loader independent of Chroma's
    default embedding function and makes idempotency testable.
    """

    def __init__(self, path: Path) -> None:
        try:
            import chromadb
        except ImportError as exc:
            raise StoreConfigurationError(
                "chromadb is not installed; install the 'store' extra from " "docs/LOCAL_SETUP.md"
            ) from exc
        self._client: Any = chromadb.PersistentClient(path=str(path))
        self._collections: dict[str, Any] = {}

    def ensure_collections(self, names: Iterable[str]) -> None:
        for name in names:
            if name not in self._collections:
                self._collections[name] = self._client.get_or_create_collection(
                    name=name, metadata={"hnsw:space": "cosine"}
                )

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
        target = self._collections.get(collection)
        if target is None:
            raise StoreError(f"collection {collection!r} was not ensured")
        for start in range(0, len(ids), _UPSERT_BATCH):
            end = start + _UPSERT_BATCH
            target.upsert(
                ids=list(ids[start:end]),
                documents=list(documents[start:end]),
                metadatas=[dict(item) for item in metadatas[start:end]],
                embeddings=[list(vector) for vector in embeddings[start:end]],
            )

    def count(self, collection: str) -> int:
        target = self._collections.get(collection)
        if target is None:
            raise StoreError(f"collection {collection!r} was not ensured")
        return int(target.count())


__all__ = ["ChromaVectorStore"]
