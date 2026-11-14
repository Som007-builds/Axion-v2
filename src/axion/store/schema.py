"""Neo4j schema v2 (constraints and indexes) for the P1 corpus.

The statements are idempotent (``IF NOT EXISTS``) and are applied on every
loader run. Schema v2 is designed for the V2 claim/context model, not ported
from V1 (ADR-0011).
"""

from __future__ import annotations

SCHEMA_VERSION = 2

SCHEMA_STATEMENTS: tuple[str, ...] = (
    "CREATE CONSTRAINT paper_pmcid_unique IF NOT EXISTS " "FOR (p:Paper) REQUIRE p.pmcid IS UNIQUE",
    "CREATE CONSTRAINT claim_id_unique IF NOT EXISTS " "FOR (c:Claim) REQUIRE c.claim_id IS UNIQUE",
    "CREATE CONSTRAINT context_id_unique IF NOT EXISTS "
    "FOR (c:CitationContext) REQUIRE c.ctx_id IS UNIQUE",
    "CREATE CONSTRAINT notice_id_unique IF NOT EXISTS "
    "FOR (n:RetractionNotice) REQUIRE n.notice_id IS UNIQUE",
    "CREATE INDEX paper_pmid_index IF NOT EXISTS FOR (p:Paper) ON (p.pmid)",
    "CREATE INDEX paper_doi_index IF NOT EXISTS FOR (p:Paper) ON (p.doi)",
    "CREATE INDEX paper_year_index IF NOT EXISTS FOR (p:Paper) ON (p.year)",
    "CREATE INDEX claim_run_index IF NOT EXISTS FOR (c:Claim) ON (c.run_id)",
    "CREATE INDEX context_citer_index IF NOT EXISTS " "FOR (c:CitationContext) ON (c.citer_pmcid)",
    "CREATE INDEX context_source_index IF NOT EXISTS "
    "FOR (c:CitationContext) ON (c.source_pmcid)",
)

SCHEMA_METADATA_STATEMENT = (
    "MERGE (s:SchemaVersion {version: $version}) "
    "SET s.applied_at = coalesce(s.applied_at, datetime())"
)


__all__ = [
    "SCHEMA_METADATA_STATEMENT",
    "SCHEMA_STATEMENTS",
    "SCHEMA_VERSION",
]
