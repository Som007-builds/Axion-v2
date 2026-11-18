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

## ADR-0015 - P1 blast-radius counts are conditional on the included citer set
**Date:** 2026-11-15 - **Status:** Proposed (owner instruction to record; approval pending)

**Context:** P1-08 selected 4,168 citers under a ~5,000-paper total cap. Link coverage is uneven: 285 of 792 source papers have an incoming citer edge and 507 do not; 34 citer papers have no outgoing edge and 533 papers have no edge. The cap truncated 5,734 eligible citers. A count computed on this graph therefore describes the included corpus, not all literature that cites the retracted sources.

**Decision:** P1 blast-radius numbers are reported **within the included citer set only**. Do not silently reinterpret a zero as "no citations exist" or a component size as a complete literature count. Expanding citers on demand is **deferred to P3**; P1 does not add a second citer-discovery pass. Reports must state the included-set denominator and the cap/truncation caveat next to each blast-radius number.

**Alternatives considered:** re-ingest with one citer per source to improve source coverage (changes the sampled corpus after the P1 baseline; needs owner approval and another full ingest); expand citers on demand now (scope creep and extra cost before P3); present the counts as complete (misleading given the measured coverage gaps).

**Consequences:** P1 can finish with the existing graph and a clearly bounded claim. P3 must add query-time citer expansion (or an approved re-ingest) before any statement about the full citation literature. The 507 isolated sources and 5,734 truncated citers remain recorded in `docs/reports/P1-corpus-coverage.{md,json}`.

## ADR-0016 - P1-11 agreement: self-relabel or independent second labeler
**Date:** 2026-11-15 - **Status:** Accepted (owner supplied the independent second-labeler overlap, 2026-11-16)

**Context:** P1-11 needs an agreement statistic in addition to precision and its Wilson CI. The owner is the only labeler today, and a single-labeler audit cannot measure intra- or inter-labeler agreement. Labeling a second full sample is expensive.

**Decision:** Measure agreement in one of two ways, chosen before labels are inspected:
- **Self-relabel (default):** after **at least 7 days**, the owner relabels a seeded 10% blind into `relabel_label` without looking at `label`.
- **Independent second labeler (optional):** a second person labels a seeded 20% overlap blind. `scripts/audit_sample.py --overlap-out` exports that subset with the exact audit columns; `scripts/audit_validate.py --overlap` merges it into `relabel_label`.

Either path reports raw agreement and Cohen's kappa through the existing metrics code. The overlap is selected by a seeded SHA-256 rank over `claim_id`, so it is reproducible and adds no hidden column to the audit CSV. Labels remain the owner's (or the approved second labeler's); the agent does not label.

**Alternatives considered:** skip agreement and report precision only (weaker audit); have the agent label a second time (not independent and violates the blind human audit); label the whole sample twice (unnecessary cost).

**Consequences:** The first agreement number waits at least 7 days or for a second labeler. The overlap CSV is a separate file and must not be merged back into the primary labels; it only supplies `relabel_label`. The tool stores second-labeler work under a separate browser-storage key.

**Outcome (2026-11-16):** the owner used the independent-second-labeler path. The seeded 40-claim (20%) overlap was labelled by `friend`; all 40 claims were `CORRECT` in both the primary and second-label sets, so raw agreement is **100.0%**. Cohen's kappa is **not estimable** because both sets used a single label (zero variance), and the overlap contains none of the 7 primary `NOT_A_CLAIM` rows. The statistic therefore does not estimate agreement on the error class; it is recorded as a weak but complete agreement check in `docs/reports/P1-audit.md`.

## ADR-0017 — P1 baseline switches from Groq to the Gemini free tier
**Date:** 2026-11-15 — **Status:** Accepted (owner decision, 2026-11-15); amended by ADR-0019 (baseline model)

**Context:** The Groq free tier (8,000 TPM / 200,000 TPD) could not complete the 5-paper pilot: after one paper, a 12,111-token request exceeded TPM and the client stopped cleanly. Raising the Groq tier would spend real money, while the P1 goal is a measured baseline at **$0 real spend**. Google AI Studio offers both chosen Gemini models on a free tier.

**Decision:** Switch the P1-10 baseline provider to **Google Gemini via the official `google-genai` SDK**, using `gemini-3.8-flash` as the large tier and `gemini-3.5-flash-lite` as the small tier. Both model IDs are official. Use SDK JSON-schema structured output, still validate with Pydantic, and map `thoughts_token_count` into the existing reasoning-token accounting. Keep `groq==1.7.0`, `src/axion/llm/groq.py`, and its tests in the repo, unused. Do not enable billing; real spend remains $0. Free-tier calls record the list price in the ledger with `billing=free_tier`, and reports show both the call-date price and the post-promotion price.

**Pricing:** Official Google list prices, checked 2026-11-15:
- `gemini-3.8-flash`: $0.75 input / $3.75 output / $0.075 cached input per 1M tokens through 2026-12-31 (introductory); $1.50 / $7.50 / $0.15 from 2027-01-01.
- `gemini-3.5-flash-lite`: $0.30 / $2.50 / $0.03 per 1M tokens.
- Both models show “Free of charge” on the free tier.

Sources: <https://ai.google.dev/gemini-api/docs/pricing>, <https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash>, <https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite>, <https://ai.google.dev/gemini-api/docs/rate-limits>, <https://ai.google.dev/gemini-api/docs/thinking>.

**Rate limits and pacing:** The owner’s AI Studio snapshot (2026-11-15) gives `gemini-3.8-flash` **5 RPM / 250K TPM / 20 RPD** and `gemini-3.5-flash-lite` **15 RPM / 250K TPM / 500 RPD**. RPD resets at midnight `America/Los_Angeles`. The runner enforces a conservative RPM gap and a daily-cap margin (18/day for the 20-RPD model), stops cleanly on the first daily-quota or `RESOURCE_EXHAUSTED` error, and resumes across days without retrying tightly.

**Fixed baseline generation config:** temperature **0.0**, max output tokens **8192**, thinking level **medium**. The prompt stays `claim-extraction-v1` unless the Gemini pilot shows paraphrase dominates; thinking effort is a P2 cost lever, not a P1 variable.

**Alternatives considered:** upgrade Groq to a paid tier (violates $0 real spend); keep Groq and sample only prompts under 8K tokens (a scope/sampling change and still exceeds the daily cap); use a local model (not provider-hosted, different baseline); leave the SDK unpinned (reproducibility risk).

**Consequences:** `google-genai==2.8.0` is pinned (outside the 14-day window and compatible with `pydantic==2.10.4`; `2.9.0` requires `pydantic>=2.12.5` and was rejected). The ledger records provider, model, prompt version, run_id, billing, price version, generation config, input/output/post-promotion cost, and reasoning tokens. The Groq adapter remains tested history. A 20-RPD limit means the 100-paper sample takes about six days at ~18 requests/day, so runs are resumable and stop at a clean daily boundary.

### ADR-0017 amendment — 2026-11-15 — failure capture, output budget, retry policy

**Status:** Accepted (owner instruction, 2026-11-15).

The first Gemini pilot attempt produced no claims. The ledger records **10 attempts and 0 successes** for run `p1-10-gemini-pilot-s20261114-n5`: one HTTP 400 `INVALID_ARGUMENT` (`additional_properties` in `response.schema`), one HTTP 504 `DEADLINE_EXCEEDED`, and eight HTTP 503 `UNAVAILABLE`. None was an output-budget exhaustion, but the run report could only say “all LLM providers failed”, and those 10 attempts used half of the 20-request day.

Changes:
- **Output budget:** `max_output_tokens` 8192 → **16384**; thinking level stays **medium** and is recorded in the ledger, the silver manifest, and the run report. The minimal probe that returned no text at `max_output_tokens=16` is an output-budget artifact and is not evidence about the pilot.
- **Empty responses are not retried.** `finish_reason=MAX_TOKENS` with no text is `OutputTokenExhaustedError` (permanent **with unchanged parameters**: raise the budget or lower thinking, do not re-call). A safety/recitation block and any other empty body are permanent too.
- **Retry policy:** retry **only** network/5xx/504 failures, at most once (`DEFAULT_MAX_ATTEMPTS = 2`). A 429 or `RESOURCE_EXHAUSTED` and a daily-quota error stop the run at a checkpoint. Every attempt — including a retry — passes through the free-tier pacer, so quota counting cannot drift.
- **Root-cause provenance:** every provider failure records a sanitized error class, message, HTTP status, provider status, finish reason, known token usage, and attempt count in the ledger, `failures.jsonl`, and the run report. Credential-shaped strings are redacted before persistence; the API key never enters a record.

Diagnosis report: `docs/reports/P1-gemini-pilot-diagnosis.md`, regenerated by `python scripts/failure_report.py`.

## ADR-0018 — Audit export is capped per paper and must cover at least 40 papers

**Date:** 2026-11-15 — **Status:** Accepted (owner instruction, 2026-11-15)

**Context:** Drawing 200 claims uniformly can concentrate them in a handful of papers. Claims from one paper share a source and context and are not independent, so a Wilson interval over them is too narrow and the audit's evidence is overstated.

**Decision:** The official ≥200-claim audit export is seeded, uses **at most 5 claims per paper**, covers **at least 40 distinct papers**, and keeps the paper-level dev/test split. The export records how many papers and claims it covers. Audit metrics report a **paper-level cluster bootstrap** interval alongside Wilson and state the dependence limitation. Papers processed after the export remain extra silver labels and are not added to the official audit.

**Consequences:** The export requires at least 40 papers with accepted claims; 200 claims at 5 per paper aligns the cap and the paper minimum. The cluster interval is wider and more honest than Wilson, and with ~40 clusters it is still imprecise — that is reported, not hidden. P1-10 must therefore yield claims from ≥40 papers, not merely 200 claims.

## ADR-0019 — P1 baseline model moves to `gemini-3.5-flash-lite`

**Date:** 2026-11-15 — **Status:** Accepted (owner decision, 2026-11-15). Amends the model ladder in ADR-0017.

**Context:** `gemini-3.8-flash` allows only **20 requests/day** on the owner's AI Studio account and returned HTTP 503/504 on every pilot attempt, including a fixed schema. At 20 RPD the seeded 100-paper sample would take about six days and any retry or transient error costs 5% of a day. `gemini-3.5-flash-lite` has the same TPM ceiling, **15 RPM and 500 RPD**, which fits the P1 goal of a measured baseline at $0 real spend.

**Decision:**
- **P1 baseline model = `gemini-3.5-flash-lite`.** One model on all baseline sections; tier `small` in the ledger, model ID recorded explicitly.
- **`gemini-3.8-flash` remains the “large”/escalation reference model**, used only on small subsets (for example, an optional 5-paper reference comparison), never as the P1 baseline and never as silver labels for that comparison.
- Free tier only, billing **off**; calls record list price with `billing=free_tier` and real spend stays $0.

**Limits and pacing:** `gemini-3.5-flash-lite` **15 RPM / 250K TPM / 500 RPD**, runner cap **450/day with a 50-request margin**, resets at midnight `America/Los_Angeles`. Every attempt, including a retry, passes through the pacer. Retry only network/5xx at most once; a 429/`RESOURCE_EXHAUSTED` or daily-quota error stops at a checkpoint (ADR-0017 amendment).

**Generation config (fixed, not tuned):** SDK **default thinking behaviour — no `thinking_config` is sent**; the ledger, silver manifest, and run report record the literal value `default`. `max_output_tokens` **16,384**, temperature **0.0**, prompt `claim-extraction-v1`. The runner takes thinking from `--thinking-level` (default `default`) and does not read `LLM_THINKING_LEVEL` for the P1 baseline; that variable remains for other stages.

**Pricing (checked 2026-11-15):** `gemini-3.5-flash-lite` is **$0.30 input / $2.50 output / $0.03 cached input per 1M tokens** on the paid tier and **“Free of charge”** on the free tier; Google prints no post-2026-12-31 change for this model. Source: <https://ai.google.dev/gemini-api/docs/pricing>. `pricing.yaml` already carries this dated version; only its comment was clarified.

**P2 small tier and bulk labeler — Proposed, not decided:** candidates are `gemini-3.1-flash-lite` and **Gemma 4 26B/31B** (owner's AI Studio limits: 30 RPM, **16K TPM**, 14.4K RPD). Untested for our use: Gemma's structured-output and system-instruction support, whether 16K TPM is workable for ~7.6K-token extraction prompts, and its lack of a published list price (a documented reference price would be required before any cost claim). No P2 choice is made here.

**Consequences:** The 100-paper sample fits in about one day under the 450/day cap instead of six days, so the baseline and then the audit export can proceed. A model change mid-baseline is forbidden without a new ADR; the 3.8 Flash reference comparison is optional, explicitly labelled **reference**, and skipped if it returns 503/504. ADR-0017's fixed config (8192 output, thinking `medium`) is superseded.

**Measured outcome (2026-11-15, run `p1-10-flashlite-s20261114-n100`):** the seeded sample completed at **100/100 papers and 765 accepted silver claims** in one day: **120 Flash-Lite requests** of the 450/day cap, **$0 real spend**. Evidence-span verbatim rate **88.7%** (97 rejected spans), **0 parse failures**, and 11 claims named a section the baseline document does not contain. The strict pre-normalization rate was identical, so normalization fixed nothing on this model. Tokens: **697,734 prompt / 142,057 completion, 0 thinking**, total 839,791; list price **$0.564459**, i.e. **$0.005645 per paper** and **$0.000738 per accepted claim**; output tokens were **62.9%** of list price. Latency mean 6,448 ms, p95 15,490 ms. Prompt-token estimate vs real: **-8.7%** (764,084 estimated). Artifacts: `eval/silver/claims_v1/baseline_flashlite/` (`run_report.md`, `run_report.json`, `silver_manifest.json`, `strict_state.json`); official audit export `eval/audit/claims_audit_v1.csv` (200 claims, 45 papers, ≤5 per paper, seed 20261114, 22 dev / 23 test papers). The SDK-default thinking setting produced **zero reasoning tokens** on every call, so the token estimate needed no thinking adjustment.

**Reference comparison (2026-11-15, `p1-10-ref-flash38-s20261114-n5`, not baseline, not silver):** the first 5 seeded papers ran once on `gemini-3.8-flash` with the same prompt/config: **74 claims, 0 span failures (100% verbatim)**, 28,087 prompt / 22,073 completion tokens of which **9,177 were thinking**, list price **$0.103838** (**$0.001403 per claim**, 1.9× Flash-Lite) and latency mean **196,588 ms**, p95 **290,982 ms** (≈30× slower), using 17 of its 18 allowed daily requests. It is a small non-random comparison, not a quality verdict.

**Failure policy as exercised:** one paper returned HTTP 503 `UNAVAILABLE` twice and another returned a TLS `ReadError` (`SSLV3_ALERT_BAD_RECORD_MAC`). TLS/socket read failures are now classified as transient (one retry) and an isolated provider failure is recorded and skipped instead of ending the batch; the run stops only after **three consecutive** provider failures, and a 429/daily-quota error still stops it immediately. Both papers were recovered by later resumes; 20 of the 120 requests were failed attempts.

## ADR-0020 — P2 measurement definition, model ladder, and silver-label budget

**Date:** 2026-11-16 — **Status:** Proposed (owner instruction at P2 kickoff, 2026-11-16)

**Context.** The P2 TODO and PRD were written before P1 measured anything. Since then: the provider
changed to the Gemini free tier (ADR-0017), the baseline model was fixed (ADR-0019), and the gold
audit measured **precision only** on 200 claims from 45 papers. Free-tier daily request caps make
"label the unlabeled corpus" impossible, and the P2 TODO did not define what a non-baseline
configuration can be scored on. This ADR records the amended P2 reality so the phase can run
without silently changing the targets. Task IDs stay stable.

**Decision.**

1. **Provider and model ladder stay as measured, and the P1 baseline is frozen.** Provider: Gemini
   free tier via AI Studio. `gemini-3.5-flash-lite` (15 RPM / 250K TPM / 500 RPD, runner cap
   450/day) remains the P1 baseline and the bulk teacher. `gemini-3.8-flash` (5 RPM / 20 RPD)
   remains the large/escalation reference only. Billing stays off; real spend stays $0; the ledger
   records list price.
2. **Candidate small tiers are tested, not adopted.** Candidates are `gemini-3.1-flash-lite` and
   Gemma 4 (`gemma-4-26b-a4b-it`, `gemma-4-31b-it`; owner-supplied 30 RPM / 16K TPM / 14.4K RPD).
   Their structured-output support, prompt-size fit, and list prices are **unknown**. Test on small
   samples; report evidence; **ask the owner before adopting either as the small tier.** No
   pricing entry is invented. A model with no price cannot support a cost claim.
3. **P2 quality is three separate measurements, and every report states their limits.**
   - **(a) Precision on gold dev/test.** The gold set labels 200 baseline claims from 45 papers.
     A configuration is scored only on output that aligns with a gold-labelled baseline claim
     (same verbatim span, or the sentence containing it for a sentence-level student). Precision
     is `CORRECT / aligned`. Output that aligns with nothing in the gold set is **unverifiable**
     and is reported as a separate count and rate, never counted as correct.
   - **(b) Retention / agreement relative to the baseline's own claims.** Fraction of the 200 gold
     claims the configuration still emits. This is **not recall**: the baseline's own recall is
     unknown, so a configuration can score 100% retention and still miss most real claims.
   - **(c) Cost**, from the ledger, reported with (a) and (b). Student inference cost is local
     compute; `s` uses an explicit, stated $/CPU-hour assumption and is labelled an
     **ASSUMPTION**, with the ledger's API cost ($0 on the free tier) reported separately.
   - Absolute recall is **unmeasured** in P2. No P2 report may claim a recall number.
4. **Splits and training exclusion.** Gold dev (22 papers) is for tuning only; gold test (23
   papers) is frozen for reporting. Student training uses only papers **outside** the 45 gold
   papers. Silver labels train; gold labels evaluate; splits are by paper. No tuning on test; no
   student evaluated on teacher-labelled data.
5. **Silver labelling is a sample, sized by a learning curve.** Daily caps (450 requests/day for
   the baseline teacher) forbid corpus-wide labelling. P2 labels a seeded sample of corpus papers
   excluding the 45 gold papers, records the sample size and seed, and justifies the size by a
   measured learning curve over geometric label budgets. The curve, not an arbitrary total, sets
   where labelling stops. Unlabelled papers stay cold.
6. **Escalation and batching are measured as levers, including negative results.** Batching may
   reduce requests without reducing tokens; that is a reportable negative result. Escalation to the
   large model is capped by its 20-RPD limit and is reported even when it is too sparse to estimate
   a quality effect.
7. **Structured claim fields are outside the P2 gold measurement.** The gold audit scores claim
   identity and correctness, not `claim_type`/population/direction fields. A sentence-level student
   that emits `claim_type="other"` is reported as such; field fidelity is a P3+ concern.
8. **Projection.** `scripts/cost_model.py` reads the ledger and prints **MEASURED** and
   **PROJECTED** sections separately, with ranges and assumptions. A projection is never a
   headline measured result.

**Alternatives considered:** relabel the corpus (owner labelling time, and would not fix the
recall gap); treat unverifiable student output as correct (dishonest); use gold test for lever
tuning (leaks the frozen split); label all 4,928 papers with the teacher (exceeds daily caps and
spends weeks); adopt Gemma without a price (no cost claim).

**Consequences:** P2 reports carry three quality numbers plus unverifiable rates, and the gate is
judged on (a) + (b) + (c) together. The student track is evaluated on its own terms (sentence
selection) and cannot inherit the baseline's 96.5% precision by construction. Some lever rows may
be dev-only; the operating point is always reported on the frozen test split. The owner must
approve ADR-0020 and any small-tier adoption before P3.

## ADR-0021 — P2 reports two retention numbers and cost per core-section claim

**Date:** 2026-11-16 — **Status:** Accepted (owner decision, 2026-11-18). The gate wording is
unchanged; both retention numbers and `$/core-section claim` are reported for every configuration.

**Context.** P2-02 measured that section targeting removes most of the audited output: the `core` set
(abstract/results/conclusion) held only **57 of 200 gold claims (28.5%)**, so the lever showed −56.4%
cost with retention 34.5%. A single retention number therefore conflates two very different things:
output the configuration chose not to look for (sections it never read) and output it failed to
reproduce (sections it read but produced nothing usable). Passing the whole P2 phase on one blended
number would let a cheap configuration win by simply reading less. P3 will need to know which
sections the *relied-upon* claims actually live in before that is decided.

**Decision.** Every P2 configuration reports:
1. **Retention — all claims:** share of the 200 gold claims the configuration still emits (today's
   number, unchanged).
2. **Retention — core-section claims:** share of the **57** gold claims whose recorded section matches
   the configuration's own section set that it still emits. A configuration that does not read a
   section is not scored on claims from it, but the exclusion is stated, never folded into one rate.
3. **Cost per core-section claim:** list-price USD (from the ledger) divided by the retained
   core-section gold claims, reported next to `$/paper` and `$/claim`.
4. **Aligned precision** stays as defined (ADR-0020): `CORRECT / aligned`, with unverifiable output
   counted separately.

The **gate keeps both precision and agreement-with-baseline**: a configuration must hold aligned
precision within tolerance *and* retain claims, reported under both definitions above. The numeric
thresholds, and whether the core-section retention becomes the binding one, are **NOT** decided here;
they stay as PRD §P2 states until the owner approves. P3 separately checks which sections the
relied-upon claims come from, because that — not P2's cost table — determines whether dropping a
section is acceptable.

**Alternatives considered:** keep one blended retention number (hides reading less as failure or
manufactures success); score precision only on retained claims with no retention reported (lets a
configuration emit almost nothing); let each lever choose its own sections and report its own
convenient subset (not comparable across rows).

**Consequences:** the ablation harness must emit both retention numbers and `$/core-section claim`
for every row; existing rows are recomputed from the same artifacts (no new labels, no new LLM
calls). Rows with a different section set remain comparable because the core definition is fixed in
config, not per configuration. Accepted 2026-11-18; the gate wording is unchanged, and the
operating-point decision records the retention consequence.

## ADR-0022 — P2 operating point: length-risk escalation

**Date:** 2026-11-17 — **Status:** Accepted (owner decision, 2026-11-18). P2-08's "proposed" lock is
promoted to accepted; P3 may use this operating point.

**Context.** Six measured P2 rows exist (`docs/reports/P2-frontier.md`): baseline, `sections-core`,
`batching`, `student-minilm`, `escalation-length30`, `flywheel-student`. Three levers are negatives on
their own — section targeting and batching buy cost by emitting far fewer claims, and the student
retains ~30% of audited output. The literal PRD §P2 gate (≥50% savings within 2 points of baseline
precision) is passed by **two** rows: `sections-core` (−56.4%, test precision 96.3%, test retention
**27.8%**) and `escalation-length30` (−55.6%, test precision 98.2%, test retention **56.7%**).

**Decision.** The P2 operating point is **`p2-05-length30-v1`**: the frozen
`student-v1-minilm-lr` on every paper (0 LLM calls), the longest **30%** of papers replaying the
frozen `gemini-3.5-flash-lite` teacher, and `gemini-3.8-flash` only for an escalated paper with no
accepted claim (which did not trigger on gold; projected 3.2% of papers).

Measured: **$0.002505111/paper (−55.6%)**, test precision **98.2%**, retention test **56.7%**
(core 50.9%), **`e = 31.1%`**, **`s = 0.29%`** of baseline cost at an **ASSUMED** $0.05/CPU-hour and
measured 1,192 ms/paper. Selection rule: among gate-passing rows, the one that retains the most
audited output; cheapest-only would select `sections-core` at 27.8% retention, which reads less
rather than works better.

**Alternatives considered:** `sections-core` (marginally cheaper, half the retention); `batching`
(fails the cost target at −37.7% and halves yield); `student-minilm`/`flywheel-student` (no provider
cost but ~30% retention, and they still need escalation to be a pipeline); baseline (no savings).

**Consequences and accepted caveats.** ADR-0021 and this ADR were accepted on 2026-11-18. The literal
PRD gate is recorded as PASS on `escalation-length30`; the **56.7% test retention is a stated
limitation**, not a silent pass, and no measured row reaches 90% retention. Savings exclude stage 2,
which is projected to add $0.000335/paper (54.8% savings) and was never measured at scale. `s` is a
priced compute assumption, not a bill. If a later phase requires ≥90% retention, this operating point
must be revisited; the negative-result alternative remains documented in `docs/reports/P2-cascade.md`.

## ADR-0023 — P3-03 gold set: waves, two-frame sampling, source-level split

**Date:** 2026-11-18 — **Status:** Proposed (owner decision pending; the owner is the labeler).

**Context.** P3-02 produced **6,117 candidate contexts** over **258 source papers** with at least one
context, and a source-claim proxy for **69.7%** of the frame (`docs/reports/P3-02-candidates.md`).
The P3-01 pilot labelled 20 rows: **16 MENTIONS / 2 RELIES_ON / 2 UNRELATED**, a base rate of 10.0%
(Wilson 95% **[2.8%, 30.1%]**) from a single labeler, on an edge-case-enriched packet. The PRD gate
needs recall ≥0.70 (ratified ≥0.80) on `RELIES_ON` against a citation-level baseline, so the audit
must produce enough positives that a recall estimate can be defended — not merely enough rows.

**Decision.**

1. **Waves, not one sample.** Wave 1 is **150 rows**. Each later wave draws from the pool remaining
after earlier waves, so a wave never re-labels or invalidates an earlier draw. Every row carries a
fixed inclusion probability and weight in `p3-03-wave1-manifest.csv`, and the dev/test split is fixed
at source level, so waves are additive: row weights, strata and split are properties of the row, not
of the wave. The owner decides after wave 1 whether to continue toward ~300–600 rows.
2. **Two frames in every wave.** A **uniform random slice of 30 rows** (π = 30/6,117 = 0.004904,
weight 203.9) gives an unbiased base rate; **120 cue-enriched rows**, stratified by citing section,
give the positives. The cap is **8 rows per source** (5% of a 150-row wave) because 17 sources hold
66% of all contexts; 5 sources hit the cap in wave 1. Cues are deterministic regexes over the citing
sentence: `we_used` (0.3% of contexts), `based_on` (3.5%), `numeric_effect` (2.2%), `comparison`
(6.5%), `method_word` (3.7%), `inference_connector` (3.0%), `prior_finding` (1.0%), leaving a
cue-positive pool of 1,080 (17.7%). A bare-digit cue was rejected after measurement: it fired on
99.8% of contexts and enriched nothing. Metrics are reported **weighted and unweighted**.
3. **Split by source paper, frozen before any detector exists.** Seed `20261119` assigns whole source
papers, balanced by context count: **34 dev / 34 test sources, 3,059 / 3,058 contexts**, wave rows
**73 / 77**. Because assignment covers every source, no context can move split later. Nothing is tuned
on test.
4. **Linked and unlinked rows are both in the gold set.** 67.3% of wave rows carry a source-claim
proxy; 49 do not. Of those, 15 show the source abstract and 34 have no abstract at all (retracted or
withdrawn stub articles with a title only). Dropping the unlinked third would truncate the frame and
bias prevalence, and those rows are exactly where retraction-notice `MENTIONS`/`UNRELATED` cases live.
**Effect on the framing:** gold labels the context→source edge, so a corpus-level claim is about
*context-source edges*, and claim-linking accuracy (P3-06) is reported on the linked subset only.
5. **A reserved overlap set for a second labeler.** **30 rows (20% of the wave)** — 24 cue-enriched +
6 uniform — are exported as a separate blind packet with a blank labeler-id field. Enrichment is what
makes `RELIES_ON` and `UNRELATED` frequent enough for κ to be estimable; κ from an enriched overlap is
prevalence-specific and is **not** the corpus κ. If a class is absent after labelling, the owner tops
up with ≤10 rows from the remaining pool.
6. **How many positives a recall claim needs** (measured by the script's Wilson table):

| positives | recall 0.80 CI | recall 0.85 CI |
| --: | :-- | :-- |
| 15 | 0.548–0.930 | 0.621–0.963 |
| 30 | 0.627–0.905 | 0.703–0.947 |
| 60 | 0.682–0.882 | 0.739–0.919 |
| 100 | 0.711–0.867 | 0.767–0.907 |

At ~15 positives the interval straddles the gate and certifies nothing; **~30 positives** supports a
decision-grade read at observed recall ≈0.85, and **~100** gives a lower bound above 0.70 at observed
0.80. Wave 1 is expected to yield **3 positives under the pilot's own cue reading** (0 of 3
cue-positive pilot rows were `RELIES_ON`) and **~21 if enrichment lifts the rate to 15%**; the realised
count replaces this assumption before the owner decides on wave 2.

**Alternatives considered.** One uniform sample of ~600 rows: unbiased and ~60 positives, but ≈5 hours
of owner labeling and no class coverage guarantee for κ. Pure cue-enriched sampling: more positives,
but no base rate, so false-alarm reduction could not be estimated. Labelling the whole 6,117-context
frame: not feasible at one labeler.

**Consequences and risks.** The cues are **unvalidated** — no cue separates `RELIES_ON` from
`MENTIONS` in the 20-row pilot — so wave 1 is also a measurement of the cues; if the lift is near zero,
wave 2 shifts rows to the uniform frame. The per-source cap makes enriched design weights approximate,
and capped sources are listed in the report so the effect is checkable. The 30-row uniform slice yields
only ~3 positives, so the base-rate interval stays wide until later waves. Estimated labeling time is
50–112 minutes for wave 1 at 20–45 s/row; the P3-01 pilot recorded no duration, so that is arithmetic,
not a measurement. No labels are created by the agent.

## ADR template
```
## ADR-XXXX — Title
Date · Status
Context:
Decision:
Alternatives considered:
Consequences:
```
