# PROGRESS — live project state

> Agents: update this file at the end of every session (and mid-session if long). Newest log entries first.

## Current state
- **Phase:** P1 (foundation)
- **Next action:** P1-03 — LLMClient + cost ledger (`docs/phases/P1-foundation/TODO.md`)
- **Last updated:** 2026-11-09 by DeepSeek V4.1 Flash Free

## Day-0 status (as of 2026-11-09)

Legend: ✅ done · ⛔ blocked on owner · ⚪ not attempted (needs keys, V1 access, or network).
This block records status only; it does not change the Day-0 checklist.

**Done by scaffold / this session**
- ✅ Repo scaffold committed (`dde455c`); remote `origin` configured.
- ✅ `.env.example` present (names only, no values).
- ✅ `docs/PROVENANCE.md` and `docs/DATA_SOURCES.md` templates present.
- ✅ Git ignores `_private/`, `.env`/`.env.*` (except `.env.example`), and `data/`.

**Blocked on owner (👤)**
- ⛔ B1 License decision for V2.
- ⛔ B2 Repository visibility (public vs. private until P5).
- ⛔ B3 LLM providers per tier (`small`, `large`) and fallback order.
- ⛔ B4 Budget caps per phase and global cap (local untracked file).
- ⛔ B5 Weekly hours available.
- ⛔ B6 Backup location for the untracked private folder.
- ⛔ Fresh API keys generated; V1 keys rotated/revoked.
- ⛔ Retraction Watch data obtained and license/terms verified (record in `docs/DATA_SOURCES.md`).
- ⛔ V1 snapshot: confirm suite, tag `v1-final`, record commit hash, secret-scan V1 history.
- ⛔ `origin` created as an empty GitHub repository (owner supplied the URL; creation/visibility confirmation pending).

**Not attempted this session (environment/network/V1)**
- ⚪ Docker + Docker Compose; Neo4j container.
- ⚪ Europe PMC and Crossref reachability, polite-pool contact confirmation.
- ⚪ Disk headroom for raw JATS cache.
- ⚪ Real local `.env` with values.

P1-01 and P1-02 are **not** blocked by the above: both are offline and need no keys or V1 access.

## Phase status
| Phase | Status | Gate result | Notes |
| :-- | :-- | :-- | :-- |
| Day 0 | Partially blocked | — | Owner items open; see Day-0 status above |
| P1 Foundation | In progress | — | P1-01 and P1-02 done; P1-03 next |
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
- Day-0 wording conflict: `docs/DAY0_PREREQUISITES.md` §F.6 says the first commit should wait until the Day-0 checklist passes, but this session's owner instruction was to commit the scaffold and start P1-01/P1-02 now. Confirm that `dde455c` stands as the scaffold commit (no Day-0 doc change made).
- Repository visibility, and whether to push `main` and task branches to `origin`. No push was attempted because this session forbade network use.
- Provider→tier mapping, model IDs, and `pricing.yaml` prices are needed before any live LLM call. Offline fake-provider work on P1-03 can proceed without them.
- This Windows host has no GNU `make`. Is running the exact underlying commands locally acceptable evidence, with CI running `make lint typecheck test`? That is what was done this session.

## Blocked tasks
- Day-0 owner (👤) items only: B1–B6, fresh keys/V1 key rotation, V1 snapshot, retraction-data license, repo visibility. None of these block P1-03.

## Session log (newest first)
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
