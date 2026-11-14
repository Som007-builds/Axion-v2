"""Deterministic and sentence-transformers embeddings for Chroma.

``HashEmbedder`` is an offline plumbing default: it needs no model download and
is stable across runs, but it is not a semantic model. Production retrieval
should use ``SentenceTransformerEmbedder`` with the CPU-only install described
in ``docs/LOCAL_SETUP.md``.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Sequence
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9]+")
DEFAULT_DIMENSION = 384
DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class EmbeddingError(Exception):
    """Raised when an embedder cannot be constructed or used."""


class Embedder(Protocol):
    name: str
    dimension: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class HashEmbedder:
    """Hashed token bag, L2-normalized.

    This is deliberately simple and deterministic so tests and dry runs do not
    need a model download. It preserves lexical overlap, not meaning.
    """

    name = "hash-384-v1"
    dimension = DEFAULT_DIMENSION

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimension
            for token in _TOKEN.findall(text.lower()):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimension
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vector[index] += sign
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class SentenceTransformerEmbedder:
    """Local MiniLM embeddings on CPU; imports the optional model lazily."""

    name = DEFAULT_MODEL
    dimension = DEFAULT_DIMENSION

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise EmbeddingError(
                "sentence-transformers is not installed; install the CPU-only "
                "extras from docs/LOCAL_SETUP.md or use --embedder hash"
            ) from exc
        self._model = SentenceTransformer(model_name, device="cpu")
        dimension = self._model.get_sentence_embedding_dimension()
        if dimension is not None:
            self.dimension = int(dimension)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors = self._model.encode(
            list(texts),
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [list(map(float, vector)) for vector in vectors]


def build_embedder(name: str) -> Embedder:
    if name == "hash":
        return HashEmbedder()
    if name in {"sentence-transformers", "minilm"}:
        return SentenceTransformerEmbedder()
    raise EmbeddingError(f"unknown embedder {name!r}; use 'hash' or 'sentence-transformers'")


__all__ = [
    "DEFAULT_DIMENSION",
    "DEFAULT_MODEL",
    "Embedder",
    "EmbeddingError",
    "HashEmbedder",
    "SentenceTransformerEmbedder",
    "build_embedder",
]
