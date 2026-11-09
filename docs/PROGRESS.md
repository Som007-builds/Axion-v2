# PROGRESS — live project state

> Agents: update this file at the end of every session (and mid-session if long). Newest log entries first.

## Current state
- **Phase:** Day 0 (prerequisites)
- **Next action:** complete `docs/DAY0_PREREQUISITES.md` checklist (owner decisions B1–B6, V1 snapshot, accounts), then start `P1-01` in `docs/phases/P1-foundation/TODO.md`
- **Last updated:** 2026-11-09 by scaffold generator

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
| Day 0 | Not started | — | |
| P1 Foundation | Not started | — | |
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
- (none)

## Blocked tasks
- (none)

## Session log (newest first)
### 2026-11-09 — scaffold generator — Day 0
- Did: created repo scaffold (CONTEXT, PRD, Day-0, protocol, phase TODOs, private folder templates)
- State: nothing committed yet; repo not initialized
- Next: owner completes Day-0 checklist
- Blockers/questions: owner decisions B1–B6
