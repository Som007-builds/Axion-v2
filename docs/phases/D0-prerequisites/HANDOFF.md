# HANDOFF — Day 0 (prerequisites and build-ready close-out)

**Status:** Agent close-out complete; local P1 work can start. `main` is pushed, but the task branches and CI confirmation remain owner items, as do later P1 data/pricing inputs.
**Branch:** local `main` (includes the 2026-11-14 local-env/Neo4j follow-up); `d0/build-ready` is retained for history.
**Last updated:** 2026-11-14

## State
- `main` contains P1-01, P1-02, DOC-01, and the P1-03 checkpoint. Task branches are retained for history.
- P1-03 is deliberately left `[~]` as the first task of the P1 thread, with an exact resume checkpoint in `docs/phases/P1-foundation/TODO.md`.
- Day-0 agent work: local git hygiene, full-history secret scan, provenance audit, minimal Neo4j Compose, `day0-check`, data-source research, config/pricing consistency, phase-thread protocol, handoff templates, phase prompts, and owner action sheet.
- Build-ready gate: see `docs/reports/D0-readiness.md`.

## Decisions
- ADR-0008: scale approach (deterministic layer, distilled students, rare escalation, lazy/incremental work).
- ADR-0009: Day-0 decisions (MIT for now; private until P5; $0 paid budget; no `_private/` backup accepted).
- Provider is Groq. Tier IDs are `openai/gpt-oss-20b` (small) and `openai/gpt-oss-120b` (large); their public prices are known, but `pricing.yaml` stays blank and dry-run stays enabled until the owner approves a paid budget.
- Retraction Watch licence/redistribution terms are **not** confirmed. Treat the raw CSV as non-redistributable until the owner approves `docs/DATA_SOURCES.md`.

## Gotchas
- This Windows host has no GNU `make`; the equivalent Python commands are the verification path. CI runs the Makefile targets on Ubuntu.
- The venv lacks a working `wheel`/setuptools>=68 install, so verify the CLI with `python -m axion.llm.cli`, not the console script.
- Docker Desktop may be stopped; `day0-check` will report Docker/Neo4j failures or skips honestly.
- V1's Neo4j may already own ports 7474/7887. V2 uses host ports 7475/7888 so both can coexist; never reuse V1 volumes or credentials.
- `detect-secrets` reports historical false positives: the literal phrase "secret scan" in P1-01 evidence and a fake test env value. No verified secret was found.
- `main` is on the private remote; do not push the task branches without owner approval. CI has not been confirmed.

## Open risks and owner blockers
- **Hard blocker for normal phase operations:** the task branches are not pushed and CI is unconfirmed; `main` itself is on the remote.
- **P1-04:** local contact emails and Neo4j are configured, but the owner confirmation rule still applies before starting the task. Offline implementation can proceed after confirmation.
- **Hard blocker for P1-10:** `pricing.yaml` is blank and any paid budget needs owner approval.
- **Hard blocker for P1-06/P1-07:** Retraction Watch licence/terms and data acquisition need owner confirmation.
- **Hard blocker later:** owner labeling time for P1-11 (≥200 claims + 10% relabel after ≥7 days) and P3-03 (100–150 contexts).
- **Can wait:** V1 file port/rewrite decision for P1-09; `_private/` backup location; B5 weekly-hours value.

## Exact next step
1. Owner: push the task branches (if desired) and confirm GitHub Actions is green; decide the paid budget and when to enter prices for P1-10.
2. Fresh P1 thread: read this handoff, `docs/phases/P1-foundation/TODO.md`, and PRD §P1. Resume P1-03 at its checkpoint:
   `git switch main` → `python -m pytest -q` → `python -m ruff check .` → `python -m ruff format --check .` → `python -m mypy`.
3. Close P1-03 with fresh evidence, then claim P1-03b. Do not start P1-04 without owner confirmation.

## Gate report
- `docs/reports/D0-readiness.md`

## Session log
- 2026-11-14 — DeepSeek V4.1 Flash Free — Day-0 build-ready close-out; local `main` assembled; owner items handed off. Next: owner gate, then fresh P1 thread resumes P1-03.
- 2026-11-14 — DeepSeek V4.1 Flash Free — local `.env` completed, Groq tiers selected, V2 Neo4j healthy on 7475/7888 beside V1, handoff refreshed. Next: fresh P1 thread resumes P1-03; P1-04 needs owner confirmation.
