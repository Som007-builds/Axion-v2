# CONTEXT.md — RetractionScope Project Bible

> **Audience:** any AI agent or human contributor, at any time.
> **Authority:** this file outranks every other document except an explicit, dated owner instruction recorded in `docs/DECISIONS.md`.
> **Hierarchy of truth:** `CONTEXT.md` > `docs/DECISIONS.md` > `docs/PRD.md` > phase `TODO.md` > code comments.
> **Maintenance:** edit only via a PR/commit that also adds an entry to the changelog at the bottom. Scope-changing edits require an ADR approved by the owner.

---

## 1. One-line purpose

RetractionScope is a **claim-level trust-propagation system for the scientific literature**: when a paper is retracted or flagged, it determines which claims in *other* papers genuinely depended on it, and it does so at a **measured, minimized cost**.

## 2. Why this project exists

### 2.1 Problem
- Retractions and integrity flags are increasingly large-batch events (e.g., conference-proceedings purges, paper-mill takedowns), and AI-generated or fabricated content is entering the literature faster than review capacity grows.
- Existing downstream-impact alerts work at the **citation level** ("this paper cites a retracted paper"). A citation can be a passing mention, a background reference, or a load-bearing premise; citation-level alerts cannot tell these apart and therefore generate false alarms or get ignored.
- LLM-based claim processing over an entire corpus is cost-prohibitive at publisher scale (illustratively, a small per-paper LLM cost across tens of millions of papers becomes a multi-million-dollar range depending on assumptions). Any credible system must treat cost as a design constraint, not an afterthought.

### 2.2 Thesis (the "two bets")
1. **Future-proof bet — claim-level blast radius.** Determine, for a retracted/flagged source paper, which downstream *claims* depend on which *source claims*, and propagate reduced trust accordingly.
2. **Cost bet — layered, demand-driven cascade.** Process only what is needed: expand outward from retracted/flagged nodes and push work through four layers: **(0)** deterministic JATS/sections/dedup/cache, **(1)** distilled student models trained on teacher silver labels, **(2)** rare escalation from a small LLM to a large LLM, and **(3)** lazy/priority processing with hash-cached, paper-level idempotency. The simplified planning model is `relative_cost ≈ s + e`, where `s` is student cost as a fraction of LLM-everywhere cost and `e` is the escalation rate. `e` dominates and is measured, not assumed. Illustrative values (`s≈0.01`, `e≈0.05–0.15`) are **assumptions**; a 20M-paper / 200M-claim / ~300 GB-embedding calculation is an **arithmetic illustration**, not measured data. Cost scales with retractions and escalated cases, not with the whole corpus.

The headline results this project exists to produce:
- **Cost per paper** (before vs. after the cascade, at equal measured quality).
- **Dollars per retraction analyzed.**
- **False-alarm reduction versus a citation-level baseline**, at acceptable recall.

### 2.3 Owner goals (public-safe summary)
Build a flagship, portfolio-grade, rigorously evaluated system; gain real experience designing systems where cost and scale are first-class constraints; publish results openly. Private strategy lives in `_private/` (untracked) — see §13.

## 3. Scope

### 3.1 In scope
- Ingest open-access biomedical full text (Europe PMC, JATS XML).
- Deterministic extraction of sections, paragraphs, references, and **citation contexts** from JATS.
- Structured claim extraction with provenance (paper → section → evidence span).
- Retraction/flag ingestion and linking to papers in the corpus.
- Claim-dependency detection between citing contexts and source claims.
- Trust (confidence) propagation with a documented, testable rule.
- Full cost ledger and a cost-vs-quality frontier for every pipeline stage.
- Reproducible evaluation with human-audited labels.
- Train small student models (claim-sentence detector; citation-context relation classifier) from teacher silver labels, and evaluate them on human-audited gold labels with paper-level splits.
- A cost-projection model with explicit ranges and assumptions, driven by measurements from the ledger.
- Minimal API + dashboard demonstrating blast radius with a visible cost panel.

### 3.2 Explicitly out of scope (non-goals)
- Not a chatbot, not generic RAG, not a literature Q&A product.
- Not an arbiter of scientific truth. Outputs are hypotheses with provenance.
- No multi-tenant accounts, billing, or production hardening.
- No PDF-first pipeline (JATS first; PDF only as a documented fallback if ever needed).
- No contradiction/reconciliation judge, gap finder, experiment recommender, temporal agent, or Coordinator Q&A loop in V2.0 (see backlog, §12).
- No new data sources beyond Europe PMC + Crossref/Retraction Watch data unless an ADR approves them.
- No claim of solving extraction at 20M-paper scale; V2 measures cost structure at ~5k papers and projects to larger scales with explicit assumptions.

## 4. Domain and data

| Item | Decision |
| :-- | :-- |
| Domain | Open-access biomedical literature (Europe PMC OA subset) |
| Full-text format | JATS XML via Europe PMC REST API |
| Retraction labels | Retraction Watch database as distributed via Crossref (**verify license and fields in Day-0**) |
| Corpus size (initial) | **2,000–5,000 papers total, including retracted sources and all discoverable citers; hard cap ~5,000** (owner decision 2026-11-14) |
| Sub-topic selection criteria | Enough retracted OA papers with full text **and** enough in-corpus citers (provisional minimums: ≥30 retracted source papers, ≥300 citation contexts citing them). Revisit with real data. |
| Legacy domain | V1 used ML papers from arXiv. V1's reviewed pair set is retained only as a clearly labeled legacy benchmark (`eval/legacy/`). |

Notes:
- JATS `<xref ref-type="bibr" rid="…">` markers inside paragraphs give **citation contexts for free** (no LLM). This is a core cost lever.
- Retracted papers' text may be missing, truncated, or watermarked. Handle explicitly; record coverage stats.

## 5. Glossary

| Term | Definition |
| :-- | :-- |
| **Claim** | A falsifiable, source-linked assertion extracted from a paper, with section and evidence span. |
| **Evidence span** | The verbatim text span in the paper supporting the claim as extracted. |
| **Citation context** | The sentence(s) in paper B surrounding a citation marker that points to paper A. |
| **Source paper (A)** | A retracted or flagged paper. |
| **Citing paper (B)** | A paper in the corpus that cites A. |
| **Dependency** | A directed relation: a claim (or context) in B *relies on* a specific claim in A. Labels: `RELIES_ON`, `MENTIONS`, `UNRELATED`. |
| **Blast radius** | The set of downstream claims/papers affected by a retraction, with per-edge strength and aggregate trust change. |
| **Citation-level baseline** | Treat every citing paper as affected. The thing we aim to beat on false alarms. |
| **Cascade** | Ordered pipeline stages from cheap/deterministic to expensive/LLM; later stages run only on cases earlier stages cannot resolve. |
| **Teacher** | An expensive LLM used to produce **silver labels** for student training; it is not an evaluator of student quality. |
| **Student** | A small encoder model trained on silver labels; it runs the bulk of inference at low cost. |
| **Silver labels** | Machine-generated labels (teacher, student, or heuristic). Used for **training** only; never for reported evaluation. |
| **Gold labels** | Human-audited labels used for **evaluation** (dev for tuning, frozen test for reporting). |
| **Escalation rate (e)** | Fraction of items sent to any LLM after the student stage; the dominant driver of `relative_cost ≈ s + e`. |
| **Student cost ratio (s)** | Student inference cost divided by LLM-everywhere cost for the same workload; measured from the ledger. |
| **Hot / cold corpus** | Hot corpus is prioritized risk-first (contexts citing flagged/retracted papers); cold corpus stays unprocessed until needed. |
| **Cost projection** | Modeled cost to `N` papers from measured ledger values; always labeled **PROJECTION** with ranges and assumptions, never presented as measured. |
| **Cost ledger** | Persistent record of every LLM call: tokens, dollars, latency, cache hit, stage, run. |
| **Cost-quality frontier** | Plot of quality (e.g., precision/recall) vs. cost for pipeline configurations. |
| **$/retraction analyzed** | Total ledger cost to compute the blast radius of one retracted paper, end to end. |
| **Audit** | Human labeling of a sample against `docs/eval/AUDIT_RUBRIC.md`. |
| **Gate** | A pass/fail checkpoint at the end of a phase with explicit kill/pivot criteria. |

## 6. Success metrics and gates

Targets marked *provisional* are ratified or revised at the end of Phase 1 using real data (record in an ADR).

| Metric | Measured in | Target | Notes |
| :-- | :-- | :-- | :-- |
| Claim extraction precision | P1 | ≥ 90% (blocks P2 if lower) | Audit n ≥ 200; report Wilson 95% CI |
| Cost per paper (baseline) | P1 | measured, no target | Baseline = single large model on all sections |
| Cost per paper reduction | P2 | ≥ 60% (stretch 80%) | At ≤ 2 points precision loss vs. baseline |
| Escalation rate `e` | P2 | measured; target TBD after first data | Fraction sent to any LLM after students; key cost driver |
| Student cost ratio `s` | P2 | measured | Student inference cost / LLM-everywhere cost |
| Learning curve — quality vs. silver label count | P2 | report | Quality on frozen gold test at geometric label budgets |
| Student agreement with gold | P2/P3 | report | On frozen gold test, per task; never teacher-labeled evaluation |
| Cost projection to `N` papers | P2/P4/P5 | report; labeled **PROJECTION** | Ranges + assumptions; never headline-as-measured |
| Dependency detection recall | P3 | ≥ 0.80 *(provisional)* | On audited citation-context set |
| False-alarm reduction vs. citation-level | P3 | ≥ 50% *(provisional)* | At the recall above |
| $/retraction analyzed | P3 | measured, reported | Headline cost number |
| Reproducibility | All | One command regenerates each reported table | `make report` or documented script |

**Kill / pivot rules (apply honestly):**
- P1: if feasibility spike cannot find a sub-topic meeting the minimums, broaden to multiple sub-topics or lower minimums via ADR; do not fabricate labels.
- P2: if no configuration reaches ≥ 50% savings within 2 points of baseline precision, publish the negative result and proceed with the best frontier point.
- P2 students: if students cannot reach within **2 points of baseline precision** on the gold test at any label budget, publish the negative result and fall back to the best cascade without students.
- P3: if dependency detection cannot beat the citation-level baseline on false alarms at ≥ 0.70 recall, stop and write up why; do not ship the claim.

## 7. Architecture (planned; see `docs/ARCHITECTURE.md`)

Pipeline (layered, demand-driven):
- **Layer 0 — deterministic.** Ingest, parse, flag, expand, deduplicate, and cache. No model calls.
- **Layer 1 — students.** Small encoder models triage claim sentences and citation-context reliance on the bulk of the hot corpus.
- **Layer 2 — rare escalation.** Low-confidence items move to a small LLM, then a large LLM. Escalated cases are written back as new silver labels for retraining (the flywheel).
- **Layer 3 — lazy/incremental.** Process each paper once via content/ID hashes, prioritize by risk, and leave the cold corpus unprocessed until needed.

1. **Ingest** — Europe PMC search/fetch (JATS) → raw store. No LLM.
2. **Parse** — JATS → sections, paragraphs, references, citation contexts. No LLM.
3. **Flag ingestion** — retraction records → link to corpus papers by DOI/PMID/PMCID.
4. **Expand + schedule** — for each flagged source paper A, find citing papers B and their citation contexts; enqueue contexts citing flagged work first. No LLM.
5. **Student triage** — claim-sentence and reliance students label the bulk of hot-corpus items. No LLM.
6. **Escalate** — only low-confidence items go to a small LLM, then a large LLM; log the parent call and feed the resulting labels back into the silver store.
7. **Link** — match relying contexts to specific claims in A (embedding/student match; LLM only if ambiguous).
8. **Process once** — hash-cached, paper-level idempotent runs; cold items remain pending.
9. **Propagate** — compute trust change with the documented rule.
10. **Serve** — API + dashboard with cost panel and a separately labeled projection table.

### 7.1 Stack (decided; see ADRs)
| Layer | Choice |
| :-- | :-- |
| Language | Python 3.11 |
| API | FastAPI + Uvicorn, Pydantic v2 |
| Graph | Neo4j 5.x Community (blast radius is graph traversal) |
| Vectors | ChromaDB persistent, local embeddings (sentence-transformers) |
| Students | Small encoder models trained on teacher silver labels; local inference |
| Ledger / run metadata / labels | SQLite (single file, easy to ship and inspect), including `llm_calls` and `training_runs` |
| LLM access | Provider-agnostic `LLMClient` with tiering, retry, cooldown, caching, mandatory ledger |
| Tests | pytest; offline by default |
| Lint/format/types | ruff, mypy (strict on `src/axion`) |
| CI | GitHub Actions: lint, type-check, offline tests |
| Frontend (P4) | Minimal Next.js/React view; may reuse V1 design tokens |

### 7.2 Planned repository layout
```
retractionscope/
├── AGENTS.md  CONTEXT.md  README.md
├── docs/                 # tracked documentation (this tree)
├── _private/             # UNTRACKED dev-assist files (gitignored)
├── src/axion/
│   ├── config/           # settings, pricing.yaml, stage configs
│   ├── llm/              # LLMClient, providers, ledger
│   ├── ingest/           # europepmc client, retraction data loader
│   ├── parse/            # JATS parser, citation-context extractor
│   ├── extract/          # deterministic + student + escalation stages, claim extraction
│   ├── link/             # context→claim linking, dependency detector
│   ├── train/            # silver labeling, student training, evaluation
│   ├── schedule/         # priority queue, incremental/hash-cached work
│   ├── propagate/        # trust propagation rules
│   ├── store/            # neo4j, chroma, sqlite access (incl. labels, training_runs)
│   └── api/              # FastAPI app
├── eval/                 # gold audit + silver manifests (large artifacts not committed)
├── tests/
├── scripts/              # reproducible report builders (incl. cost_model.py)
└── web/                  # P4 demo UI
```

### 7.3 Planned data model
- Nodes: `Paper{pmcid, pmid, doi, title, year, journal, source}`, `Claim{claim_id, text, section, evidence_span, base_confidence, structured fields}`, `CitationContext{ctx_id, text, section, marker}`, `RetractionNotice{notice_id, date, reason, source}`.
- Edges: `CITES (Paper→Paper)`, `EXTRACTED_FROM (Claim→Paper)`, `IN_PAPER (CitationContext→Paper)`, `POINTS_TO (CitationContext→Paper)`, `DEPENDS_ON (CitationContext|Claim→Claim){label, strength, rationale, confidence, stage, run_id}`, `RETRACTED_BY (Paper→RetractionNotice)`.
- Labels: `Label{label_id, target_id, label, source: teacher|human, teacher_model/version, run_id, split}`. Silver (`source=teacher`) labels train; gold (`source=human`) labels evaluate.
- Every derived edge stores `stage` and `run_id`, so cost and quality can be attributed per stage. Allowed stage values include `rules`, `student`, `teacher_label`, `small_llm`, and `large_llm`.
- SQLite adds `training_runs{run_id, model, data_hash, hardware, duration_s, estimated_usd}` (local training uses `estimated_usd=0` unless a real external cost is incurred).

## 8. Engineering standards

1. **Typing & style:** type hints everywhere in `src/axion`; `ruff` + `mypy --strict` clean before commit. Pydantic v2 models at all boundaries.
2. **Determinism:** pin dependency versions; fix seeds for sampling/evals; persist run configs with results.
3. **Tests:** offline by default (no network, no paid LLM). Network/LLM/integration tests are marked and opt-in. New logic ships with tests; bug fixes ship with a regression test.
4. **LLM access:** only through `LLMClient`. Every call logs to the cost ledger. Prompts live in versioned files, not inline strings. Structured output validated by Pydantic; parse failures are recorded, never silently dropped.
5. **Caching:** content-hash cache in front of every LLM stage. A cache hit is logged as cost $0 with `cache_hit=true`.
6. **Config:** no hard-coded model names, prices, thresholds, or paths. Everything in `src/axion/config/` or env.
7. **Secrets:** only in `.env` (gitignored); `.env.example` documents names. Pre-commit includes a secret scan. Never print secrets in logs.
8. **Logging:** structured logs with `run_id`, `stage`, `paper_id`. No `print` in library code.
9. **Git:** small commits; Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `wip:`); one working branch per phase (`p1`, `p2`, …); commit WIP as `wip: <task-id> <state>`; merge to `main` at task boundaries only when lint, types, and tests are green; delete the phase branch after the gate; never force-push shared branches.
10. **Docs:** public behavior changes update docs in the same commit. Decisions go in `docs/DECISIONS.md`.
11. **Idempotency:** ingestion and pipeline stages are safe to re-run; keys are content/ID based.
12. **No dead code from V1:** ported code is cleaned, tested, and recorded in `docs/PROVENANCE.md`.
13. **Silver trains; gold evaluates.** Teacher/student/heuristic labels are silver and may be used for training only. Human-audited labels are gold and are the only basis for reported evaluation. Split by **paper**, not by claim/context; every paper in gold dev/test is excluded from student training. Record student version/hash with each result; do not commit model artifacts (commit metadata + hashes).

## 9. Evaluation and honesty rules

- Label every machine output a **hypothesis**; keep provenance to the source span.
- Report sample size and a confidence interval (Wilson for proportions) with every rate.
- Keep audit sets, labeling rubric, and label files in-repo (`eval/`, `docs/eval/`); keep label provenance (who/when).
- Agreement check: re-label ≥10% of an audit set after ≥7 days, or use an independent second labeler on a ≥20% blind overlap; report raw agreement and Cohen's κ.
- Never tune on the audit set used for final reporting; maintain a dev split and a frozen test split.
- Publish negative results. Never claim a number the repo cannot regenerate.
- Distinguish **silver** (machine/heuristic) from **gold** (human-audited) labels everywhere.
- Gold is for evaluation: use gold dev for threshold tuning and a frozen gold test for reporting. Never evaluate a student on teacher-labeled data.
- Split by paper, not by claim/context. Student training must exclude every paper in the gold dev/test sets.
- Record student version/hash with every reported result; commit label manifests and hashes, not large model artifacts.

## 10. Cost rules (hard constraints)

1. Every LLM call is logged: `ts, run_id, stage, provider, model, tier, prompt_tokens, completion_tokens, usd, latency_ms, cache_hit, paper_id, parent_call_id, error`.
2. Prices come from `src/axion/config/pricing.yaml`, filled by the owner; if a price is missing, the call fails closed in dry-run and warns loudly otherwise.
3. **Budget guard:** read `_private/budget.md` for phase spend caps. If missing or unspecified, an agent must not run any paid-model batch larger than 20 calls without owner approval.
4. **Dry-run first:** any new batch job supports `--dry-run` that reports expected calls/tokens/cost from the ledger's historical averages before spending.
5. **Never loop LLM calls without a counter and a cap.**
6. **Cache first, small model second, big model last.**
7. Every experiment reports quality **and** cost together; a result without cost is incomplete.
8. Teacher labeling calls are ledgered with stage `teacher_label`; their outputs are silver labels with provenance (teacher model/version, prompt version, run_id).
9. Escalations are ledgered with `parent_call_id` (or the documented equivalent) linking back to the call/stage they escalated from.
10. Training compute is recorded in `training_runs` (run_id, model, data hash, hardware, duration, estimated USD; `0` for local compute unless a real external cost is incurred).
11. The cost projection script must read from the ledger, not hand-typed numbers. It separates **MEASURED** from **PROJECTED** output and prints its assumptions and ranges.

## 11. Agent operating rules (summary; full text in `docs/AGENT_PROTOCOL.md`)

- Read order: `AGENTS.md` → `CONTEXT.md` → `docs/AGENT_PROTOCOL.md` → `docs/PROGRESS.md` → active phase `TODO.md` → relevant PRD section → `_private/` if present.
- **Claim a task** in the phase TODO before starting; **mark it done with evidence** right after finishing. Checkpoint at every task boundary because you may be cut off without warning.
- If interrupted mid-task, leave a **partial-state note** in the task: what is done, what remains, exact next command.
- Do not expand scope; propose via ADR. Stop and ask the owner for: scope changes, spend over cap, destructive/irreversible operations, schema-breaking changes, license/data-terms questions.
- Update `docs/PROGRESS.md` at session end (and mid-session if the session is long).

## 12. Phase map and backlog

| Phase | Name | Target window* | PRD section | TODO |
| :-- | :-- | :-- | :-- | :-- |
| Day 0 | Prerequisites | before P1 | `docs/DAY0_PREREQUISITES.md` | in that doc |
| P1 | Foundation, ledger, corpus, baseline | weeks 1–2 | PRD §P1 | `docs/phases/P1-foundation/TODO.md` |
| P2 | Cost cascade | weeks 3–5 | PRD §P2 | `docs/phases/P2-cost-cascade/TODO.md` |
| P3 | Blast radius | weeks 6–9 | PRD §P3 | `docs/phases/P3-blast-radius/TODO.md` |
| P4 | Demo and dashboard | weeks 10–11 | PRD §P4 | `docs/phases/P4-demo/TODO.md` |
| P5 | Release and write-up | week 12 | PRD §P5 | `docs/phases/P5-release/TODO.md` |

*Assumes ~10 hrs/week; windows stretch, order does not.

**Backlog (not in scope unless ratified by ADR):** port V1 contradiction/reconciliation judge with the three-part decomposition guard; citation-faithfulness checking (does a cited paper support the citing claim); temporal claim decay; Coordinator-style Q&A; Java/other service layers; multi-user auth; self-hosted open-weight inference at volume; calibrated/conformal escalation thresholds; production active-learning loop.

## 13. Non-public context

An untracked `_private/` folder may exist locally. It holds budget caps, outreach strategy, call notes, agent kickoff prompts, and scratch files. Rules:
- Agents read `_private/README.md` and `_private/budget.md` at session start if present.
- Tracked files must **not** quote, summarize, or link `_private/` content beyond this section.
- If something in `_private/` should become public knowledge, restate it in `docs/` deliberately (never copy-paste).
- `_private/` is not in git: back it up separately (see Day-0).

## 14. Reference facts from Axion V1 (for orientation)

- V1: Python 3.11, FastAPI, Neo4j 5.18, ChromaDB (all-MiniLM-L6-v2, 384-d), Next.js 16 UI, RQ+Redis queue; ~48 papers, 2,389 claims.
- V1 retrieval gate: `CONTRADICTION_MAX_DISTANCE` 0.95 → 0.35 passed 42.6% of 11,602 candidate pairs (57.4% fewer judge calls) while 80% of claims kept ≥1 candidate.
- V1 judge pilot: 286 reviewed cross-paper pairs, only 4 `CONTRADICTS`; a stricter variant flagged 15 pairs for 3 true positives. Lesson: base rates are brutal; precision at low prevalence needs ranking and explanation, and cost per correct verdict matters.
- V1 limitations known: extraction precision never formally audited; confidence rule heuristic (`base + 0.08·supports − 0.12·contradictions`, clamped to [0.05, 0.98]); graph/vector stores not transactionally consistent.
- Public comparables for orientation: commercial products group evidence as supporting/mixed/contradicting at query time; research benchmarks exist for claim verification (SciFact) and contextual contradictions (BioDivergence). Do not claim novelty without checking current literature.

**External evidence for the scale approach (orientation, verify before citing; metadata checked 2026-11-14 via arXiv API and Crossref; findings are as reported by the authors and were not independently replicated by us):**
- FrugalGPT (Chen, Zaharia, Zou), arXiv:2305.05176 — LLM cascades can match the best single LLM at lower cost on the tasks tested.
- *Distilling Large Language Models for Biomedical Knowledge Extraction: A Case Study on Adverse Drug Events*, arXiv:2307.06439 — distillation into a task-specific student reported gains over out-of-box LLMs with cost/efficiency advantages.
- MetaIE, arXiv:2404.00457 — a small tuned LM distilled from an LLM can be a strong starting point across information-extraction tasks; the authors report tuned small LMs outperforming prompted LLMs on the IE tasks tested.
- *Distilling Large Language Models for Efficient Clinical Information Extraction*, arXiv:2501.00031 — distilled encoder models reported much lower cost/latency than frontier LLMs on clinical NER.
- scite (Nicholson et al., *Quantitative Science Studies* 2021, doi:10.1162/qss_a_00146) — large-scale classification of citation statements as supporting/contrasting/mentioning; scite also surfaces retracted references in its product (verify current product behavior before citing). This is **prior art for citation-level classification**; V2's novelty claim is claim-level reliance + propagation, not citation-statement classification.

## 15. Risks

| Risk | Mitigation |
| :-- | :-- |
| Not enough retracted OA papers with full text and in-corpus citers | Feasibility spike in P1; broaden sub-topics; ADR before lowering minimums |
| Labeling effort dominates schedule | Budget hours explicitly; small, high-quality audit sets; dev/test split |
| "Depends on" is subjective | Written guideline + double-label subset + report agreement |
| Cost experiments burn budget | Budget guard, dry-run, caching, caps in `_private/budget.md` |
| Scope creep from V1 features | Non-goals list; backlog requires ADR |
| JATS variability across publishers | Parser tests on real samples; coverage stats; fail loudly on unknown structure |
| Student underperforms on fuzzy claim boundaries | Gold-test evaluation; learning curve; fall back to cascade without students per kill rule |
| Teacher errors propagate into silver labels | Teacher provenance; gold audit; monitor student-vs-gold gap; do not treat silver as ground truth |
| Domain/publisher drift requires retraining | Versioned models and labels; drift checks; scheduled re-evaluation |
| Label budget exceeds labeling capacity | Paper-level splits; small high-quality gold sets; learning curve stops at budget |
| Projection overreach | Ledger-driven script; ranges and sensitivity; separate MEASURED vs PROJECTED labels |

## Changelog
- 2026-11-09 — Initial version created at repo bootstrap.
- 2026-11-14 — Adopted ADR-0008 scale approach: four layers, `s + e` planning model, silver/gold separation, paper-level splits, lazy scheduling, and ledger-driven projections.
- 2026-11-14 — Adopted ADR-0010: one working branch per phase (`p1`, `p2`, …), `wip: <task-id> <state>` commits, green-gated merges at task boundaries, and phase-branch deletion after the gate. No history rewrite.
