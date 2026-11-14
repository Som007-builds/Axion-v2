# PROGRESS — live project state

> Agents: update this file at the end of every session (and mid-session if long). Newest log entries first.

## Current state
- **Phase:** P1 (foundation) — P1-01 through P1-09 are `[x]`; P1-10 is offline-complete but blocked for the paid run; P1-11 is blocked on owner labels; P1-12 is scaffolded and blocked on measured values.
- **Owner decisions recorded:** ADR-0011 (clean V2 store rewrite), ADR-0012 (infectious disease, exact-count conditions, PMID limitation, config-driven manifest, oncology deferred), ADR-0013 (total corpus including citers, ~5,000 hard cap), ADR-0014 (P1-10 seeded sample). PRD P1.8 and CONTEXT §4 already use the total-corpus wording.
- **Next action:** owner supplies verified prices, a paid cap, SDK approval, and confirms the 100-paper sample; then run the paid P1-10 baseline and the P1-11 audit.
- **Last updated:** 2026-11-15 by Freebuff / DeepSeek V4.x Flash
- **Build-ready gate:** `docs/reports/D0-readiness.md`

## Day-0 status (2026-11-14 close-out)

Legend: ✅ done · ⛔ owner/local blocker · ⚪ deferred.

**Agent close-out — done**
- ✅ Local `main` contains P1-01, P1-02, DOC-01, and the P1-03 checkpoint (merge `6986af3`). Task branches retained.
- ✅ P1-03 is `[~]` with exact done/left/next-command/gotchas for a fresh P1 thread. (Superseded 2026-11-14: P1-03, P1-03b, P1-04, and P1-05 are now `[x]`.)
- ✅ Only `.env.example` is tracked among env/private paths; `_private/` is ignored.
- ✅ Full-history `detect-secrets` scan: 98 unique blobs across all refs + reflog; 9 unverified false positives; **0 verified secrets**. Custom working-tree scan passed.
- ✅ Provenance audit: 59 V2 blobs vs 185 allowed V1 blobs; only empty `docs/reports/.gitkeep` matched an empty V1 `__init__.py`; no substantive V1 copy.
- ✅ Tests: **89 passed, 1 skipped** (network test opt-in). Ruff check/format and strict mypy pass.
- ✅ Pre-commit hooks install and pass (8/8) when run under Python 3.12; the host's Python 3.11 venv has a virtualenv path bug because the base interpreter is at `D:\`.
- ✅ CI YAML parses and passes `check-yaml`; `actionlint` unavailable.
- ✅ Minimal Neo4j `docker-compose.yml` validates (`docker compose config --quiet`) with loopback ports, healthcheck, env password, named volumes. It has not been started in this close-out.
- ✅ `scripts/day0_check.py` + `make day0-check` + offline tests. No secret values printed.
- ✅ `docs/DATA_SOURCES.md` records verified URLs/date, access methods, Retraction Watch fields, per-article Europe PMC licence rule, polite-usage rules, and explicit unknowns.
- ✅ Phase-thread protocol, D0 handoff, P1–P5 handoff templates, six untracked phase prompts, and the untracked owner action sheet exist.
- ✅ Local Markdown links: 25 files checked, 0 missing.

**Current host readiness — green (2026-11-14, later run)**
`python scripts/day0_check.py`:
- PASS Python 3.11.9.
- PASS environment names (Groq key, both tier model IDs, Neo4j password, and both contact emails present).
- PASS dry-run guard (`AXION_DRY_RUN=true`).
- PASS Docker daemon.
- PASS Neo4j at `bolt://127.0.0.1:7888`; V2 container `axion-v2-neo4j-1` is healthy and `cypher-shell 'RETURN 1'` succeeded.
- V1's stack is still running from `D:\AI-Projects\schimesh` on 7474/7887; V2 uses host ports 7475/7888 so both coexist.

**Owner/local blockers**
- ⛔ Push/CI: `main` is pushed; historical task branches remain local by design (ADR-0010) and CI has not been confirmed.
- ✅ Contact emails, Groq key, Neo4j password, and V2 Neo4j are configured locally; no secret values are tracked.
- ⛔ P1-10: tier IDs are chosen (`openai/gpt-oss-20b`, `openai/gpt-oss-120b`) and public prices are known, but `pricing.yaml` is blank and paid-budget approval is pending.
- ✅ P1-06: Retraction Watch CC0 verified on Crossref’s Metadata Retrieval page and owner-approved; loader/linker and coverage report committed.
- ⛔ P1-08: owner approval of the P1-07 sub-topic ADR.
- ⛔ P1-11/P3-03: owner labeling time (P1-11 also needs a 7-day relabel gap).
- ⚪ Can wait: B5 weekly hours; B6 `_private/` backup risk; P5 licence/release/outreach.

**Recorded facts**
- V1 snapshot: offline suite **252 passed, 12 deselected**; `v1-final` at `b4b6a25338057bd05bc6b74bc75b26198fe546e8`; custom V1 history scan 0 candidate hits; owner reported V1 keys rotated.
- Day-0 decisions: MIT for now; private until P5; $0 paid budget; `_private/` no backup accepted; weekly hours open-ended. ADR-0008 is the scale approach; the Day-0 ADR is ADR-0009. Owner confirmation of the renumbering is requested.
- The GitHub repo is private, but the remote has not received the local commits; visibility alone is not the remaining blocker.

## Phase status
| Phase | Status | Gate result | Notes |
| :-- | :-- | :-- | :-- |
| Day 0 | Agent close-out complete; owner items pending | — | CI confirmation, paid pricing/budget, Retraction Watch terms, labeling time |
| P1 Foundation | In progress | — | P1-01..P1-09 `[x]`; P1-10 offline-complete (paid run blocked on prices/budget/SDK); P1-11 blocked on owner labels; P1-12 scaffolded |
| P2 Cost cascade | Not started | — | |
| P3 Blast radius | Not started | — | |
| P4 Demo | Not started | — | |
| P5 Release | Not started | — | |

## Doc maintenance
| ID | Status | Scope | Evidence |
| :-- | :-- | :-- | :-- |
| DOC-01 | [x] | Scale approach docs: ADR-0008, CONTEXT, PRD P1–P5, phase TODOs, audit rubric, architecture, agent protocol | commit `96fe8f8`; verification recorded in earlier session log |

DOC-01 verification: every PRD step maps to a TODO task ID (and vice versa); superseded P2-03/P2.3 reference ADR-0008; no source/tests/CI/config changed by the docs commit. Doc-only branch: `docs/scale-approach`.

## Headline numbers (update when measured; each must cite its report)
| Metric | Value | Source report |
| :-- | :-- | :-- |
| Claim extraction precision (±95% CI) | — | |
| Baseline cost per paper | — | |
| Cost per paper after cascade | — | |
| Dependency false-alarm reduction vs citation-level | — | |
| $/retraction analyzed | — | |
| JATS citation-context coverage (12 CC BY fixtures) | 12/12 papers, 1,133/1,133 contexts resolved | `docs/reports/P1-jats-coverage.md` |
| Retraction Watch snapshot | 73,822 rows; 68,369 retractions; 93.0% linkable by DOI/PMID | `docs/reports/P1-retraction-coverage.md` |
| Retraction Watch → Europe PMC (seeded n=150) | 80 resolved (53.3%); 54 with full text (67.5% of resolved); 77/80 have citers | `docs/reports/P1-retraction-coverage.md` |
| P1 feasibility shortlist | All 5 pass; infectious disease est. 741 sources / 4,409 contexts / 4,749-paper corpus | `docs/reports/P1-feasibility.md` |
| Infectious-disease corpus (exact) | 4,928 papers; 792 sources; 4,168 citers; 6,117 contexts; 4,928/4,928 parsed | `docs/reports/P1-corpus.md` |
| Full store load (twice) | Paper 4,928; CITES 4,982; contexts 6,117; notices 792; vectors 4,928 + 6,117 | `data/corpus/infectious-disease-v1/store-load.log` |
| P1-10 100-paper dry-run (estimate) | 764,084 prompt tokens; mean 7,641/paper; expected 500 claims at 5/paper | `docs/reports/P1-baseline-estimate.md` |

## Open questions for owner
- **Push:** when will local `main` and the phase branches be pushed to `Som007-builds/Axion-v2`, and will the P1-03/Day-0 work be a direct push or a PR to `main`?
- **Provider/prices:** tier IDs are `openai/gpt-oss-20b` (small) and `openai/gpt-oss-120b` (large) on Groq; enter their published prices in `pricing.yaml` only when the owner approves a paid budget.
- **Live data:** contact emails and Neo4j are configured locally; confirm the addresses are the ones to use for polite-pool requests. Never paste values in chat.
- **Retraction Watch:** resolved 2026-11-14. Crossref’s canonical Metadata Retrieval page lists the database as CC0; owner approved use and the acquisition method (REST lookups + pinned GitLab CSV snapshot; no raw CSV committed). Recorded in `docs/DATA_SOURCES.md`.
- **Sub-topic:** resolved 2026-11-14 — ADR-0012 accepted (`(HSC) Medicine - Infectious Disease`), with the exact-count stop condition and PMID-gap reporting. Oncology deferred to its own ADR as a held-out transfer corpus.
- **Labeling:** when can the owner block ~3–6 hours for P1-11 and ~3–6 hours for P3-03, including the P1-11 7-day relabel gap?
- **ADR renumbering:** confirm ADR-0008 (scale) and ADR-0009 (Day-0) are the intended final numbers.
- **Local tooling:** no GNU `make` on this host; equivalent Python commands are used. Pre-commit under the 3.11 venv fails to create hook envs because its base Python is at `D:\`; the hooks pass under Python 3.12, and CI will use Ubuntu 3.11.
- **Provider SDK adapters:** real Groq/Gemini/Anthropic adapters are deferred until packages are approved/installed. P1-03 is offline and uses a scripted provider.

## Blocked tasks
- P1-10: offline portion complete; the paid run needs verified prices in `pricing.yaml`, a paid-budget cap, the provider SDK dependency, and owner confirmation of the seeded-sample size (dry-run estimate prepared).
- P1-11: owner labeling time (~3–6 h for ≥200 claims) and a ≥7-day relabel gap; tooling is ready.
- P1-12: follows from P1-11 (and the P1-10 run).
- P3-03: owner labeling (later phase).

## Session log (newest first)
### 2026-11-14 — Freebuff / DeepSeek V4.x Flash — P1 SESSION IN PROGRESS (23:55)
- Status: **IN PROGRESS** — second late session; branch `p1`, clean tree at `d02dd57`, no push/merge.
- One ingest runner is already alive from the previous session (detached), 3,400/4,967 full texts and 3,476 cached. Do **not** start a duplicate.
- Plan: (A) let the existing runner finish; (B) full manifest + exact counts, PMID gap, parse coverage, resources; (C) load the full manifest into Neo4j/Chroma twice; (D) semantic MiniLM embeddings only if the disk/time risk is acceptable (C: has ~9 GB free), else document hash as placeholder; (E) build the offline P1-10 baseline path (prompt v1, claim schema, verbatim-span validator, fake-provider runner + dry-run, seeded 100-paper selector, silver-label manifest, provider interface only); (F) P1-12 report scaffold with "not yet measured"; (G) real-corpus dry-run estimate.
- Constraints: no LLM calls, no provider SDKs, prices blank, dry-run on, no labels, no merge/push.
- Checkpoint 2026-11-15 00:50 — **A/B/C/D/E/F/G done to the allowed boundary.** Full ingest finished: **4,928 papers / 792 sources / 4,168 citers / 6,117 contexts**; both §4 minimums pass. Parse coverage 4,928/4,928, 0 failures. Full Neo4j + Chroma (MiniLM) load twice: identical counts in 491s. Semantic stack installed CPU-only (torch 2.5.1+cpu, sentence-transformers 3.3.1), HF cache on D:. Offline P1-10 pipeline and 100-paper dry-run estimate are built; provider SDK and paid calls remain blocked. P1-12 report scaffold emits NOT YET MEASURED placeholders.

#### SESSION HANDOFF FOR THE REVIEWER (2026-11-15 00:50)
**1. Files changed and confidence**
- `src/axion/ingest/corpus_pipeline.py`, `scripts/ingest_corpus.py` — **verified by live full run + tests**; resumed a single runner, 4,928-paper manifest.
- `docs/reports/P1-corpus-{papers.csv,cites.csv,manifest.json,md}`, `P1-corpus-coverage.{md,json}` — **verified by scripts**; IDs only, no full text.
- `src/axion/extract/{claims,prompting,baseline}.py`, `src/axion/extract/prompts/claim-extraction-v1.md`, `scripts/run_baseline_extraction.py`, `src/axion/llm/adapters.py` — **verified by tests + real-corpus dry run**; no provider SDK, no LLM call.
- `scripts/build_p1_report.py`, `Makefile`, `docs/reports/P1-baseline.md` — **verified by test + live generation**; placeholders only where inputs are absent.
- `src/axion/store/{loader,chroma}.py` — **verified by tests + full live load twice**.
- `tests/test_extract_baseline.py`, `tests/test_p1_report.py`, `tests/test_corpus.py`, `tests/test_store_loader.py` — **verified by pytest**.
- **Unverified:** the paid P1-10 run, any precision/cost measurement, and the P1-11 audit.

**2. Commands to re-verify** (use `.venv/Scripts/python.exe`)
```
.venv/Scripts/python.exe -m pytest -q            # 244 passed, 2 skipped
.venv/Scripts/python.exe -m ruff check . && .venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy
.venv/Scripts/python.exe scripts/corpus_coverage.py
.venv/Scripts/python.exe scripts/run_baseline_extraction.py --manifest docs/reports/P1-corpus-manifest.json --sample 100
HF_HOME=D:/hf-cache .venv/Scripts/python.exe scripts/load_stores.py --manifest docs/reports/P1-corpus-manifest.json --chroma-dir data/chroma-full --twice --embedder sentence-transformers
.venv/Scripts/python.exe scripts/build_p1_report.py
```

**3. Known issues / risks**
- 39 full-text downloads are permanent Europe PMC HTTP 500s and are excluded; 6 sources and 34 citers are affected.
- The cap truncated 5,734 eligible citers; context counts are for the included set. 1 source has no PMID, so its citers cannot be discovered.
- Only MED/PPR citation records are kept; other Europe PMC source types are ignored.
- Chroma still prints telemetry warnings from its bundled client; loads succeed and the adapter sets anonymized telemetry off.
- Docker's data lives in WSL on C:, which has 8.6 GB free; Neo4j grew to 545 MB. Watch this before adding more stores.
- `data/chroma-full`, the JATS cache, and the Neo4j volume are untracked and required to reproduce the store load.
- No audit labels exist; precision and the gate remain unmeasured.

**4. Exact counts / resources**
- Corpus: 4,928 papers (792 sources, 4,168 citers, 32 dual-role), 6,117 contexts, 3,976 edges with contexts, 1,006 without; 4,928/4,928 parsed, 0 parse failures; 4,777 papers with ≥1 context.
- Ingest: 3,065.9s wall (resumed process), metadata 3.2s, full text 2,878.1s, parse/context 184.4s; peak RSS 178.2 MiB; cache 644.4 MiB / 4,928 files; 2,089 downloaded + 2,839 cache hits.
- Store load: 491s for two loads; Paper 4,928; CITES 4,982; contexts/IN_PAPER/POINTS_TO 6,117; notices 792; vectors 4,928 + 6,117 + 0 claims. Chroma 53 MB; Neo4j volume 545 MB; raw cache 801 MB on disk.
- Semantic stack: torch 2.5.1+cpu (CUDA false), sentence-transformers 3.3.1, MiniLM 384-d, normalized; HF cache at `D:/hf-cache`.
- P1-10 estimate (100 seeded papers, seed 20261114): **764,084 prompt tokens**, mean 7,641, median 6,971, p95 15,867; output 24k/60k/120k and expected 200/500/1,000 claims at 2/5/10 per paper. No dollar cost (prices blank).

**5. Next 3 actions**
1. Owner: supply verified tier prices, a paid cap, SDK approval, and confirm the 100-paper sample; then run the paid baseline.
2. Draw the ≥200-claim audit sample and label it (P1-11); relabel 10% after ≥7 days.
3. Regenerate `docs/reports/P1-baseline.md` and the gate decision once P1-10/P1-11 have measured values.

### 2026-11-14 — Freebuff / DeepSeek V4.x Flash — P1 SESSION IN PROGRESS
- Status: **IN PROGRESS** — taking over after a usage-limit cutoff. Branch `p1`, clean tree at start (`d4f3171`), no push.
- Plan (in order): (A) verify the unverified P1-08/P1-09 WIP against acceptance criteria + CONTEXT §7.3 and get tests/ruff/format/strict mypy green; (B) move reusable ingest logic from `scripts/ingest_corpus.py` into `src/axion/ingest/` with tests; (C) live smoke ingest (~30–50 papers), then the full infectious-disease corpus up to the ~5,000 cap; (D) exact counts vs §4 minimums + PMID gap; (E) load Neo4j/Chroma twice with identical counts (or in-memory fallback, stated plainly); (F) verify Neo4j heap/page-cache env names, WSL2 guidance, CPU-only torch pin, real resource numbers; (G) P1-10 dry-run readiness estimate only — no extractor code, no SDK, no LLM.
- Constraints: dry-run on, prices blank, $0 budget, zero LLM calls, no merge/push, do not delete the existing `data/corpus/infectious-disease-v1` checkpoint.
- Partial checkpoint found: `data/corpus/infectious-disease-v1/` (citations.jsonl, citers.jsonl, ingest.log, sources_doi.jsonl, sources_pmid.jsonl) — to be inspected, not deleted.
- Checkpoint 2026-11-14 23:44 — **Step A done:** baseline 226 passed/2 skipped, ruff/format/strict mypy clean. **Step B done:** orchestration moved to `src/axion/ingest/corpus_pipeline.py`, CLI thin, orphan-cite validation, bounded full-text batches, end-to-end offline resume test (`231 passed, 2 skipped` at that commit). **Step C partly done:** 30-source smoke ran end-to-end and three consecutive runs produced identical counts/hashes (14 papers, 4 sources, 10 citers, 8 contexts; 0 downloads on the re-run). Full ingest running; 2,898 full texts cached. **Step E partly done:** in-memory and real Neo4j 5.18 + persistent Chroma smoke loads both loaded twice with identical counts (14 papers, 10 CITES, 8 contexts). **Step F partly done:** Neo4j heap/page-cache env names verified via `dbms.listConfig`; host 15.6 GB RAM, D: 134.3 GB free, C: 9.1 GB free, no `.wslconfig`. A stale ingest process from the interrupted session was found and stopped; cap one ingest at a time. **G:** estimator script written and validated on the smoke manifest; real report waits for the full manifest.
- Next update: after the full ingest and store load.

#### SESSION HANDOFF FOR THE REVIEWER (2026-11-14 23:51)
**1. Files changed and confidence**
- `src/axion/ingest/corpus_pipeline.py` — **verified by tests + live smoke + partial live run.** Holds the moved orchestration, bounded full-text batches, per-paper failure capture, cache-size accounting, PMID/MED limits. End-to-end offline resume test passes; 30-source live smoke passed three times with identical counts/hashes.
- `scripts/ingest_corpus.py` — **verified by tests + live smoke** (thin CLI; exit 1 when below §4 minimums, 130 on Ctrl+C).
- `src/axion/store/{loader,chroma}.py` — **verified by tests + live Neo4j/Chroma smoke** (orphan/non-source edges rejected; load twice identical; telemetry off).
- `src/axion/eval/cost_estimate.py`, `scripts/p1_10_estimate.py` — **verified on the smoke manifest only**; final estimate not generated.
- `tests/{test_corpus,test_store_loader,test_cost_estimate}.py` — **verified by pytest.**
- `docs/LOCAL_SETUP.md`, `docs/PROGRESS.md`, `docs/phases/P1-foundation/TODO.md` — docs, verified by review/commands below.
- **Unverified:** the full infectious-disease manifest, its exact counts, full store load, and any P1-10 sample numbers.

**2. Commands to re-verify** (use `.venv/Scripts/python.exe`; bare `python` is a broken D: shim)
```
.venv/Scripts/python.exe -m pytest -q                 # 236 passed, 2 skipped
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe -m ruff format --check .
.venv/Scripts/python.exe -m mypy                      # 38 source files
.venv/Scripts/python.exe scripts/ingest_corpus.py      # resumes; writes docs/reports/P1-corpus-*
.venv/Scripts/python.exe scripts/load_stores.py --manifest docs/reports/P1-corpus-manifest.json --twice
.venv/Scripts/python.exe scripts/p1_10_estimate.py --manifest docs/reports/P1-corpus-manifest.json --sample 50
```

**3. Known issues / risky areas**
- **Full ingest incomplete:** 3,276/4,967 full texts cached; a detached run was at 3,200/4,967 when the session ended and may be killed by session cleanup. No `docs/reports/P1-corpus-*` files exist yet. Check for a running `scripts/ingest_corpus.py` before starting another; never run two.
- A stale ingest from the interrupted session was found still running at 22:25 and was stopped; that is why duplicate requests appeared. Always check process command lines.
- Full-text HTTP 500s are permanent for a few PMCIDs (~11 so far, ~0.7%); they are dropped and counted.
- Chroma verification used the non-semantic `HashEmbedder`; CPU torch/sentence-transformers are pinned in docs but **not installed**. Do not describe the smoke vectors as semantic.
- Only MED/PPR citation records are used; other Europe PMC source types are ignored. PMID-less papers cannot have citers discovered.
- Provisional checkpoint counts (not final manifest): 798 eligible sources; 1 source without PMID; 9,936 eligible MEDLINE citers; 4,202 included; 5,734 truncated by the 5,000 cap.

**4. Exact numbers / resources (measured this session)**
- Tests **236 passed, 2 skipped**; ruff/format clean (69 files); strict mypy clean (38 source files).
- Smoke: 30 records → 4 sources, 10 citers, 14 papers, 8 contexts; three runs identical; last run 0 downloads / 14 cache hits, ~3.8 s.
- Neo4j 5.18: heap 512 MiB initial / 1 GiB max, page cache 512 MiB, verified with `dbms.listConfig()`.
- Host: 15.6 GB RAM; D: 134.3 GB free; C: 9.1 GB free; no `.wslconfig`.
- P1-10 provisional estimate on 14 smoke papers: mean 5,902 tokens/paper (chars/4 heuristic, all parsed sections); final report pending.

**5. Next 3 actions**
1. Resume/complete the ingest, then commit `docs/reports/P1-corpus-{papers.csv,cites.csv,manifest.json,md}` (IDs only).
2. Run `load_stores.py --twice` on the full manifest and record identical graph/vector counts.
3. Generate `P1-baseline-estimate.md` from the full manifest, then ask the owner for prices, budget cap, SDK approval, and sample-size confirmation.

### 2026-11-14 — DeepSeek V4.1 Flash Free — P1-06/P1-07 closed
- Did: verified Crossref’s CC0 statement for Retraction Watch on the canonical Metadata Retrieval page; recorded terms, acquisition rules, snapshot commit/date/hash in `docs/DATA_SOURCES.md`; built the Retraction Watch CSV loader, DOI/PMID index and PMCID resolver hook, added Europe PMC citations/identifier lookups, generated the P1-06 coverage report + ID-only manifest; ran a five-candidate P1-07 feasibility spike (oncology, cardiovascular, infectious disease, gastroenterology, rehabilitation/therapy), wrote `docs/reports/P1-feasibility.md`/`.json`, and proposed ADR-0012 (infectious disease, because it is the only passing candidate whose estimated corpus fits 2,000-5,000).
- State: on `p1`; P1-06/P1-07 `[x]`; all checks green — **209 passed, 2 skipped** (network opt-in), ruff check/format clean (52 files), strict mypy clean (27 source files). Snapshot `560ad745…`; coverage 73,822 rows / 68,369 retractions / 93.0% linkable; seeded n=150 → 80 resolved, 54 full text, 77/80 with citers. All five candidates pass; infectious disease est. 741 sources (653-829), 4,409 contexts (3,498-5,332), 4,749-paper corpus.
- Next: owner approves ADR-0012 or names an alternative; then resume P1-08. Do not start P1-09/P1-10 before their owner decisions; do not push.
- Blockers/questions: P1-08 sub-topic approval; P1-10 prices/budget; P1-11 labeling time + 7-day relabel gap.

### 2026-11-14 — DeepSeek V4.1 Flash Free — P1-03b/04/05 closed; P1-11 tooling ready
- Did: closed P1-03b (ledger tier/escalation/training runs), P1-04 (Europe PMC client), and P1-05 (JATS parser + 12 CC BY golden fixtures + coverage report); prepared the P1-11 audit tooling (`src/axion/eval/audit.py`, `scripts/audit_sample.py`, `scripts/audit_metrics.py`, `eval/audit/README.md`, header-only template) without creating labels; marked P1-06..P1-12 `[!]` with exact unblocks.
- State: on `p1`; commits `809e093`/`f7485ed`/`8bf4d46` earlier, plus `809bd7f` (parse) and `a83a84e` (audit tooling). Full checks: **168 passed, 2 skipped** (network opt-in); ruff check/format and strict mypy (26 files) clean. JATS coverage: 12/12 papers, 1,133 contexts (100% resolved), 0 warnings; reference DOI coverage 102/775 is measured, not a defect.
- Next: owner decisions below; then resume P1-06/P1-07.
- Blockers/questions: Retraction Watch terms, candidate sub-topics, V1-port/rewrite, prices/paid budget, labeling time + 7-day relabel gap.

### 2026-11-14 — DeepSeek V4.1 Flash Free — git workflow (ADR-0010)
- Did: owner decision — one working branch per phase (`p1`, `p2`, …), WIP commits as `wip: <task-id> <state>`, merges to `main` at task boundaries only when lint/types/tests are green, and phase-branch deletion after the gate; updated `CONTEXT.md` §8.9, `docs/AGENT_PROTOCOL.md`, the phase TODO `branch:` fields, and the private phase prompts. No history rewrite.
- State: docs-only; commits `52e16cd` and `cf356fe`; historical task branches and `d0/build-ready` are retained. `main` is unchanged apart from the documentation commits.
- Next: fresh P1 thread creates `p1` from `main` and resumes P1-03; then P1-03b, then P1-04 (owner confirmation required).
- Blockers/questions: owner push/CI and the other standing owner items; old task branches do not need to be pushed.

### 2026-11-14 — DeepSeek V4.1 Flash Free — local env and V2 Neo4j
- Did: selected Groq tier IDs `openai/gpt-oss-20b` (small) and `openai/gpt-oss-120b` (large) from the owner's production list, because both have published prices; owner filled the Groq key, contact emails, and Neo4j password; remapped V2 Neo4j to host 7475/7888 so V1's running stack (`D:\AI-Projects\schimesh`) keeps 7474/7887; fixed Compose passing `NEO4J_PASSWORD` (Neo4j strict validation reads it as setting `PASSWORD`) and made the healthcheck read the password from `NEO4J_AUTH`; updated `.env.example`, `docs/LOCAL_SETUP.md`, and the D0 handoff.
- State: V2 `axion-v2-neo4j-1` healthy; `cypher-shell 'RETURN 1'` succeeded; `python scripts/day0_check.py` → 5/5 PASS; `pytest -q` → **89 passed, 1 skipped**; dry-run stays true and `pricing.yaml` stays blank.
- Next: owner pushes the task branches and confirms CI; fresh P1 thread resumes P1-03.
- Blockers/questions: paid budget/pricing for P1-10, task-branch push/CI, Retraction Watch terms, labeling time.

### 2026-11-14 — DeepSeek V4.1 Flash Free — Day-0 build-ready close-out
- Did: merged P1-03/DOC-01 into local `main`; created `d0/build-ready`; added the D0 tracker and P1-03 resume checkpoint; ran full-history `detect-secrets`; updated `PROVENANCE.md`; added `docker-compose.yml` + `docs/LOCAL_SETUP.md`; added `scripts/day0_check.py` + offline tests + Makefile target; rewrote `DATA_SOURCES.md` with verified terms and unknowns; aligned `.env.example`; added phase-thread protocol and D0/P1–P5 handoffs; created untracked phase prompts and owner action sheet; wrote `D0-readiness.md`.
- State: local `main` contains the checkpoint and the Day-0 close-out (merge `739d0b1`); nothing pushed. Final checks on `main`: 89 passed/1 skipped; ruff/format/mypy clean; pre-commit 8/8 under Python 3.12; Compose config pass; 26 Markdown files, 0 missing local links. Current host `day0-check`: env/Docker failures, Neo4j skip.
- Next: owner pushes private `main` and confirms CI; fresh P1 thread resumes P1-03, then P1-03b, P1-04.
- Blockers/questions: push/CI, contact emails/Neo4j, provider/prices/budget, Retraction Watch terms, labeling time; V1 port/rewrite can wait.

### 2026-11-14 — DeepSeek V4.1 Flash Free — DOC-01
- Did: checkpointed P1-03 locally (`0c79b02` code/tests/config, `16a37fc` docs); created `docs/scale-approach`; recorded ADR-0008 (four layers, `s + e`, alternatives, evidence, risks); updated CONTEXT, PRD, phase TODOs, audit rubric, architecture, and agent protocol.
- State: DOC-01 is doc-only, committed as `96fe8f8`, and fast-forwarded into `p1/P1-03-llmclient`; P1-03 continuation remains the active task.
- Next: return to P1-03; owner Day-0 actions still block any push.
- Blockers/questions: ADR-0008 was already used by the uncommitted Day-0 ADR; renumbered to ADR-0009. External metadata verified 2026-11-14; findings are as reported, not independently replicated. P2-03/P2.3 are superseded by ADR-0008.

### 2026-11-09 — DeepSeek V4.1 Flash Free — Day-0 verification
- Did: recorded owner decisions (ADR-0009); added MIT `LICENSE`; set `_private/budget.md` caps to $0; created local `.env` from the template; started Docker; verified `axion_neo4j` 5.18.1 healthy on loopback; verified Europe PMC + Crossref HTTP 200; ran V1 suite (**252 passed, 12 deselected**); created/pushed V1 tag `v1-final`; ran a custom V1 history secret scan (**0 candidate hits**).
- State: Day-0 close; V2 repo visibility and `.env` values later resolved/partly resolved in the 2026-11-14 close-out.
- Next: owner push/CI and live-data prerequisites; then P1-03.
- Blockers/questions: contact emails, provider/prices, Retraction Watch terms, labeling time.

### 2026-11-09 — DeepSeek V4.1 Flash Free — P1-03
- Did: read V1 reference at `D:\AI-Projects\schimesh` commit `b4b6a25` (`llm.py`, router tests, cache, parser); implemented provider-agnostic `LLMClient` with tier resolution, retry/fallback/cooldown, persistent content-hash cache, SQLite `llm_calls` ledger, Pydantic structured-output validation, and `axion-cost-report`; added settings/env keys and tests.
- State: `p1/P1-03-llmclient` checkpointed at `16a37fc` (code `0c79b02`); local checks green: ruff, ruff format, strict mypy (22 files), **69 tests passed**, secret scan.
- Next: fresh P1 thread re-runs checks, closes P1-03, then P1-03b. Do not start P1-04 without owner confirmation.
- Blockers/questions: provider SDK adapters deferred; local `wheel`/setuptools mismatch for console-script install.

### 2026-11-09 — DeepSeek V4.1 Flash Free — P1
- Did: scaffold sanity check; `git init` + initial scaffold commit; Day-0 status recorded; P1-01 (repo bootstrap) and P1-02 (settings/config) complete.
- State: `main` contains the scaffold and both tasks; local checks green (ruff, mypy strict, 22 offline tests, secret scan).
- Next: P1-03 — LLMClient + cost ledger.
- Blockers/questions: Day-0 owner items remain open but do not block P1-03.

### 2026-11-09 — scaffold generator — Day 0
- Did: created repo scaffold (CONTEXT, PRD, Day-0, protocol, phase TODOs, private folder templates)
- State: nothing committed yet; repo not initialized
- Next: owner completes Day-0 checklist
- Blockers/questions: owner decisions B1–B6
