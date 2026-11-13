# PROGRESS — live project state

> Agents: update this file at the end of every session (and mid-session if long). Newest log entries first.

## Current state
- **Phase:** P1 (foundation)
- **Next action:** owner sets the GitHub repo to **private** and fills the pending `.env` values, then confirms the commit exception. Day-0 checks are otherwise complete. P1-03 is code-complete as **uncommitted WIP** on `p1/P1-03-llmclient`; commit/push it next, then start P1-04 — Europe PMC client.
- **Last updated:** 2026-11-09 by DeepSeek V4.1 Flash Free

## Day-0 status (as of 2026-11-09)

Legend: ✅ done · ⛔ blocked on owner · ⚪ not attempted (needs keys, V1 access, or network).
This block records status only; it does not change the Day-0 checklist.

**Recorded / done this session**
- ✅ B1 License: MIT for now; `LICENSE` added and ADR-0008 recorded; revisit before P5.
- ✅ B2 decision: private until P5. **The GitHub repo is currently public and must be switched to private before any push.**
- ✅ B3 decision: both tiers stay configurable; only one Groq provider/key for now; fallback chain `groq`; model IDs live in `.env`, never code.
- ✅ B4 Budget: default **$0 paid usage** recorded; untracked `_private/budget.md` caps set to 0.
- ⚠️ B6 `_private` backup: owner accepts **no backup** for now (explicit ADR-0008 exception to ADR-0006).
- ✅ V1 snapshot: offline suite **252 passed, 12 deselected**; `v1-final` tag created and pushed; commit `b4b6a25338057bd05bc6b74bc75b26198fe546e8`; custom history secret scan found 0 candidate hits (`gitleaks`/`trufflehog` unavailable).
- ✅ V2 remote exists but is empty; GitHub API reports `private: false` (visibility blocker above).
- ✅ Docker daemon started; existing `axion_neo4j` (`neo4j:5.18-community`) healthy on loopback `127.0.0.1:7474` and `127.0.0.1:7887`. This is the V1 container; V2 will own its own in P1-09.
- ✅ Europe PMC REST reachable (HTTP 200, JSON) and Crossref reachable (HTTP 200); contact emails still pending.
- ✅ Python 3.11.9; `D:` has ~145 GB free.
- ✅ Local `.env` created from `.env.example`; values pending owner. It is gitignored.
- ✅ `docs/PROVENANCE.md` and `docs/DATA_SOURCES.md` templates present; gitignore verified for `.env` and `_private/`.

**Still blocked on owner (👤)**
- ⛔ B2 follow-through: change GitHub repo visibility from **public** to **private** before any push.
- ⛔ B5 weekly hours not supplied; Day-0 default (~10 hrs/week) recorded in ADR-0008 until changed.
- ⛔ Fresh API keys generated; V1 keys rotated/revoked.
- ⛔ Fill local `.env`: `GROQ_API_KEY`, `CROSSREF_CONTACT_EMAIL`, `EUROPEPMC_CONTACT_EMAIL`, `LLM_SMALL_MODEL`, `LLM_LARGE_MODEL`, and Neo4j values.
- ⛔ Retraction Watch data obtained and license/terms verified; fill `docs/DATA_SOURCES.md`.
- ⛔ Confirm the commit exception: `docs/DAY0_PREREQUISITES.md` §F.6 vs. the existing scaffold commit and P1-03 WIP.
- ⚠️ `_private/` has no backup by owner decision (accepted risk).

**Not attempted / intentionally deferred**
- ⚪ Full V2 Neo4j container ownership and schema (P1-09).
- ⚪ Real local `.env` values (template only).
- ⚪ Paid LLM calls and prices (intentionally blocked; dry-run/fail-closed only).

P1-01, P1-02, and P1-03 are **not** blocked by the above: all are offline and need no keys or live provider calls. Commit/push for P1-03 is held until the repo is private, `.env` is filled, and the commit exception is confirmed.

## Phase status
| Phase | Status | Gate result | Notes |
| :-- | :-- | :-- | :-- |
| Day 0 | Almost complete | — | Repo visibility, `.env` values, key rotation, weekly hours, Retraction Watch terms, commit exception |
| P1 Foundation | In progress | — | P1-01/P1-02 merged; P1-03 code+tests complete as uncommitted WIP |
| P2 Cost cascade | Not started | — | |
| P3 Blast radius | Not started | — | |
| P4 Demo | Not started | — | |
| P5 Release | Not started | — | |

## Headline numbers (update when measured; each must cite its report)
| Metric | Value | Source report |
| :-- | :-- | :-- |
| Claim extraction precision (±95% CI) | — | |
| Baseline cost per paper | — | |
| Cost per paper after cascade | — | |
| Dependency false-alarm reduction vs citation-level | — | |
| $/retraction analyzed | — | |

## Open questions for owner
- **Repository visibility:** GitHub API reports `Som007-builds/Axion-v2` as **public**. The owner decision is private until P5; flip it to private before any push. `gh` CLI is not installed.
- **Commit exception:** `docs/DAY0_PREREQUISITES.md` §F.6 says the first commit waits for Day-0, but the scaffold and P1-01/P1-02 were already committed on owner instruction. Confirm that `dde455c` and the P1-01/P1-02 merges stand, and that P1-03 WIP may be committed/pushed after the remaining owner actions.
- **Weekly hours (B5):** not supplied. ADR-0008 records the Day-0 default (~10 hrs/week) until the owner changes it.
- **Local `.env`:** created from `.env.example`; still needs `GROQ_API_KEY`, contact emails, both tier model IDs, and Neo4j values. Do not paste keys in chat.
- **V1 key rotation:** V1 history contains only `.env.example` (no `.env`/`.env.bak`), and the custom scan found 0 candidate hits, but any V1 keys ever shared or used outside the repo should still be rotated/revoked.
- **Retraction Watch:** data acquisition and current license/redistribution terms still need owner verification in `docs/DATA_SOURCES.md`.
- **Provider SDK adapters:** real Groq/Gemini/Anthropic adapters are deferred until the pinned packages are approved/installed. P1-03 is offline and uses a scripted provider.
- **Local tooling:** this Windows host has no GNU `make`; the exact underlying commands are used locally. The venv lacks `wheel` and has setuptools 65.5.0 (pyproject requires >=68), so `axion-cost-report` is verified via `python -m axion.llm.cli`; normal installs/CI will generate the executable.

## Blocked tasks
- Day-0 owner (👤) follow-through: set repo private; fill `.env`; rotate/revoke V1 keys; confirm weekly hours; verify Retraction Watch terms; confirm the commit exception.
- P1-04 live fetch acceptance is blocked until `.env` has contact emails and the owner confirms live network use for the task (Day-0 reachability checks are done).

## Session log (newest first)
### 2026-11-09 — DeepSeek V4.1 Flash Free — Day-0 verification
- Did: recorded owner decisions (ADR-0008); added MIT `LICENSE`; set `_private/budget.md` caps to $0; created local `.env` from the template; started Docker; verified `axion_neo4j` 5.18.1 healthy on loopback; verified Europe PMC + Crossref HTTP 200; ran V1 suite (**252 passed, 12 deselected**); created/pushed V1 tag `v1-final`; ran a custom V1 history secret scan (**0 candidate hits**).
- State: Day-0 is close; the GitHub repo is still **public**, `.env` values are pending, V1 key rotation and Retraction Watch terms are owner actions. P1-03 remains uncommitted WIP.
- Next: owner flips repo to private and fills `.env`; confirm commit exception; then commit/push P1-03 and start P1-04.
- Blockers/questions: repo visibility, `.env` values, key rotation, B5 weekly hours, Retraction Watch terms, commit exception.

### 2026-11-09 — DeepSeek V4.1 Flash Free — P1-03
- Did: read V1 reference at `D:\AI-Projects\schimesh` commit `b4b6a25` (`llm.py`, router tests, cache, parser); implemented provider-agnostic `LLMClient` with tier resolution, retry/fallback/cooldown, persistent content-hash cache, SQLite `llm_calls` ledger, Pydantic structured-output validation, and `axion-cost-report`; added settings/env keys and 47 new/updated tests.
- State: `p1/P1-03-llmclient` has uncommitted WIP. Local checks green: ruff, ruff format, strict mypy (22 files), **69 tests passed**, secret scan.
- Next: owner completes Day-0, then commit/push P1-03. Do not start P1-04 without owner confirmation (its acceptance needs live network/cache data).
- Blockers/questions: commit/push hold; provider SDK adapters deferred; local `wheel`/setuptools mismatch for console-script install. See Open questions above.

### 2026-11-09 — DeepSeek V4.1 Flash Free — P1
- Did: scaffold sanity check; `git init` + initial scaffold commit; Day-0 status recorded; P1-01 (repo bootstrap) and P1-02 (settings/config) complete.
- State: `main` contains the scaffold and both tasks; local checks green (ruff, mypy strict, 22 offline tests, secret scan).
- Next: P1-03 — LLMClient + cost ledger.
- Blockers/questions: Day-0 owner items remain open but do not block P1-03; see Open questions above.

### 2026-11-09 — scaffold generator — Day 0
- Did: created repo scaffold (CONTEXT, PRD, Day-0, protocol, phase TODOs, private folder templates)
- State: nothing committed yet; repo not initialized
- Next: owner completes Day-0 checklist
- Blockers/questions: owner decisions B1–B6
