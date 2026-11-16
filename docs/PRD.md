# Axion V2 — Product Requirements Document (phase-wise)

**Status:** Draft v1 · **Owner:** project owner · **Last updated:** 2026-11-14
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
2. `LLMClient` with provider tiering, retry, cooldown, content-hash cache, and mandatory SQLite cost ledger; every ledger row records `stage`, model `tier`, and an escalation link (`parent_call_id` or equivalent).
3. `pricing.yaml` (owner-filled) and ledger report script (cost by stage/model/paper).
4. Europe PMC client + JATS parser producing sections, paragraphs, references, and citation contexts.
5. Retraction data loader and linker (by DOI/PMID/PMCID) with coverage stats.
6. Feasibility report and **sub-topic decision (ADR)**.
7. Ingested corpus of 2k–5k papers **total, including all discoverable citers**, in Neo4j (schema v2) + Chroma; hard cap ~5,000.
8. Baseline claim extractor (single large model, all target sections) with ledger; outputs persisted as candidate **silver** labels with provenance (teacher model/version, prompt version, run_id), not gold.
9. Audit rubric applied to ≥200 random claims; labels committed; Wilson CI computed.
10. `docs/reports/P1-baseline.md` with: precision, cost/paper, p95 latency, corpus & retraction coverage stats.

### Step-by-step plan
- **P1.1 Repo bootstrap.** `pyproject.toml`, `src/axion` skeleton, ruff, mypy, pytest, pre-commit (incl. secret scan), GitHub Actions CI, `.env.example`, Makefile targets (`lint`, `typecheck`, `test`, `report`).
- **P1.2 Settings & config.** Pydantic settings, `config/` package, `pricing.yaml` template, stage config schema.
- **P1.3 LLMClient + ledger.** Port V1 `llm.py` ideas (fallback chain, transient retry, provider cooldown, cache); add: tier names (`small`, `large`), structured-output validation, SQLite `llm_calls` table, `cost_report` CLI. Offline tests with a fake provider.
- **P1.3b Ledger schema extension.** Add model tier and `parent_call_id` escalation links to `llm_calls`; add a `training_runs` table (`run_id, model, data_hash, hardware, duration_s, estimated_usd`). Teacher calls use stage `teacher_label`; escalated calls link to the call/stage they escalated from. Keep schema migration/idempotency tests.
- **P1.4 Europe PMC client.** Search + fetch JATS by PMCID; polite rate limiting; local raw cache; deterministic file naming.
- **P1.5 JATS parser.** Sections, paragraphs, reference list (DOI/PMID/PMCID where present), and **citation contexts** via bibr xrefs. Golden-file tests from ≥10 real samples across journals; coverage metrics (% papers with ≥1 parsed context).
- **P1.6 Retraction loader.** Load Retraction Watch/Crossref data; link to corpus candidates; coverage report (retracted, full text available, citers present).
- **P1.7 Feasibility spike.** For 3–5 candidate sub-topics, count retracted OA papers with full text and in-corpus citers and contexts. Choose by criteria in `CONTEXT.md §4`; record ADR. Apply pivot rule if minimums fail.
- **P1.8 Ingest corpus.** 2k–5k papers **total, including retracted sources and all discoverable citers of those sources** (hard cap ~5,000; owner decision 2026-11-14), so blast radius is computable. Zero LLM cost.
- **P1.9 Stores.** Neo4j schema v2 (constraints/indexes), Chroma collections, idempotent loaders; tests with ephemeral/mocked stores.
- **P1.10 Baseline extractor.** Structured claim extraction with provenance, one large model, all target sections, via `LLMClient`. Cap run by budget guard; `--dry-run` first. Persist outputs as candidate **silver** labels with provenance (`teacher model/version`, `prompt version`, `run_id`); they are not gold and cannot be used to evaluate students.
- **P1.11 Audit.** Draw a random sample of ≥200 claims (seeded), label per `docs/eval/AUDIT_RUBRIC.md`, complete the agreement step (blind self-relabel after ≥7 days or independent 20% second-labeler overlap); commit labels.
- **P1.12 Baseline report + gate review.** Generate `docs/reports/P1-baseline.md` via script; ratify or revise provisional targets in `CONTEXT.md §6` via ADR.

### Acceptance criteria
- CI green; ≥ one real-sample golden test per parser feature.
- Ledger shows 100% of LLM calls with `stage`, model `tier`, and escalation links; report script reproduces cost tables.
- Corpus meets or ADR-justifies minimums; baseline report committed.
- Baseline outputs have a silver-label manifest with teacher/prompt/run provenance; they are not treated as gold.
- Audit labels + CI committed; agreement statistic reported.

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
Cut cost per paper by **≥60%** (stretch 80%) at ≤2 points precision loss vs. the P1 baseline, with each lever's contribution measured. The main scale lever is a teacher-distilled student plus rare, calibrated escalation.

### Rationale
This is the cost half of the thesis and the number a publisher-side stakeholder will care about. LLM-on-every-paper does not scale; the escalation rate `e` and student cost ratio `s` are the quantities that determine whether the layered approach works.

### Deliverables
1. Ablation harness that runs configurations against the frozen audited sample and the ledger, outputting a comparison table.
2. Implemented levers (each toggleable): section targeting, teacher-distilled claim-sentence student (silver training / gold evaluation), content-hash cache/dedup, calibrated small-to-large escalation, prompt batching, tightened candidate gating for later pair work.
3. Cost-vs-quality **frontier chart** and table; chosen operating point recorded in an ADR.
4. `docs/reports/P2-cascade.md` including negative results, measured `e` and `s`, the learning curve, the flywheel result, and a clearly labeled cost-projection section with assumptions.

### Step-by-step plan
- **P2.1 Eval harness.** Frozen dev/test split of audited claims; scripted configs; outputs JSON + markdown table; seeds and config hashes recorded.
- **P2.2 Lever: section targeting.** Restrict to abstract/results/conclusion (configurable); measure Δcost, Δprecision, Δclaim yield.
- **P2.3 Lever: sentence filter.** *Superseded by ADR-0008 on 2026-11-14.* Original plan: embedding features + simple classifier trained on audited labels. Replaced by the teacher-student track below.
- **P2.3a Silver labeling by the teacher.** Budget-capped and dry-run-first teacher labeling on the unlabeled corpus; persist provenance (`teacher model/version`, prompt version, run_id); paper-level split; write to the silver-label store. Gold data is never used to train the student.
- **P2.3b Train claim-sentence student + gold evaluation.** Train a small encoder on the silver TRAIN split; tune thresholds on gold DEV; report precision/recall/F1 on the frozen gold TEST. Record student version/hash; never evaluate on teacher-labeled data.
- **P2.3c Learning curve.** Measure student quality vs. number of silver labels at geometric steps up to the label budget; report the curve and the marginal value of more labels.
- **P2.4 Lever: cache/dedup.** Content-hash keys; dedupe near-identical sentences; measure hit rates on re-runs and across papers.
- **P2.5 Lever: calibrated escalation.** Define confidence/agreement signals and calibrated or conformal thresholds; escalate low-confidence items to a small LLM, then a large LLM. Measure the escalation rate `e`, escalation cost, and net cost.
- **P2.5b Flywheel experiment.** Retrain the student including escalated cases as new silver labels; show whether `e` falls and whether gold-test quality holds. Report before/after.
- **P2.6 Lever: batching.** Multiple sentences/sections per call within token limits; measure parse-failure rate.
- **P2.7 Combine & sweep.** Evaluate combinations; produce the frontier; report `e`, `s`, and net cost per configuration; select the operating point.
- **P2.8 Regression tests & docs.** Lock chosen config in `config/`; tests ensure ledger logging and determinism; write the report with measured `e`, `s`, and a separate projection section.
- **P2.9 Cost projection.** Add `scripts/cost_model.py` that reads ledger measurements and projects to `N` papers (e.g., 1M, 20M) with ranges and sensitivity to `s`, `e`, tokens/paper, and prices. Output separates **MEASURED** from **PROJECTED** and prints all assumptions.

### Acceptance criteria
- Chosen config achieves the original target savings within the precision tolerance, **or** the report documents why not (negative result) and the best frontier point.
- Every lever has an isolated ablation row; all numbers regenerable via one command.
- No test-split leakage (documented); no student evaluation on teacher-labeled data; splits are by paper.
- `e`, `s`, the learning curve, the flywheel result, and the projection are reported, with measured and projected values clearly separated.
- **Student kill rule:** if students cannot reach within 2 points of baseline precision on the gold test at any label budget, publish the negative result and fall back to the best cascade without students.

### Metrics
Cost/paper, precision/recall of claim extraction vs gold labels, escalation rate `e`, student cost ratio `s`, learning curve, cache hit rate, parse failure rate, latency, projected cost to `N` papers (separately labeled).

### Gate
Pass if ≥50% savings within 2 points precision (or negative result published and owner agrees to proceed). Must hold before P3 processes full corpus.

### Out of scope
Dependency detection, new data sources, UI.

### Risks
Small models degrade quality unevenly; teacher errors propagate into silver labels; student underperforms on fuzzy claim boundaries; batching hurts parse reliability; projections overreach if assumptions are hidden.

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
5. Staged detector (heuristic features → teacher-distilled student → calibrated LLM escalation) plus claim linking to A's claims (embedding/student match, LLM only if ambiguous); risk-ordered, lazy processing.
6. Trust propagation rule v2: documented, parameterized, unit-tested; before/after on case studies.
7. Evaluation report with precision/recall/false-alarm reduction vs baselines, cost per stage, `e`, `s`, and $/retraction analyzed.
8. ≥3 case studies of real retractions (blast radius graphs + narrative).

### Step-by-step plan
- **P3.1 Guideline.** Draft definitions; pilot on 20 contexts; refine.
- **P3.2 Candidate generator.** Build from parsed contexts; link to source claims; store in Neo4j.
- **P3.3 Gold labeling.** Sample stratified by section and retracted paper; label; double-label ≥20%; compute agreement; freeze dev/test split.
- **P3.4 Baselines.** Implement and score citation-level, heuristic, and LLM-only baselines (with ledger cost).
- **P3.5 Staged detector.** Feature stage → teacher-distilled student (silver labels from teacher on candidate contexts, paper-level split, gold dev/test) → calibrated LLM escalation; tune on gold dev; evaluate on frozen gold test; report `e` and `s`.
- **P3.5b Priority / lazy scheduling.** Implement a risk-ordered queue (contexts citing flagged papers first), idempotent hash-keyed incremental runs, and explicit hot/cold corpus states. Cold items remain unprocessed until needed.
- **P3.6 Claim linking.** Match relying contexts to specific claims in A (embedding/student match; LLM only if ambiguous); evaluate link accuracy on a labeled subset.
- **P3.7 Propagation v2.** Define rule (e.g., strength-weighted decay with caps and transitive limits); unit tests; sensitivity analysis.
- **P3.8 Cost accounting.** Compute $/retraction analyzed, per-stage breakdown, escalation rate `e`, and student cost ratio `s` from the ledger.
- **P3.9 Case studies.** Select 3+ retractions; document blast radius; include honest failure cases.
- **P3.10 Report + gate review.**

### Acceptance criteria
- Test-split results reported with CIs; false-alarm reduction and recall at the chosen operating point stated against provisional targets.
- Agreement statistic for double-labeled subset reported.
- Cost per retraction analyzed reproducible from ledger; `e` and `s` reported; no student evaluation on teacher-labeled data; splits are by paper.
- Re-running the scheduler produces identical counts/decisions; cold corpus items are demonstrably untouched.

### Metrics
Precision/recall/F1 per class, false-alarm reduction vs citation-level, claim-link accuracy, inter-labeler agreement, $/retraction analyzed, per-stage cost share, escalation rate `e`, student cost ratio `s`.

### Gate
Pass if staged detector beats citation-level on false alarms at recall ≥ 0.70 (ratified target ≥0.80 per CONTEXT). **Otherwise stop, write up honestly, and do not ship the claim.**

### Out of scope
Contradiction judge, new sources, multi-user features.

### Risks
Subjective labels; small label count; heterogeneous citation styles; retracted-paper claims poorly extractable; teacher errors propagate into the student; student underperforms on ambiguous reliance contexts.

---

## P4 — Demo and dashboard (weeks 10–11)

### Objective
Make the results inspectable: a minimal API and UI showing a retraction's blast radius with a **visible cost panel**.

### Deliverables
1. FastAPI read endpoints: list retractions, blast radius for a paper, claim provenance, cost summary (by stage, per retraction). Shared-key auth on any compute endpoint; health endpoints.
2. Minimal web view: retraction picker → blast radius graph + table (claim, citing paper, strength, evidence span) + cost panel (dollars, calls, cache hits, `e`, `s`, cost by stage, and a clearly labeled projection table with assumptions).
3. Docker Compose for Neo4j + API (+ web), healthchecked, loopback-bound ports.
4. Seeded demo dataset and one-command local start; screenshots committed.

### Step-by-step plan
- **P4.1 API.** Models, endpoints, error handling, rate limit, tests.
- **P4.2 Cost endpoints.** Aggregations from ledger; tests.
- **P4.3 UI shell.** Layout, API client, offline/empty states.
- **P4.4 Blast radius view.** Graph + table; provenance links to source spans.
- **P4.5 Cost panel.** Per-stage cost, savings vs baseline, escalation rate `e`, student cost ratio `s`, and the projection table labeled **PROJECTION** with assumptions (measured values visually separated).
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
2. Public write-up (blog/preprint-style): problem, method, cost-quality frontier, blast-radius results, limitations, negative results, and a section **"What we do and do not claim about scale."**
3. Open dataset release (labels, ledger summaries, schemas) after license/terms check of source data.
4. `CITATION.cff`, LICENSE, SECURITY.md, CONTRIBUTING.md; tagged release `v2.0.0`.
5. Owner-run outreach per `_private/outreach-plan.md` (agents do not contact anyone).

### Step-by-step plan
- **P5.1 Reproducibility pass.** Fresh-environment run of all scripts; fix drift.
- **P5.2 Data release check.** Verify redistribution terms for any text/labels; release only what is allowed.
- **P5.3 Docs polish.** README, OPERATIONS, limitations.
- **P5.4 Write-up draft.** Numbers pulled from generated reports only; include "What we do and do not claim about scale": measured at ~5k papers, projected with ranges, students can fail on fuzzy boundaries, and prior art in citation-statement classification is acknowledged.
- **P5.5 Release.** Tag, changelog, citation metadata.
- **P5.6 Owner outreach prep** (agent drafts materials in `_private/`; owner sends).

### Acceptance criteria
Independent reproduction of headline tables from a clean checkout; every claim in the write-up maps to a generated artifact.

---

## Backlog (requires ADR to enter a phase)
Contradiction/reconciliation judge port; citation-faithfulness check; temporal claim decay; Q&A coordinator; auth/multi-tenancy; additional corpora/sources.
