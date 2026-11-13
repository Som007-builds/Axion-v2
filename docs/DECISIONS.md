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

## ADR-0008 — Day-0 owner decisions (license, visibility, providers, budget)
**Date:** 2026-11-09 · **Status:** Accepted (owner-provided; revisit before P5)
**Context:** Day-0 required owner choices B1–B6 plus the provider/pricing policy for P1.
**Decision:**
- **License:** MIT for now; revisit before P5. `LICENSE` added.
- **Visibility:** private until P5. The GitHub repo is currently public; it must be switched to private before any push.
- **Providers/tiers:** both `small` and `large` tiers remain configurable; only one Groq provider/key is used for now. The fallback chain is `groq` until more providers are added. Model IDs live in `.env`, never in code.
- **Pricing:** `pricing.yaml` stays an empty template. P1 remains dry-run only and fails closed on missing prices. The owner will add verified prices before the first paid run (P1-10); agents must not guess or copy prices from memory.
- **Budget:** default **$0 paid usage**. Any paid batch needs explicit owner approval; the untracked `_private/budget.md` is set to zero.
- **Weekly hours:** not supplied; the Day-0 default (~10 hrs/week) applies until the owner states otherwise.
- **`_private/` backup:** the owner accepts **no backup** for now. This is an explicit exception to ADR-0006; losing that folder loses untracked notes/budget context.
**Consequences:** Day-0 can progress with offline/dry-run work; live provider calls remain blocked until keys, model IDs, and verified prices are supplied.

## ADR template
```
## ADR-XXXX — Title
Date · Status
Context:
Decision:
Alternatives considered:
Consequences:
```
