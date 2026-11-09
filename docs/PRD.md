# Axion V2 — Product Requirements Document (phase-wise)

**Status:** Draft v1 · **Owner:** project owner · **Last updated:** 2026-11-09
Authority: subordinate to `CONTEXT.md`. Task-level tracking lives in each phase's `TODO.md`; this PRD defines *what and why*, the TODOs track *done or not*.

## How to read this PRD
Each phase has: objective, rationale, inputs, deliverables, step-by-step plan, acceptance criteria, metrics, gate (with kill/pivot rules), out of scope, risks. Steps are numbered `P<n>.<k>` and map one-to-one onto TODO task IDs (`P<n>-<kk>`).

Cross-cutting requirements (apply to every phase):
- Every LLM call is ledgered; every experiment reports quality **and** cost.
- Every reported number is regenerable by a documented command.
- Tests are offline by default; CI stays green.
- Docs updated with behavior changes; decisions recorded as ADRs.

---

## Day 0 — Prerequisites (see `docs/DAY0_PREREQUISITES.md`)
Outputs required before P1 starts: clean repo created, V1 snapshot tagged, migration map executed (files ported with provenance), accounts/keys ready, budget caps written, owner decisions recorded (license, LLM providers per tier). Exit: Day-0 checklist fully ticked.

---

## P1 — Foundation, ledger, corpus, baseline (weeks 1–2)

### Objective
Stand up a clean, tested codebase with a **cost ledger**, a **JATS-based corpus** in a chosen biomedical sub-topic, and a **measured baseline** (claim precision, cost per paper, latency).

### Rationale
Nothing later is credible without a baseline, and V1's "99/100 claims correct" was never formally measured. The ledger makes every later cost claim honest.

### Inputs
V1 components per migration map; Europe PMC REST API; Retraction Watch data via Crossref; owner-supplied API keys and budget caps.

### Deliverables
1. Bootstrapped repo (packaging, lint, types, tests, CI, pre-commit with secret scan).
2. `LLMClient` with provider tiering, retry, cooldown, content-hash cache, and mandatory SQLite cost ledger.
3. `pricing.yaml` (owner-filled) and ledger report script (cost by stage/model/paper).
4. Europe PMC client + JATS parser producing sections, paragraphs, references, and citation contexts.
5. Retraction data loader and linker (by DOI/PMID/PMCID) with coverage stats.
6. Feasibility report and **sub-topic decision (ADR)**.
7. Ingested corpus of 2k–5k papers in Neo4j (schema v2) + Chroma.
8. Baseline claim extractor (single large model, all target sections) with ledger.
9. Audit rubric applied to ≥200 random claims; labels committed; Wilson CI computed.
10. `docs/reports/P1-baseline.md` with: precision, cost/paper, p95 latency, corpus & retraction coverage stats.

### Step-by-step plan
- **P1.1 Repo bootstrap.** `pyproject.toml`, `src/axion` skeleton, ruff, mypy, pytest, pre-commit (incl. secret scan), GitHub Actions CI, `.env.example`, Makefile targets (`lint`, `typecheck`, `test`, `report`).
- **P1.2 Settings & config.** Pydantic settings, `config/` package, `pricing.yaml` template, stage config schema.
- **P1.3 LLMClient + ledger.** Port V1 `llm.py` ideas (fallback chain, transient retry, provider cooldown, cache); add: tier names (`small`, `large`), structured-output validation, SQLite `llm_calls` table, `cost_report` CLI. Offline tests with a fake provider.
- **P1.4 Europe PMC client.** Search + fetch JATS by PMCID; polite rate limiting; local raw cache; deterministic file naming.
- **P1.5 JATS parser.** Sections, paragraphs, reference list (DOI/PMID/PMCID where present), and **citation contexts** via bibr xrefs. Golden-file tests from ≥10 real samples across journals; coverage metrics (% papers with ≥1 parsed context).
- **P1.6 Retraction loader.** Load Retraction Watch/Crossref data; link to corpus candidates; coverage report (retracted, full text available, citers present).
- **P1.7 Feasibility spike.** For 3–5 candidate sub-topics, count retracted OA papers with full text and in-corpus citers and contexts. Choose by criteria in `CONTEXT.md §4`; record ADR. Apply pivot rule if minimums fail.
- **P1.8 Ingest corpus.** 2k–5k papers for the chosen sub-topic **plus all discoverable citers of its retracted papers** (so blast radius is computable). Zero LLM cost.
- **P1.9 Stores.** Neo4j schema v2 (constraints/indexes), Chroma collections, idempotent loaders; tests with ephemeral/mocked stores.
- **P1.10 Baseline extractor.** Structured claim extraction with provenance, one large model, all target sections, via `LLMClient`. Cap run by budget guard; `--dry-run` first.
- **P1.11 Audit.** Draw a random sample of ≥200 claims (seeded), label per `docs/eval/AUDIT_RUBRIC.md`, re-label 10% after ≥7 days; commit labels.
- **P1.12 Baseline report + gate review.** Generate `docs/reports/P1-baseline.md` via script; ratify or revise provisional targets in `CONTEXT.md §6` via ADR.

### Acceptance criteria
- CI green; ≥ one real-sample golden test per parser feature.
- Ledger shows 100% of LLM calls; report script reproduces cost tables.
- Corpus meets or ADR-justifies minimums; baseline report committed.
- Audit labels + CI committed; self-consistency agreement reported.

### Metrics
Claim precision (+95% CI), cost/paper, tokens/paper, p50/p95 latency, parse coverage, retraction linkage coverage.

### Gate
Pass if baseline report exists with audited precision. **If precision < 90%: fix extraction before P2.** If feasibility minimums cannot be met even after pivot options, stop and escalate to owner.

### Out of scope
Cost optimization, dependency detection, UI, contradiction judge.

### Risks
JATS variety; retracted-paper full-text availability; rate limits; labeling time.

---

## P2 — Cost cascade (weeks 3–5)

### Objective
Cut cost per paper by **≥60%** (stretch 80%) at ≤2 points precision loss vs. the P1 baseline, with each lever's contribution measured.

### Rationale
This is the cost half of the thesis and the number a publisher-side stakeholder will care about.

### Deliverables
1. Ablation harness that runs configurations against the frozen audited sample and the ledger, outputting a comparison table.
2. Implemented levers (each toggleable): section targeting, sentence-level claim filter (cheap classifier), content-hash cache/dedup, small-model first pass with escalation rule, prompt batching, tightened candidate gating for later pair work.
3. Cost-vs-quality **frontier chart** and table; chosen operating point recorded in an ADR.
4. `docs/reports/P2-cascade.md` including negative results.

### Step-by-step plan
- **P2.1 Eval harness.** Frozen dev/test split of audited claims; scripted configs; outputs JSON + markdown table; seeds and config hashes recorded.
- **P2.2 Lever: section targeting.** Restrict to abstract/results/conclusion (configurable); measure Δcost, Δprecision, Δclaim yield.
- **P2.3 Lever: sentence filter.** Embedding features + simple classifier (logistic regression/GBM) trained on audited labels (train split only); threshold chosen on dev; measure on test.
- **P2.4 Lever: cache/dedup.** Content-hash keys; dedupe near-identical sentences; measure hit rates on re-runs and across papers.
- **P2.5 Lever: small-model first pass + escalation.** Define escalation signals (low self-reported confidence, schema failure, classifier disagreement); measure escalation rate and net cost.
- **P2.6 Lever: batching.** Multiple sentences/sections per call within token limits; measure parse-failure rate.
- **P2.7 Combine & sweep.** Evaluate combinations; produce frontier; select operating point.
- **P2.8 Regression tests & docs.** Lock chosen config in `config/`; tests ensure ledger logging and determinism; write report.

### Acceptance criteria
- Chosen config achieves target savings within the precision tolerance, **or** the report documents why not (negative result) and the best frontier point.
- Every lever has an isolated ablation row; all numbers regenerable via one command.
- No test-split leakage (documented).

### Metrics
Cost/paper, precision/recall of claim extraction vs audited labels, escalation rate, cache hit rate, parse failure rate, latency.

### Gate
Pass if ≥50% savings within 2 points precision (or negative result published and owner agrees to proceed). Must hold before P3 processes full corpus.

### Out of scope
Dependency detection, new data sources, UI.

### Risks
Small models degrade quality unevenly; classifier overfits small label set; batching hurts parse reliability.

---

## P3 — Blast radius (weeks 6–9)

### Objective
Detect **claim-level dependencies** from citing papers on retracted/flagged papers, **beat the citation-level baseline on false alarms** at acceptable recall, and compute **$/retraction analyzed**.

### Rationale
This is the future-proof bet and the differentiator.

### Deliverables
1. Dependency labeling guideline (`docs/eval/DEPENDENCY_GUIDELINE.md`) with examples and edge cases.
2. Deterministic candidate generator: for each retracted paper A, all in-corpus citing contexts (via JATS bibr xrefs) — zero LLM cost.
3. Gold audit set of 100–150 citation contexts (more if feasible) labeled `RELIES_ON`/`MENTIONS`/`UNRELATED`, with a double-labeled subset and agreement stats.
4. Baselines: citation-level (all affected), section/lexical heuristic, LLM-only.
5. Staged detector (heuristic features → small classifier → LLM only for ambiguous) plus claim linking to A's claims (embedding match, LLM only if ambiguous).
6. Trust propagation rule v2: documented, parameterized, unit-tested; before/after on case studies.
7. Evaluation report with precision/recall/false-alarm reduction vs baselines, cost per stage, and $/retraction analyzed.
8. ≥3 case studies of real retractions (blast radius graphs + narrative).

### Step-by-step plan
- **P3.1 Guideline.** Draft definitions; pilot on 20 contexts; refine.
- **P3.2 Candidate generator.** Build from parsed contexts; link to source claims; store in Neo4j.
- **P3.3 Gold labeling.** Sample stratified by section and retracted paper; label; double-label ≥20%; compute agreement; freeze dev/test split.
- **P3.4 Baselines.** Implement and score citation-level, heuristic, and LLM-only baselines (with ledger cost).
- **P3.5 Staged detector.** Feature stage → classifier → LLM escalation; tune on dev; evaluate on test.
- **P3.6 Claim linking.** Match relying contexts to specific claims in A; evaluate link accuracy on a labeled subset.
- **P3.7 Propagation v2.** Define rule (e.g., strength-weighted decay with caps and transitive limits); unit tests; sensitivity analysis.
- **P3.8 Cost accounting.** Compute $/retraction analyzed and per-stage breakdown from the ledger.
- **P3.9 Case studies.** Select 3+ retractions; document blast radius; include honest failure cases.
- **P3.10 Report + gate review.**

### Acceptance criteria
- Test-split results reported with CIs; false-alarm reduction and recall at the chosen operating point stated against provisional targets.
- Agreement statistic for double-labeled subset reported.
- Cost per retraction analyzed reproducible from ledger.

### Metrics
Precision/recall/F1 per class, false-alarm reduction vs citation-level, claim-link accuracy, inter-labeler agreement, $/retraction analyzed, per-stage cost share.

### Gate
Pass if staged detector beats citation-level on false alarms at recall ≥ 0.70 (ratified target ≥0.80 per CONTEXT). **Otherwise stop, write up honestly, and do not ship the claim.**

### Out of scope
Contradiction judge, new sources, multi-user features.

### Risks
Subjective labels; small label count; heterogeneous citation styles; retracted-paper claims poorly extractable.

---

## P4 — Demo and dashboard (weeks 10–11)

### Objective
Make the results inspectable: a minimal API and UI showing a retraction's blast radius with a **visible cost panel**.

### Deliverables
1. FastAPI read endpoints: list retractions, blast radius for a paper, claim provenance, cost summary (by stage, per retraction). Shared-key auth on any compute endpoint; health endpoints.
2. Minimal web view: retraction picker → blast radius graph + table (claim, citing paper, strength, evidence span) + cost panel (dollars, calls, cache hits).
3. Docker Compose for Neo4j + API (+ web), healthchecked, loopback-bound ports.
4. Seeded demo dataset and one-command local start; screenshots committed.

### Step-by-step plan
- **P4.1 API.** Models, endpoints, error handling, rate limit, tests.
- **P4.2 Cost endpoints.** Aggregations from ledger; tests.
- **P4.3 UI shell.** Layout, API client, offline/empty states.
- **P4.4 Blast radius view.** Graph + table; provenance links to source spans.
- **P4.5 Cost panel.** Per-stage cost, savings vs baseline.
- **P4.6 Compose + seed.** Reproducible demo; docs.
- **P4.7 Screenshots + walkthrough doc.**

### Acceptance criteria
Fresh clone → one command → demo with seeded data; every displayed number traceable to the ledger or labeled evaluation; no secrets in client bundle.

### Out of scope
Accounts, multi-tenancy, streaming, export.

---

## P5 — Release and write-up (week 12)

### Objective
Package the work so a stranger can understand, reproduce, and cite it.

### Deliverables
1. Polished README, `docs/OPERATIONS.md`, reproduction guide (`make report` regenerates all tables).
2. Public write-up (blog/preprint-style): problem, method, cost-quality frontier, blast-radius results, limitations, negative results.
3. Open dataset release (labels, ledger summaries, schemas) after license/terms check of source data.
4. `CITATION.cff`, LICENSE, SECURITY.md, CONTRIBUTING.md; tagged release `v2.0.0`.
5. Owner-run outreach per `_private/outreach-plan.md` (agents do not contact anyone).

### Step-by-step plan
- **P5.1 Reproducibility pass.** Fresh-environment run of all scripts; fix drift.
- **P5.2 Data release check.** Verify redistribution terms for any text/labels; release only what is allowed.
- **P5.3 Docs polish.** README, OPERATIONS, limitations.
- **P5.4 Write-up draft.** Numbers pulled from generated reports only.
- **P5.5 Release.** Tag, changelog, citation metadata.
- **P5.6 Owner outreach prep** (agent drafts materials in `_private/`; owner sends).

### Acceptance criteria
Independent reproduction of headline tables from a clean checkout; every claim in the write-up maps to a generated artifact.

---

## Backlog (requires ADR to enter a phase)
Contradiction/reconciliation judge port; citation-faithfulness check; temporal claim decay; Q&A coordinator; auth/multi-tenancy; additional corpora/sources.
