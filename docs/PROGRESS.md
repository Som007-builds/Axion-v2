# PROGRESS — live project state

> Agents: update this file at the end of every session (and mid-session if long). Newest log entries first.

## Current state
- **Phase:** P1 (foundation) — P1-01 through P1-07 are `[x]`; P1-08 through P1-12 are `[!]` pending owner decisions (sub-topic approval, prices/budget, labeling time).
- **Next action:** **Owner decision** on ADR-0012. Under the total-corpus reading it proposes `(HSC) Medicine - Infectious Disease`; under the base-papers reading it points to oncology. Then a fresh P1 thread resumes P1-08. Read `docs/phases/P1-foundation/TODO.md` first; P1-11 tooling is already prepared and tested.
- **Owner first action:** settle the corpus-bound reading and approve ADR-0012, or name an alternative candidate/corpus bound (unblocks P1-08). See `_private/owner-action-sheet.md`.
- **Last updated:** 2026-11-14 by DeepSeek V4.1 Flash Free
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
| P1 Foundation | In progress | — | P1-01..P1-07 `[x]`; P1-08..P1-12 `[!]` on owner decisions (sub-topic, prices/budget, labeling) |
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

## Open questions for owner
- **Push:** when will local `main` and the phase branches be pushed to `Som007-builds/Axion-v2`, and will the P1-03/Day-0 work be a direct push or a PR to `main`?
- **Provider/prices:** tier IDs are `openai/gpt-oss-20b` (small) and `openai/gpt-oss-120b` (large) on Groq; enter their published prices in `pricing.yaml` only when the owner approves a paid budget.
- **Live data:** contact emails and Neo4j are configured locally; confirm the addresses are the ones to use for polite-pool requests. Never paste values in chat.
- **Retraction Watch:** resolved 2026-11-14. Crossref’s canonical Metadata Retrieval page lists the database as CC0; owner approved use and the acquisition method (REST lookups + pinned GitLab CSV snapshot; no raw CSV committed). Recorded in `docs/DATA_SOURCES.md`.
- **Sub-topic:** approve ADR-0012 (proposed: `(HSC) Medicine - Infectious Disease`, est. 4,749-paper corpus) or choose an alternative from `docs/reports/P1-feasibility.md`.
- **Labeling:** when can the owner block ~3–6 hours for P1-11 and ~3–6 hours for P3-03, including the P1-11 7-day relabel gap?
- **ADR renumbering:** confirm ADR-0008 (scale) and ADR-0009 (Day-0) are the intended final numbers.
- **Local tooling:** no GNU `make` on this host; equivalent Python commands are used. Pre-commit under the 3.11 venv fails to create hook envs because its base Python is at `D:\`; the hooks pass under Python 3.12, and CI will use Ubuntu 3.11.
- **Provider SDK adapters:** real Groq/Gemini/Anthropic adapters are deferred until packages are approved/installed. P1-03 is offline and uses a scripted provider.

## Blocked tasks
- P1-08: owner approves ADR-0012 (infectious-disease sub-topic) or names an alternative candidate/corpus bound. P1-06/P1-07 data and tooling are ready.
- P1-09: follows P1-08; clean V2 rewrite is decided (ADR-0011), so no V1-port question remains.
- P1-10: P1-09 stores, verified prices in `pricing.yaml`, a paid-budget cap, and the provider SDK dependency.
- P1-11: owner labeling time (~3–6 h for ≥200 claims) and a ≥7-day relabel gap; tooling is ready.
- P1-12: follows from P1-11 (and the P1-10 run).
- P3-03: owner labeling (later phase).

## Session log (newest first)
### 2026-11-14 — Freebuff / DeepSeek V4.x Flash — P1 SESSION IN PROGRESS
- Status: **IN PROGRESS** — taking over after a usage-limit cutoff. Branch `p1`, clean tree at start (`d4f3171`), no push.
- Plan (in order): (A) verify the unverified P1-08/P1-09 WIP against acceptance criteria + CONTEXT §7.3 and get tests/ruff/format/strict mypy green; (B) move reusable ingest logic from `scripts/ingest_corpus.py` into `src/axion/ingest/` with tests; (C) live smoke ingest (~30–50 papers), then the full infectious-disease corpus up to the ~5,000 cap; (D) exact counts vs §4 minimums + PMID gap; (E) load Neo4j/Chroma twice with identical counts (or in-memory fallback, stated plainly); (F) verify Neo4j heap/page-cache env names, WSL2 guidance, CPU-only torch pin, real resource numbers; (G) P1-10 dry-run readiness estimate only — no extractor code, no SDK, no LLM.
- Constraints: dry-run on, prices blank, $0 budget, zero LLM calls, no merge/push, do not delete the existing `data/corpus/infectious-disease-v1` checkpoint.
- Partial checkpoint found: `data/corpus/infectious-disease-v1/` (citations.jsonl, citers.jsonl, ingest.log, sources_doi.jsonl, sources_pmid.jsonl) — to be inspected, not deleted.
- Next update: after baseline checks (Step A).

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
