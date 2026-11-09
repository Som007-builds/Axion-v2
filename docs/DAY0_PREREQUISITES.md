# Day 0 — Prerequisites and V1 Migration Map

**Purpose:** everything that must be true before Phase 1 starts, including exactly what is (and is not) carried over from the Axion V1 repo.
**Owner action required** on items marked 👤. Agents may do the rest.

---

## A. Principles for the move
1. **Clean-room restart, selective port.** New repo, **no V1 git history**. Port by explicit file list, clean and test each file, record it in `docs/PROVENANCE.md`.
2. **Nothing sensitive crosses over.** Never copy `.env`, local databases, `data/`, PDFs, caches, or logs.
3. **Port ideas before code.** If a V1 file does not fit V2's scope, leave it behind (see table).
4. **Attribution.** V1 is MIT-licensed; keep the copyright notice for ported code.

## B. Owner decisions to record before P1 (👤)
| # | Decision | Default if undecided |
| :-- | :-- | :-- |
| 1 | License for V2 | MIT (same as V1) |
| 2 | Repo name and visibility (public from day one vs. private until P5) | Private until P5 |
| 3 | LLM providers per tier (`small`, `large`) and fallback order | Reuse V1 providers via config; **no model names hard-coded** |
| 4 | Budget caps per phase and a global cap (write in `_private/budget.md`) | Free tiers only; agents must not run paid batches >20 calls without approval |
| 5 | Weekly hours available (affects phase windows) | ~10 hrs/week |
| 6 | Where `_private/` is backed up (private repo, encrypted cloud folder) | Private git repo separate from V2 |

## C. Accounts, tools, environment
- [ ] 👤 New GitHub repo created (empty, no template files).
- [ ] 👤 Fresh API keys generated for each LLM provider (**do not reuse V1 keys**); stored only in local `.env`.
- [ ] 👤 Rotate/revoke any V1 keys that were ever committed, pasted in logs, or shared.
- [ ] Python 3.11 available; Docker + Docker Compose working.
- [ ] Neo4j 5.x container runs locally (port bindings loopback-only).
- [ ] Europe PMC REST API reachable (as far as known, no key required — **verify** rate-limit etiquette).
- [ ] Crossref API access confirmed; set a contact email for polite usage.
- [ ] 👤 Retraction Watch data obtained via Crossref — **verify current license, fields, and redistribution terms**; record in `docs/DATA_SOURCES.md`.
- [ ] Disk budget confirmed for raw JATS cache (several GB headroom).

## D. V1 snapshot (do first, in the V1 repo)
- [ ] Confirm V1 offline suite passes (`pytest`), or note failures.
- [ ] Tag the final V1 state: `git tag v1-final` and push.
- [ ] Record V1 commit hash for provenance.
- [ ] Run a secret scan over V1 history; fix/rotate before anything is copied.

## E. V1 migration map

Legend: **PORT** = copy, clean, test, record provenance · **REDESIGN** = take the idea, write fresh · **LEAVE** = do not carry over · **LEGACY** = keep only as clearly labeled legacy artifact.

| V1 item | Action | Notes for V2 |
| :-- | :-- | :-- |
| `llm.py` (provider router: fallback, transient retry, provider cooldown, optional cache) | **PORT → refactor** | Add tiers (`small`/`large`), structured-output validation, **mandatory SQLite cost ledger**, content-hash cache keyed by prompt+model+params. No hard-coded model names or prices. |
| `config.py` / env handling | **REDESIGN** | Pydantic settings; `pricing.yaml`; stage configs. Keep only env var names that still apply. |
| `embeddings/store.py` (Chroma, MiniLM, local) | **PORT → clean** | Keep local embeddings; new collections for claims and citation contexts; idempotent upserts. |
| `graph/neo4j_client.py`, `neo4j_schema.py`, `neo4j_queries.py` | **PORT client; REDESIGN schema/queries** | New nodes/edges per `CONTEXT.md §7.3`; keep idempotent schema setup. Do not carry unused `Benchmark/Dataset/Method` constraints. |
| `agents/reader.py` (claim extraction, provenance stamping, defensive normalization, min length) | **REDESIGN using its prompt/normalization ideas** | Structured Pydantic output; evidence span validation (span must be found verbatim in source text); parse failures recorded. |
| `ingestion/arxiv_client.py` | **LEAVE** | V2 uses Europe PMC. |
| `ingestion/pdf_parser.py` (PyMuPDF, section split, chunking) | **LEAVE** (optional fallback later) | JATS replaces PDF parsing. Chunking constants (800/100) are not reused. |
| `ingestion/scheduler.py`, `ingestion/progress.py` | **LEAVE** | Not needed for V2 scope. |
| `jobs/` (RQ+Redis worker/queue) | **LEAVE for now** | Revisit only if P3/P4 need background jobs; use simple CLI runs first. |
| `agents/contradiction.py` (gate, 3-part decomposition guard, `diagnostics`) | **LEAVE (backlog)** | Keep as idea for the backlog reconciliation judge; do not port in V2.0. |
| `agents/gap_finder.py`, `experiment_recommender.py`, `temporal.py`, `citation.py` | **LEAVE** | Out of scope. |
| `agents/confidence_updater.py` | **REDESIGN** | Replace heuristic with documented propagation rule v2 (P3). Keep the idea of clamped scores. |
| `agents/coordinator_v2.py`, `planner/reflector/synthesizer` | **LEAVE** | Q&A loop is a non-goal. |
| `api/main.py`, `api/models.py` (auth via shared key, fail-closed, rate limits, `/healthz` vs `/api/health`) | **REDESIGN** | Keep patterns: fail-closed auth, generic 500 body, readiness vs liveness. New endpoints per PRD P4. |
| `docker-compose.yml` (Neo4j + healthchecks, loopback bindings) | **PORT services; trim** | Keep `neo4j` (APOC off unless needed) and healthcheck; drop redis/worker unless justified. |
| `axion/` Next.js frontend | **LEAVE for P4; reuse selectively** | Reuse design tokens, API-client patterns, and brand assets only if desired (consider visual separation from V1). |
| `eval/run_eval.py`, `measure_gate.py`, `judge_ablation.py`, `build_ablation_summary.py` | **REDESIGN using methodology** | Keep: pre-registered protocol style, Wilson CIs, majority/random baselines, cache-keyed resumable runs, "report-only" regeneration. |
| `eval/Data/axion_pairs.csv`, `contradicts_review_labeled.csv`, `labeled_pairs_cleaned.csv` | **LEGACY** | Copy to `eval/legacy/` with a README stating domain (ML/arXiv), label provenance, and 4-positive limitation. Not used for V2 metrics. |
| `eval/Data/train.csv`, `val.csv`, `test.csv`, 0-byte placeholders | **LEAVE** | Obsolete per V1 docs. |
| `eval/results/ablation_cache.jsonl`, large candidate pools, V1 databases/PDF cache | **LEAVE** | Not needed; large or irrelevant. |
| `tests/` | **PORT selectively** | Keep tests for the LLM router and any generic utils; rewrite the rest. |
| `.github/workflows/ci.yml` | **REDESIGN (simplify)** | Lint, mypy, offline tests. Frontend build step only once `web/` exists. |
| `docs/OPERATIONS.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CITATION.cff`, `LICENSE` | **PORT as templates** | Rewrite content for V2; keep MIT notice and attribution. |
| `.env`, `.env.*`, `data/`, `venv/`, `node_modules/`, logs, screenshots, `artifacts/` | **NEVER COPY** | Secrets/state. Regenerate artifacts fresh in V2. |

## F. Procedure to extract from V1
1. In V1, create `v1-final` tag; list files to port in a scratch file (`_private/scratch/port-list.md`).
2. In V2, copy **only** listed files into their V2 locations; do not copy directories wholesale.
3. For each ported file: remove dead code and V1-specific comments, add type hints, add tests, run lint/mypy.
4. Append an entry to `docs/PROVENANCE.md`: V1 path, V1 commit hash, V2 path, what changed, license note.
5. Run a secret scan on the V2 working tree before the first push.
6. Make the first commit only after Day-0 checklist passes.

## G. Day-0 exit checklist
- [ ] Owner decisions B1–B6 recorded (ADR or `_private/`).
- [ ] V1 snapshot tagged; V1 secrets rotated.
- [ ] V2 repo created; this scaffold committed (excluding `_private/`).
- [ ] `docs/PROVENANCE.md` and `docs/DATA_SOURCES.md` created (empty templates ok).
- [ ] `.env.example` created; real `.env` present locally and ignored.
- [ ] `_private/budget.md` filled; `_private/` backed up elsewhere.
- [ ] Neo4j container healthy; Europe PMC and Crossref reachable.
- [ ] Retraction data license verified and noted.
- [ ] `docs/PROGRESS.md` updated: phase = P1, next action = P1-01.
