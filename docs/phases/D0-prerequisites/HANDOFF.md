# HANDOFF — Day 0 (prerequisites and build-ready close-out)

**Status:** Agent close-out complete; owner-only items remain. Local P1 work can start, but push/CI and some later P1 tasks wait on the owner.
**Branch:** local `main` plus `d0/build-ready`; no push was made in this close-out.
**Last updated:** 2026-11-14

## State
- `main` contains P1-01, P1-02, DOC-01, and the P1-03 checkpoint. Task branches are retained for history.
- P1-03 is deliberately left `[~]` as the first task of the P1 thread, with an exact resume checkpoint in `docs/phases/P1-foundation/TODO.md`.
- Day-0 agent work: local git hygiene, full-history secret scan, provenance audit, minimal Neo4j Compose, `day0-check`, data-source research, config/pricing consistency, phase-thread protocol, handoff templates, phase prompts, and owner action sheet.
- Build-ready gate: see `docs/reports/D0-readiness.md`.

## Decisions
- ADR-0008: scale approach (deterministic layer, distilled students, rare escalation, lazy/incremental work).
- ADR-0009: Day-0 decisions (MIT for now; private until P5; $0 paid budget; no `_private/` backup accepted).
- Provider choice is still unresolved: the configured chain says Groq, but the local key situation must be reconciled by the owner. Pricing stays blank and dry-run stays enabled.
- Retraction Watch licence/redistribution terms are **not** confirmed. Treat the raw CSV as non-redistributable until the owner approves `docs/DATA_SOURCES.md`.

## Gotchas
- This Windows host has no GNU `make`; the equivalent Python commands are the verification path. CI runs the Makefile targets on Ubuntu.
- The venv lacks a working `wheel`/setuptools>=68 install, so verify the CLI with `python -m axion.llm.cli`, not the console script.
- Docker Desktop may be stopped; `day0-check` will report Docker/Neo4j failures or skips honestly.
- A V1 Neo4j container may already own ports 7474/7887. Stop it before running V2's Compose stack; never reuse V1 volumes.
- `detect-secrets` reports historical false positives: the literal phrase "secret scan" in P1-01 evidence and a fake test env value. No verified secret was found.
- Do not push while the repo visibility/push gate is open.

## Open risks and owner blockers
- **Hard blocker for normal phase operations:** repository is still public and the local commits/branches are not pushed; CI cannot run until the owner completes the visibility/push gate.
- **Hard blocker for live P1 fetch:** contact emails are missing; P1-04/P1-05/P1-06 live acceptance waits. Offline implementation can proceed.
- **Hard blocker for P1-10:** provider/model IDs, verified prices, and any paid budget are not ready.
- **Hard blocker for P1-06/P1-07:** Retraction Watch licence/terms and data acquisition need owner confirmation.
- **Hard blocker later:** owner labeling time for P1-11 (≥200 claims + 10% relabel after ≥7 days) and P3-03 (100–150 contexts).
- **Can wait:** V1 file port/rewrite decision for P1-09; `_private/` backup location; B5 weekly-hours value.

## Exact next step
1. Owner: work through `_private/owner-action-sheet.md` in order, starting with making the V2 repository private and pushing local `main` plus task branches.
2. Fresh P1 thread: read this handoff, `docs/phases/P1-foundation/TODO.md`, and PRD §P1. Resume P1-03 at its checkpoint:
   `git switch main` → `python -m pytest -q` → `python -m ruff check .` → `python -m ruff format --check .` → `python -m mypy`.
3. Close P1-03 with fresh evidence, then claim P1-03b. Do not start P1-04 without owner confirmation.

## Gate report
- `docs/reports/D0-readiness.md`

## Session log
- 2026-11-14 — DeepSeek V4.1 Flash Free — Day-0 build-ready close-out; local `main` assembled; owner items handed off. Next: owner gate, then fresh P1 thread resumes P1-03.
