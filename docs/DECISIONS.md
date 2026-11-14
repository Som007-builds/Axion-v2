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

## ADR-0008 — Scale approach: LLM-teacher distillation + cascade + lazy processing
**Date:** 2026-11-14 · **Status:** Accepted (owner instruction, 2026-11-14)
**Context:** Processing every paper with an LLM does not scale to a corpus of tens of millions of papers. The P1 baseline is intentionally LLM-heavy so it can act as a reference, but the production path must teach once, run cheap, escalate rarely, and process lazily. The project also needs an honest distinction between what is measured at a small scale and what is projected to a larger scale.

**Decision:** adopt a four-layer scale approach:
- **Layer 0 — deterministic.** JATS citation markers, sections, reference parsing, deduplication, and content-hash caching. No model calls.
- **Layer 1 — distilled students.** Use an expensive LLM as a **teacher** to produce **silver labels**, then train small encoder **students** for (a) "is this sentence a claim?" and (b) "does this citation context rely on the cited source claim?". The bulk of the corpus runs through students.
- **Layer 2 — rare escalation.** Low-confidence cases escalate to a small LLM, then a large LLM. Escalated cases become new training labels, so the escalation rate should fall over time (the flywheel).
- **Layer 3 — lazy/incremental.** Process each paper once (hash-cached), prioritize by risk (contexts citing flagged/retracted papers first), and leave the cold corpus unprocessed until needed.

**Simplified cost model:** `relative_cost ≈ s + e`, where `s` is student inference cost as a fraction of LLM-everywhere cost and `e` is the fraction of items escalated to an LLM. This is a planning model, not a measured law. The escalation rate `e` dominates the result and is therefore a first-class metric. Actual cost always comes from the ledger, never from this formula.
- **ASSUMPTION:** `s ≈ 0.01` is inspired by external work reporting roughly two orders of magnitude lower cost for distilled models on a *different* task. It is not our measurement.
- **ASSUMPTION:** `e` between `0.05` and `0.15` is a starting range to be measured; it is not observed data.
- **ASSUMPTION / arithmetic illustration:** ~10 claims per paper × an illustrative 20M-paper corpus ≈ 200M claims. At 384 dimensions × 4 bytes, 200M float32 embeddings would be ~300 GB. These are illustrative assumptions, not measured corpus facts. Do not embed the whole corpus at that scale; store only what the layered path needs.

**Owner-approved documentation scope:** this instruction explicitly authorizes the corresponding edits to `CONTEXT.md` §2.2, §3, §5, §6, §7, §10, and §15, plus the consistency edits in §8/§9/§12/§14/changelog, and the matching PRD, TODO, audit-rubric, architecture, and agent-protocol updates.

**Alternatives considered:**
- **LLM-everywhere:** simplest and highest possible quality ceiling, but cost is unacceptable at corpus scale.
- **Self-hosted large model only:** removes per-token API pricing but still needs substantial hardware/ops and does not remove the cost of running a large model on every item; keep as a backlog option.
- **Deterministic-only:** cheapest, but cannot handle fuzzy claim boundaries or citation reliance; insufficient as the whole system.

**Consequences:**
- New modules: `src/axion/train/` (silver labeling, student training, evaluation) and `src/axion/schedule/` (priority queue, incremental/hash-cached processing).
- Ledger/telemetry: teacher calls use stage `teacher_label`; escalations carry a parent-call link; training compute is recorded in a `training_runs` table; a projection script reads the ledger.
- Evaluation: silver labels train; gold human-audited labels evaluate. Splits are by **paper**, never by claim/context. The frozen gold test is the only basis for reported student quality.
- Reporting: the project reports measured structure at ~5k papers and projects to larger `N` with explicit ranges and assumptions. Projections are never presented as measurements.
- Added complexity: student training/evaluation, label management, and drift monitoring; student quality is capped by teacher error.

**Evidence (orientation; verify before citing):** metadata verified 2026-11-14 via the arXiv API and Crossref; findings are as reported by the authors and were not independently replicated by us.
- FrugalGPT (Chen, Zaharia, Zou), arXiv:2305.05176 — LLM cascades can match the best single LLM at lower cost on the tasks tested. [metadata verified; results external]
- *Distilling Large Language Models for Biomedical Knowledge Extraction: A Case Study on Adverse Drug Events*, arXiv:2307.06439 — distillation into a task-specific student reported gains over out-of-box LLMs with cost/efficiency advantages. [metadata verified; results external]
- MetaIE, arXiv:2404.00457 — a small tuned LM distilled from an LLM can be a strong starting point across information-extraction tasks; the authors report tuned small LMs outperforming prompted LLMs on the IE tasks tested. [metadata verified; results external]
- *Distilling Large Language Models for Efficient Clinical Information Extraction*, arXiv:2501.00031 — distilled encoder models reported much lower cost/latency than frontier LLMs on clinical NER. [metadata verified; results external]
- scite (Nicholson et al., *Quantitative Science Studies* 2021, doi:10.1162/qss_a_00146) — large-scale citation-statement classification into supporting/contrasting/mentioning; scite also surfaces retracted references in its product (verify current product behavior before citing). **This is prior art for citation-level classification; our novelty claim must be claim-level reliance + propagation, not "we classify citation statements."** [metadata verified; results external]

**Risks/limits:**
- Students may underperform on fuzzy claim boundaries; teacher errors propagate into silver labels.
- Domain/publisher drift requires retraining and monitoring.
- Label budget and human-audit capacity constrain the learning curve.
- Projections can overreach; every projection must show ranges, assumptions, and sensitivity to `s`, `e`, tokens/paper, and prices.
- The external studies are on different tasks; we do not claim to solve extraction at 20M-paper scale.

## ADR-0009 — Day-0 owner decisions (license, visibility, providers, budget)
**Date:** 2026-11-09 · **Status:** Accepted (owner-provided; revisit before P5)
**Context:** Day-0 required owner choices B1–B6 plus the provider/pricing policy for P1. Renumbered from provisional ADR-0008 on 2026-11-14 to reserve ADR-0008 for the owner-requested scale approach; the renumbering is recorded here and owner confirmation is requested in `_private/owner-action-sheet.md` (D0-O1).
**Decision:**
- **License:** MIT for now; revisit before P5. `LICENSE` added.
- **Visibility:** private until P5. Confirmed private on 2026-11-14 (unauthenticated GitHub API returned 404); local commits still need an owner push.
- **Providers/tiers:** both `small` and `large` tiers remain configurable; only one Groq provider/key is used for now. The fallback chain is `groq` until more providers are added. Model IDs live in `.env`, never in code.
- **Pricing:** `pricing.yaml` stays an empty template. P1 remains dry-run only and fails closed on missing prices. The owner will add verified prices before the first paid run (P1-10); agents must not guess or copy prices from memory.
- **Budget:** default **$0 paid usage**. Any paid batch needs explicit owner approval; the untracked `_private/budget.md` is set to zero.
- **Weekly hours:** owner reports open-ended/no fixed schedule; the earlier ~10 hrs/week default is superseded and is not a blocker.
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
