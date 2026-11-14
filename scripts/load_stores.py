"""Load the P1 corpus manifest into Neo4j schema v2 and Chroma.

Usage:
    python scripts/load_stores.py --manifest docs/reports/P1-corpus-manifest.json --twice

The loader is idempotent: stable node IDs and MERGE/upsert semantics mean a
second run leaves identical counts. Use ``--in-memory`` for a dependency-free
smoke test; the real run needs the optional store extras and a running Neo4j.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from axion.config.settings import Settings
from axion.store.base import StoreConfigurationError
from axion.store.chroma import ChromaVectorStore
from axion.store.embeddings import build_embedder
from axion.store.loader import LoadResult, dump_result, load_bundle
from axion.store.memory import InMemoryGraph, InMemoryVectorStore
from axion.store.neo4j import Neo4jBackend

DEFAULT_MANIFEST = Path("docs/reports/P1-corpus-manifest.json")


def _print_result(label: str, result: LoadResult) -> None:
    print(f"{label}:")
    print(dump_result(result), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--chroma-dir", type=Path, default=None)
    parser.add_argument(
        "--embedder",
        choices=("hash", "sentence-transformers"),
        default="hash",
        help="hash is offline plumbing; sentence-transformers is for real retrieval",
    )
    parser.add_argument(
        "--in-memory",
        action="store_true",
        help="use in-memory stores (dependency-free smoke test)",
    )
    parser.add_argument(
        "--twice",
        action="store_true",
        help="load twice and fail if the counts differ",
    )
    parser.add_argument(
        "--allow-missing-fulltext",
        action="store_true",
        help="load IDs even when the raw full-text cache is incomplete",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    cache_dir = args.cache_dir or settings.resolved_europepmc_cache_dir
    if args.in_memory:
        graph = InMemoryGraph()
        vectors = InMemoryVectorStore()
    else:
        if not settings.neo4j_uri or not settings.neo4j_password:
            raise StoreConfigurationError(
                "set NEO4J_URI and NEO4J_PASSWORD in .env, or use --in-memory"
            )
        graph = Neo4jBackend(
            settings.neo4j_uri,
            settings.neo4j_username or "neo4j",
            settings.neo4j_password.get_secret_value(),
        )
        data_dir = settings.data_dir or Path("data")
        vectors = ChromaVectorStore(args.chroma_dir or data_dir / "chroma")
    embedder = build_embedder(args.embedder)

    try:
        first = load_bundle(
            args.manifest,
            graph=graph,
            vectors=vectors,
            embedder=embedder,
            cache_dir=cache_dir,
            require_fulltext=not args.allow_missing_fulltext,
        )
        _print_result("load 1", first)
        if args.twice:
            second = load_bundle(
                args.manifest,
                graph=graph,
                vectors=vectors,
                embedder=embedder,
                cache_dir=cache_dir,
                require_fulltext=not args.allow_missing_fulltext,
            )
            _print_result("load 2", second)
            if (
                first.graph_counts != second.graph_counts
                or first.vector_counts != second.vector_counts
            ):
                print(
                    "NOT IDEMPOTENT: counts changed between loads",
                    file=sys.stderr,
                    flush=True,
                )
                return 1
    finally:
        graph.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
