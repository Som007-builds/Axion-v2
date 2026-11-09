# Architecture & Project Decision Records (ADRs)

Status values: `Proposed` · `Accepted` · `Superseded` · `Rejected`. Agents may add `Proposed` entries; only the owner marks `Accepted`.

---
## ADR-0001 — Separate clean repo, no V1 history
**Date:** 2026-11-09 · **Status:** Accepted
**Context:** V1 mixed experiments, obsolete datasets, and broad scope. **Decision:** start a clean repo; port selected files with provenance; do not import history. **Consequences:** cleaner story and security hygiene; some rework of ported code.

## ADR-0002 — Domain: open-access biomedical literature (Europe PMC, JATS)
**Date:** 2026-11-09 · **Status:** Accepted, subject to P1 feasibility spike
**Context:** retractions are common in biomedical journals and rare in arXiv ML; JATS gives deterministic citation contexts. **Decision:** biomedical OA via Europe PMC; sub-topic chosen in P1. **Consequences:** V1's ML benchmark becomes legacy-only; need retraction data coverage check.

## ADR-0003 — Two bets: claim-level blast radius + cost as first-class metric
**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** every phase reports quality and cost; headline results are cost/paper reduction, $/retraction analyzed, and false-alarm reduction vs citation-level.

## ADR-0004 — Stack: Neo4j + ChromaDB + SQLite ledger, Python 3.11, FastAPI
**Date:** 2026-11-09 · **Status:** Accepted
**Rationale:** blast radius is graph traversal (Neo4j); local embeddings (Chroma) keep cost zero; SQLite ledger is portable and inspectable. Redis/RQ deferred.

## ADR-0005 — Demand-driven expansion from flagged papers
**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** expensive processing runs only on citing contexts of retracted/flagged papers; cost scales with retractions, not corpus size.

## ADR-0006 — Untracked `_private/` folder for non-public dev assistance
**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** budget, outreach, call notes, agent prompts, and scratch live in a gitignored folder; tracked docs must not reference its content; back it up separately.

## ADR-0007 — Deterministic first (JATS xrefs, rules) before any model
**Date:** 2026-11-09 · **Status:** Accepted
**Decision:** use deterministic extraction wherever possible; LLMs only where a cheaper stage cannot decide.

## ADR template
```
## ADR-XXXX — Title
Date · Status
Context:
Decision:
Alternatives considered:
Consequences:
```
