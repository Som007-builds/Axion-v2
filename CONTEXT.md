# CONTEXT.md — Axion V2 Project Bible

> **Audience:** any AI agent or human contributor, at any time.
> **Authority:** this file outranks every other document except an explicit, dated owner instruction recorded in `docs/DECISIONS.md`.
> **Hierarchy of truth:** `CONTEXT.md` > `docs/DECISIONS.md` > `docs/PRD.md` > phase `TODO.md` > code comments.
> **Maintenance:** edit only via a PR/commit that also adds an entry to the changelog at the bottom. Scope-changing edits require an ADR approved by the owner.

---

## 1. One-line purpose

Axion V2 is a **claim-level trust-propagation system for the scientific literature**: when a paper is retracted or flagged, it determines which claims in *other* papers genuinely depended on it, and it does so at a **measured, minimized cost**.

## 2. Why this project exists

### 2.1 Problem
- Retractions and integrity flags are increasingly large-batch events (e.g., conference-proceedings purges, paper-mill takedowns), and AI-generated or fabricated content is entering the literature faster than review capacity grows.
- Existing downstream-impact alerts work at the **citation level** ("this paper cites a retracted paper"). A citation can be a passing mention, a background reference, or a load-bearing premise; citation-level alerts cannot tell these apart and therefore generate false alarms or get ignored.
- LLM-based claim processing over an entire corpus is cost-prohibitive at publisher scale (illustratively, ~$0.01/paper × 20M papers ≈ $200k–$2M depending on assumptions). Any credible system must treat cost as a design constraint, not an afterthought.

### 2.2 Thesis (the "two bets")
1. **Future-proof bet — claim-level blast radius.** Determine, for a retracted/flagged source paper, which downstream *claims* depend on which *source claims*, and propagate reduced trust accordingly.
2. **Cost bet — demand-driven cascade.** Process only what is needed: expand the graph outward from retracted/flagged nodes, and push work through a cheap-to-expensive cascade so the expensive LLM sees only ambiguous cases. Cost scales with the number of retractions, not with corpus size.

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
- Minimal API + dashboard demonstrating blast radius with a visible cost panel.

### 3.2 Explicitly out of scope (non-goals)
- Not a chatbot, not generic RAG, not a literature Q&A product.
- Not an arbiter of scientific truth. Outputs are hypotheses with provenance.
- No multi-tenant accounts, billing, or production hardening.
- No PDF-first pipeline (JATS first; PDF only as a documented fallback if ever needed).
- No contradiction/reconciliation judge, gap finder, experiment recommender, temporal agent, or Coordinator Q&A loop in V2.0 (see backlog, §12).
- No new data sources beyond Europe PMC + Crossref/Retraction Watch data unless an ADR approves them.

## 4. Domain and data

| Item | Decision |
| :-- | :-- |
| Domain | Open-access biomedical literature (Europe PMC OA subset) |
| Full-text format | JATS XML via Europe PMC REST API |
| Retraction labels | Retraction Watch database as distributed via Crossref (**verify license and fields in Day-0**) |
| Corpus size (initial) | 2,000–5,000 papers in one narrow sub-topic, chosen in Phase 1 by feasibility spike |
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
| Dependency detection recall | P3 | ≥ 0.80 *(provisional)* | On audited citation-context set |
| False-alarm reduction vs. citation-level | P3 | ≥ 50% *(provisional)* | At the recall above |
| $/retraction analyzed | P3 | measured, reported | Headline cost number |
| Reproducibility | All | One command regenerates each reported table | `make report` or documented script |

**Kill / pivot rules (apply honestly):**
- P1: if feasibility spike cannot find a sub-topic meeting the minimums, broaden to multiple sub-topics or lower minimums via ADR; do not fabricate labels.
- P2: if no configuration reaches ≥ 50% savings within 2 points of baseline precision, publish the negative result and proceed with the best frontier point.
- P3: if dependency detection cannot beat the citation-level baseline on false alarms at ≥ 0.70 recall, stop and write up why; do not ship the claim.

## 7. Architecture (planned; see `docs/ARCHITECTURE.md`)

Pipeline (demand-driven):
1. **Ingest** — Europe PMC search/fetch (JATS) → raw store. No LLM.
2. **Parse** — JATS → sections, paragraphs, references, citation contexts. No LLM.
3. **Flag ingestion** — retraction records → link to corpus papers by DOI/PMID/PMCID.
4. **Expand** — for each flagged source paper A, find citing papers B in the corpus and their citation contexts. No LLM.
5. **Cascade** — classify contexts and extract claims through cheap → expensive stages.
6. **Link** — match relying contexts to specific claims in A (embedding match + LLM only if ambiguous).
7. **Propagate** — compute trust change with the documented rule.
8. **Serve** — API + dashboard with cost panel.

### 7.1 Stack (decided; see ADRs)
| Layer | Choice |
| :-- | :-- |
| Language | Python 3.11 |
| API | FastAPI + Uvicorn, Pydantic v2 |
| Graph | Neo4j 5.x Community (blast radius is graph traversal) |
| Vectors | ChromaDB persistent, local embeddings (sentence-transformers) |
| Ledger / run metadata / labels | SQLite (single file, easy to ship and inspect) |
| LLM access | Provider-agnostic `LLMClient` with tiering, retry, cooldown, caching, mandatory ledger |
| Tests | pytest; offline by default |
| Lint/format/types | ruff, mypy (strict on `src/axion`) |
| CI | GitHub Actions: lint, type-check, offline tests |
| Frontend (P4) | Minimal Next.js/React view; may reuse V1 design tokens |

### 7.2 Planned repository layout
```
axion-v2/
├── AGENTS.md  CONTEXT.md  README.md
├── docs/                 # tracked documentation (this tree)
├── _private/             # UNTRACKED dev-assist files (gitignored)
├── src/axion/
│   ├── config/           # settings, pricing.yaml, stage configs
│   ├── llm/              # LLMClient, providers, ledger
│   ├── ingest/           # europepmc client, retraction data loader
│   ├── parse/            # JATS parser, citation-context extractor
│   ├── extract/          # cascade stages, claim extraction
│   ├── link/             # context→claim linking, dependency detector
│   ├── propagate/        # trust propagation rules
│   ├── store/            # neo4j, chroma, sqlite access
│   └── api/              # FastAPI app
├── eval/                 # harness, datasets, results (legacy/ for V1 benchmark)
├── tests/
├── scripts/              # reproducible report builders
└── web/                  # P4 demo UI
```

### 7.3 Planned data model
- Nodes: `Paper{pmcid, pmid, doi, title, year, journal, source}`, `Claim{claim_id, text, section, evidence_span, base_confidence, structured fields}`, `CitationContext{ctx_id, text, section, marker}`, `RetractionNotice{notice_id, date, reason, source}`.
- Edges: `CITES (Paper→Paper)`, `EXTRACTED_FROM (Claim→Paper)`, `IN_PAPER (CitationContext→Paper)`, `POINTS_TO (CitationContext→Paper)`, `DEPENDS_ON (CitationContext|Claim→Claim){label, strength, rationale, confidence, stage, run_id}`, `RETRACTED_BY (Paper→RetractionNotice)`.
- Every derived edge stores `stage` (which cascade stage produced it) and `run_id`, so cost and quality can be attributed per stage.

## 8. Engineering standards

1. **Typing & style:** type hints everywhere in `src/axion`; `ruff` + `mypy --strict` clean before commit. Pydantic v2 models at all boundaries.
2. **Determinism:** pin dependency versions; fix seeds for sampling/evals; persist run configs with results.
3. **Tests:** offline by default (no network, no paid LLM). Network/LLM/integration tests are marked and opt-in. New logic ships with tests; bug fixes ship with a regression test.
4. **LLM access:** only through `LLMClient`. Every call logs to the cost ledger. Prompts live in versioned files, not inline strings. Structured output validated by Pydantic; parse failures are recorded, never silently dropped.
5. **Caching:** content-hash cache in front of every LLM stage. A cache hit is logged as cost $0 with `cache_hit=true`.
6. **Config:** no hard-coded model names, prices, thresholds, or paths. Everything in `src/axion/config/` or env.
7. **Secrets:** only in `.env` (gitignored); `.env.example` documents names. Pre-commit includes a secret scan. Never print secrets in logs.
8. **Logging:** structured logs with `run_id`, `stage`, `paper_id`. No `print` in library code.
9. **Git:** small commits; Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`); branch per task: `p<phase>/<task-id>-<slug>`; never force-push shared branches.
10. **Docs:** public behavior changes update docs in the same commit. Decisions go in `docs/DECISIONS.md`.
11. **Idempotency:** ingestion and pipeline stages are safe to re-run; keys are content/ID based.
12. **No dead code from V1:** ported code is cleaned, tested, and recorded in `docs/PROVENANCE.md`.

## 9. Evaluation and honesty rules

- Label every machine output a **hypothesis**; keep provenance to the source span.
- Report sample size and a confidence interval (Wilson for proportions) with every rate.
- Keep audit sets, labeling rubric, and label files in-repo (`eval/`, `docs/eval/`); keep label provenance (who/when).
- Self-consistency check: re-label ≥10% of an audit set after ≥7 days; report agreement.
- Never tune on the audit set used for final reporting; maintain a dev split and a frozen test split.
- Publish negative results. Never claim a number the repo cannot regenerate.
- Distinguish **silver** (machine/heuristic) from **gold** (human-audited) labels everywhere.

## 10. Cost rules (hard constraints)

1. Every LLM call is logged: `ts, run_id, stage, provider, model, prompt_tokens, completion_tokens, usd, latency_ms, cache_hit, paper_id, error`.
2. Prices come from `src/axion/config/pricing.yaml`, filled by the owner; if a price is missing, the call fails closed in dry-run and warns loudly otherwise.
3. **Budget guard:** read `_private/budget.md` for phase spend caps. If missing or unspecified, an agent must not run any paid-model batch larger than 20 calls without owner approval.
4. **Dry-run first:** any new batch job supports `--dry-run` that reports expected calls/tokens/cost from the ledger's historical averages before spending.
5. **Never loop LLM calls without a counter and a cap.**
6. **Cache first, small model second, big model last.**
7. Every experiment reports quality **and** cost together; a result without cost is incomplete.

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

**Backlog (not in scope unless ratified by ADR):** port V1 contradiction/reconciliation judge with the three-part decomposition guard; citation-faithfulness checking (does a cited paper support the citing claim); temporal claim decay; Coordinator-style Q&A; Java/other service layers; multi-user auth.

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

## 15. Risks

| Risk | Mitigation |
| :-- | :-- |
| Not enough retracted OA papers with full text and in-corpus citers | Feasibility spike in P1; broaden sub-topics; ADR before lowering minimums |
| Labeling effort dominates schedule | Budget hours explicitly; small, high-quality audit sets; dev/test split |
| "Depends on" is subjective | Written guideline + double-label subset + report agreement |
| Cost experiments burn budget | Budget guard, dry-run, caching, caps in `_private/budget.md` |
| Scope creep from V1 features | Non-goals list; backlog requires ADR |
| JATS variability across publishers | Parser tests on real samples; coverage stats; fail loudly on unknown structure |

## Changelog
- 2026-11-09 — Initial version created at repo bootstrap.
