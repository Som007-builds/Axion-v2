"""Neo4j implementation of the schema-v2 corpus loader."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from axion.store.base import StoreConfigurationError, StoreError
from axion.store.schema import (
    SCHEMA_METADATA_STATEMENT,
    SCHEMA_STATEMENTS,
    SCHEMA_VERSION,
)

_BATCH_SIZE = 1_000

_PAPER_QUERY = """
UNWIND $rows AS row
MERGE (p:Paper {pmcid: row.pmcid})
SET p.pmid = coalesce(row.pmid, p.pmid),
    p.doi = coalesce(row.doi, p.doi),
    p.title = coalesce(row.title, p.title),
    p.year = coalesce(row.year, p.year),
    p.journal = coalesce(row.journal, p.journal),
    p.role = row.role,
    p.is_source = row.is_source,
    p.is_citer = row.is_citer,
    p.run_id = $run_id
"""

_NOTICE_QUERY = """
UNWIND $rows AS row
MERGE (n:RetractionNotice {notice_id: row.notice_id})
SET n.record_id = row.record_id,
    n.source = row.source,
    n.run_id = $run_id
WITH DISTINCT n, row
MATCH (p:Paper {pmcid: row.pmcid})
MERGE (p)-[r:RETRACTED_BY]->(n)
SET r.stage = 'rules', r.run_id = $run_id
"""

_CITES_QUERY = """
UNWIND $rows AS row
MATCH (c:Paper {pmcid: row.citer_pmcid})
MATCH (s:Paper {pmcid: row.source_pmcid})
MERGE (c)-[r:CITES]->(s)
SET r.contexts = row.contexts, r.stage = 'rules', r.run_id = $run_id
"""

_CONTEXT_QUERY = """
UNWIND $rows AS row
MATCH (citer:Paper {pmcid: row.citer_pmcid})
MATCH (source:Paper {pmcid: row.source_pmcid})
MERGE (c:CitationContext {ctx_id: row.ctx_id})
SET c.text = row.text,
    c.section = row.section,
    c.marker = row.marker,
    c.ref_id = row.ref_id,
    c.citer_pmcid = row.citer_pmcid,
    c.source_pmcid = row.source_pmcid,
    c.run_id = $run_id
MERGE (c)-[inside:IN_PAPER]->(citer)
SET inside.stage = 'rules', inside.run_id = $run_id
MERGE (c)-[points:POINTS_TO]->(source)
SET points.stage = 'rules', points.run_id = $run_id
"""

_SOURCE_CLAIM_QUERY = """
UNWIND $rows AS row
MERGE (claim:Claim {claim_id: row.claim_id})
SET claim.text = row.text,
    claim.section = row.section,
    claim.evidence_span = row.evidence_span,
    claim.claim_kind = row.claim_kind,
    claim.stage = 'rules',
    claim.run_id = $run_id
WITH DISTINCT claim, row
MATCH (source:Paper {pmcid: row.source_pmcid})
MERGE (claim)-[extracted:EXTRACTED_FROM]->(source)
SET extracted.stage = 'rules', extracted.run_id = $run_id
"""

_CANDIDATE_QUERY = """
UNWIND $rows AS row
MATCH (citer:Paper {pmcid: row.citer_pmcid})
MATCH (source:Paper {pmcid: row.source_pmcid})
MERGE (c:CitationContext {ctx_id: row.ctx_id})
SET c.text = row.text,
    c.paragraph_text = row.paragraph_text,
    c.section = row.section,
    c.paragraph_index = row.paragraph_index,
    c.sentence_index = row.sentence_index,
    c.marker = row.marker,
    c.ref_id = row.ref_id,
    c.citer_pmcid = row.citer_pmcid,
    c.source_pmcid = row.source_pmcid,
    c.source_claim_id = row.source_claim_id,
    c.run_id = $run_id
MERGE (c)-[inside:IN_PAPER]->(citer)
SET inside.stage = 'rules', inside.run_id = $run_id
MERGE (c)-[points:POINTS_TO]->(source)
SET points.stage = 'rules', points.run_id = $run_id
"""


class Neo4jBackend:
    """Thin, batch-oriented Neo4j adapter.

    The driver is imported lazily so the offline test suite does not require
    the optional store dependency.
    """

    def __init__(self, uri: str, username: str, password: str) -> None:
        try:
            from neo4j import GraphDatabase
        except ImportError as exc:
            raise StoreConfigurationError(
                "neo4j is not installed; install the 'store' extra from " "docs/LOCAL_SETUP.md"
            ) from exc
        self._driver: Any = GraphDatabase.driver(uri, auth=(username, password))

    def close(self) -> None:
        self._driver.close()

    def _write(self, query: str, **parameters: object) -> None:
        with self._driver.session() as session:
            session.execute_write(lambda tx: tx.run(query, **parameters).consume())

    def _batched_write(
        self,
        query: str,
        rows: Sequence[Mapping[str, object]],
        *,
        run_id: str,
    ) -> None:
        for start in range(0, len(rows), _BATCH_SIZE):
            self._write(query, rows=list(rows[start : start + _BATCH_SIZE]), run_id=run_id)

    def apply_schema(self) -> None:
        try:
            with self._driver.session() as session:
                for statement in SCHEMA_STATEMENTS:
                    session.run(statement).consume()
                session.run(SCHEMA_METADATA_STATEMENT, version=SCHEMA_VERSION).consume()
        except Exception as exc:  # neo4j exceptions are optional imports
            raise StoreError(f"could not apply Neo4j schema v{SCHEMA_VERSION}: {exc}") from exc

    def upsert_papers(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None:
        self._batched_write(_PAPER_QUERY, rows, run_id=run_id)

    def upsert_notices(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None:
        self._batched_write(_NOTICE_QUERY, rows, run_id=run_id)

    def upsert_cites(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None:
        self._batched_write(_CITES_QUERY, rows, run_id=run_id)

    def upsert_contexts(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None:
        self._batched_write(_CONTEXT_QUERY, rows, run_id=run_id)

    def upsert_source_claims(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None:
        self._batched_write(_SOURCE_CLAIM_QUERY, rows, run_id=run_id)

    def upsert_candidates(self, rows: Sequence[Mapping[str, object]], *, run_id: str) -> None:
        self._batched_write(_CANDIDATE_QUERY, rows, run_id=run_id)

    def count_nodes(self, label: str) -> int:
        with self._driver.session() as session:
            record = session.run(f"MATCH (n:{label}) RETURN count(n) AS n").single()
            return int(record["n"]) if record else 0

    def count_relationships(self, relationship: str) -> int:
        with self._driver.session() as session:
            record = session.run(f"MATCH ()-[r:{relationship}]->() RETURN count(r) AS n").single()
            return int(record["n"]) if record else 0

    def counts(self) -> dict[str, int]:
        return {
            "Paper": self.count_nodes("Paper"),
            "Claim": self.count_nodes("Claim"),
            "CitationContext": self.count_nodes("CitationContext"),
            "RetractionNotice": self.count_nodes("RetractionNotice"),
            "CITES": self.count_relationships("CITES"),
            "IN_PAPER": self.count_relationships("IN_PAPER"),
            "POINTS_TO": self.count_relationships("POINTS_TO"),
            "EXTRACTED_FROM": self.count_relationships("EXTRACTED_FROM"),
            "RETRACTED_BY": self.count_relationships("RETRACTED_BY"),
        }


__all__ = ["Neo4jBackend"]
