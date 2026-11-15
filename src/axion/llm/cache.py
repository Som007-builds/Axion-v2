"""Persistent content-hash cache for LLM responses."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from axion.llm.models import LLMRequest

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    response TEXT NOT NULL,
    created_at TEXT NOT NULL
)
"""


@dataclass(frozen=True)
class CachedResponse:
    provider: str
    model: str
    text: str


def make_cache_key(request: LLMRequest, model: str) -> str:
    """Deterministic key over everything that changes model output."""
    schema = None
    if request.response_schema is not None:
        schema = request.response_schema.model_json_schema()
    payload = {
        "prompt": request.prompt,
        "system": request.system,
        "model": model,
        "temperature": request.temperature,
        "max_output_tokens": request.max_output_tokens,
        "response_schema": schema,
        "thinking_level": request.thinking_level,
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class SQLiteCache:
    """SQLite-backed response cache.

    The cache is intentionally separate from the ledger interface but can share
    the same database file. A cache hit is still recorded in the ledger by the
    client, at zero cost.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(_CREATE_TABLE)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self._path)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def get(self, cache_key: str) -> CachedResponse | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT provider, model, response FROM llm_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        if row is None:
            return None
        return CachedResponse(
            provider=str(row["provider"]),
            model=str(row["model"]),
            text=str(row["response"]),
        )

    def put(self, cache_key: str, *, provider: str, model: str, text: str) -> None:
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO llm_cache (cache_key, provider, model, response, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    provider = excluded.provider,
                    model = excluded.model,
                    response = excluded.response,
                    created_at = excluded.created_at
                """,
                (cache_key, provider, model, text, created_at),
            )

    def clear(self) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM llm_cache")

    def size(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM llm_cache").fetchone()
        return int(row[0]) if row is not None else 0
