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

## ADR-0010 — One working branch per phase
**Date:** 2026-11-14 · **Status:** Accepted (owner instruction, 2026-11-14)
**Context:** The original rule created one branch per task (`p<phase>/<task-id>-<slug>`). That produced many short-lived branches, merge overhead at every task, and a handoff surface that was split across branches. The owner wants a simpler local workflow while keeping `main` green at task boundaries.

**Decision:**
- Use one working branch per phase: `p1`, `p2`, and so on, created from `main`.
- Do all tasks in the phase on that branch. Do not create per-task branches; pre-existing task branches and Day-0's `d0/build-ready` remain as history.
- Commit WIP as `wip: <task-id> <state>`; use Conventional Commits otherwise.
- Merge the phase branch into `main` at task boundaries **only** when lint, types, and tests are green. Never merge a red tree.
- Delete the phase branch after the phase gate is recorded on `main`.

**Alternatives considered:** keep one branch per task with PRs; work directly on `main`; use long-lived per-phase branches with no intermediate merges. Per-task branches added overhead without review value in a solo/agent workflow; working directly on `main` would lose the task-boundary checkpoint.

**Consequences:** fewer branches and simpler handoffs; `main` advances only at green task boundaries; the phase branch must be kept current with `main`; history is not rewritten and old branches are not deleted. Docs-only change: `CONTEXT.md` §8, `docs/AGENT_PROTOCOL.md`, phase TODO `branch:` fields, and the phase prompts.

## ADR-0011 — Rewrite the store layer in V2 (no V1 port)
**Date:** 2026-11-14 · **Status:** Accepted (owner instruction, 2026-11-14)

**Context:** P1-09 needs a Neo4j schema and Chroma loaders. The Day-0 audit identified five V1 store files that could be ported, but V1's graph was built for a different corpus and its provenance model predates the claim-level design. The owner has now chosen between porting those files and writing a clean V2 implementation.

**Decision:** Implement P1-09 as a clean V2 rewrite. Do not port V1 store code. Use CONTEXT §7.3 for constraints/indexes and the claim/context model in `docs/ARCHITECTURE.md`.

**Alternatives considered:** port the V1 files and adapt them; hybrid (schema from V1, loaders rewritten). A port would import assumptions that P1-05/P1-10 do not share and would require auditing code the project is not otherwise keeping.

**Consequences:** no V1 provenance questions for the store layer; the schema is designed against the V2 parser and claim model. The five V1 paths no longer block P1-09. V1 remains a read-only reference for benchmark and migration-map descriptions only.

## ADR-0012 — P1 sub-topic: infectious disease
**Date:** 2026-11-14 · **Status:** Accepted (owner decision, 2026-11-14), with conditions recorded below

**Context:** P1-07 needs a sub-topic that clears the CONTEXT §4 minimums: at least **30 retracted OA source papers with full text** and at least **300 citation contexts**. The owner delegated the shortlist and asked for 3-5 candidates measured with scripts, including one non-obvious candidate, chosen by the criteria rather than topic appeal. The PRD also targets a **2,000-5,000 paper corpus total, including citers** (ADR-0013 settles the bound). This ADR reports both the retracted-source estimate and the sources-plus-citers estimate.

**Method:** Five Retraction Watch subject categories were fixed in advance (`scripts/feasibility_spike.py`, seed `20261114`). For each, the script took a seeded sample of 300 linkable retractions, batch-resolved them through Europe PMC, sampled up to 20 OA source papers, fetched their citation lists, batch-resolved up to 200 MEDLINE citers, and fetched JATS for up to 10 citer/source pairs to count contexts. Reference matching used DOI, PMID, or normalized title + year; the citer list came from Europe PMC's citations endpoint, not reference-list matching alone. Estimates multiply independent measured rates; ranges combine independent Wilson bounds and are not a joint CI. Full detail: `docs/reports/P1-feasibility.md` and `P1-feasibility.json`.

**Measured results (point estimate; lower-upper range):**

| Candidate | Est. OA sources | Est. contexts | Est. corpus | Minimums at lower bound |
| :-- | --: | --: | --: | :-- |
| Oncology | 2,143 (1,921-2,360) | 14,926 (12,021-17,962) | 17,069 | pass |
| Cardiovascular | 1,244 (1,103-1,385) | 3,230 (2,543-3,914) | 6,628 | pass |
| **Infectious disease** | **741 (653-829)** | **4,409 (3,498-5,332)** | **4,749** | **pass** |
| Gastroenterology | 910 (822-994) | 10,274 (8,510-12,121) | 11,184 | pass |
| Rehabilitation/Therapy | 825 (733-918) | 6,958 (5,451-8,655) | 6,624 | pass |

All five clear both minimums at the lower bound. Rehabilitation/Therapy was the non-obvious candidate and passed comfortably, so the data would support a smaller clinical field too.

**Decision (accepted):** Use **`(HSC) Medicine - Infectious Disease`** as the P1 sub-topic. The 2,000-5,000 bound is the **total** ingested corpus including citers (ADR-0013), so infectious disease is the only passing candidate whose estimate (≈4,749 papers) stays inside the target, while clearing the mandatory minimums by wide margins (≥653 sources, ≥3,498 contexts).

**Owner conditions:**
- P1-08 must produce **exact** counts. If either exact count falls below the CONTEXT §4 minimums (≥30 retracted sources, ≥300 contexts), stop and propose the fallback via a new **Proposed** ADR; do not proceed silently.
- **Oncology is deferred** as a later held-out transfer corpus, to be approved by its own ADR. The P1-08 manifest must treat the sub-topic as configuration, so adding oncology later is a config change rather than a code change.
- P1-08 must report the **PMID gap** and state that blast-radius recall is capped by MEDLINE-only citer discovery (Europe PMC's citations endpoint is PMID-based).

P1-08 ingests the Retraction Watch retracted papers in that subject plus all discoverable OA citers, up to the ~5,000 hard cap.

**Alternatives considered:**
- **Oncology** gives the largest context margin (≥12,021) but implies ~17k papers, far outside the corpus target. It is **deferred as a later held-out transfer corpus**, to be approved by its own ADR; it is not a P1 fallback unless P1-08's exact counts fail the minimums.
- **Gastroenterology** has the highest measured OA-source rate (176/300) but ~11k papers.
- **Cardiovascular** and **Rehabilitation/Therapy** pass but imply ~6.6k papers.
- A narrower cross-category slice (for example, a specific MeSH term or journal set) was not chosen now because it would add an unmeasured definition; it remains an option if the owner rejects all five.

**Consequences:** P1-08 builds the corpus from a config file so a later oncology run is a config change. The manifest records the RW subject tag, RW snapshot commit, Europe PMC resolution rules, citation direction, OA/full-text filter, cap, and PMID gaps. Exact counts replace the sampling estimates; the estimates suggested comfortable margins, but P1-08 must verify them. The Europe PMC citations endpoint accepts a MEDLINE id (`MED/<pmid>/citations`); `PMC/<pmcid>/citations` returns 404 (verified live), so PMIDs must be resolved first. Papers without a PMID cannot have their citers discovered, which caps blast-radius recall; P1-08 reports that gap explicitly.

## ADR-0013 — P1 corpus bound is the total, citers included
**Date:** 2026-11-14 · **Status:** Accepted (owner decision, 2026-11-14)

**Context:** CONTEXT §4 and PRD P1.8 previously said “2,000–5,000 papers … plus all discoverable citers”, which could mean either (a) 2,000–5,000 total including citers or (b) 2,000–5,000 base papers with citers added. The two readings imply different sub-topic choices and different ingestion volumes. The owner has settled it.

**Decision:** The 2,000–5,000 bound is the **total corpus including retracted sources and all discoverable citers**, with a hard cap of ~5,000 papers. Remove the ambiguity from CONTEXT and PRD. P1-08 selects sources first, then citers deterministically, and stops at the cap.

**Alternatives considered:** base-papers-only bound with citers added (would favor oncology and produce ~17k papers); no cap (rejected as unbounded cost/disk).

**Consequences:** P1-08 reports exact counts against the cap. If sources plus discoverable OA citers exceed ~5,000, citers are truncated deterministically and the manifest records the truncation; context counts are then a lower bound. The P1-08 manifest must make the inclusion rule explicit so a later oncology corpus can reuse it via config.

## ADR-0014 — P1-10 baseline extraction is a seeded paper sample
**Date:** 2026-11-14 · **Status:** Accepted (owner decision, 2026-11-14)

**Context:** P1-10 originally implied running one large model over the full corpus. That is unnecessary for a baseline and exposes the project to avoidable spend; the audit only needs ≥200 claims with margin.

**Decision:** Run the baseline extractor on a **seeded sample of papers**, not the full corpus. Size the sample from a dry-run cost estimate so the expected output is **≥200 claims with margin** (target ~300+), record the seed and sampling rule, and persist provenance (`teacher model/version`, prompt version, `run_id`) for every claim. Full-corpus extraction is not a P1 goal.

**Alternatives considered:** full-corpus extraction (higher cost, no evaluation benefit at this stage); extract only from retracted sources (too few claims, no citer-side baseline).

**Consequences:** P1-10 must present a dry-run cost estimate and sample plan before any paid call. The sample is drawn at the paper level so the audit split remains paper-level. The report must distinguish claims from the sampled papers and state the sampling fraction; it must not generalize precision to the full corpus without noting the sample.

## ADR template
```
## ADR-XXXX — Title
Date · Status
Context:
Decision:
Alternatives considered:
Consequences:
```
