# TODO — Day 0 — build-ready close-out

**PRD:** `docs/PRD.md` (Day 0) · **Gate:** build-ready gate in `docs/reports/D0-readiness.md` · **Update this file as you work.**

This tracker covers the owner-requested Day-0 close-out that makes the repository safe and complete enough for fresh per-phase agent threads. It does not start P1-04 or any new P1 task.

## Status legend
`[ ]` todo · `[~]` in progress (needs agent/started/branch) · `[x]` done (needs evidence) · `[!]` blocked (needs reason) · `[-]` dropped (needs ADR ref)

## Rules (read `docs/AGENT_PROTOCOL.md` for full text)
- Claim a task (`[~]`) before starting; mark `[x]` with evidence when done; checkpoint notes at every step.
- `AGENT` tasks are done by the agent. `OWNER` tasks require the owner and are recorded here so a fresh thread can see them.
- No push, no paid calls, no LLM calls, no scope expansion in Day 0.
- Network use is read-only research and reachability checking only; never send secrets.
- Do not quote or reference `_private/` contents in tracked files.

## Agent tasks

### [x] D0-01 — Verify and checkpoint P1-03 (AGENT)
- depends: P1-03 code checkpoint
- what: Re-run the P1-03 checks; record exact done / left / next command / gotchas so a fresh P1 thread can resume; leave P1-03 as the first task of the P1 thread.
- acceptance: Tests, lint, format, and strict mypy are green; P1-03 is `[~]` with a resumable partial-state note; no P1 feature work is started.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: d0/build-ready
  - notes:
    - 2026-11-14 claimed as part of the Day-0 close-out.
    - Re-ran the checkpoint checks; P1-03 remains `[~]` with the exact resume note in `docs/phases/P1-foundation/TODO.md`.
  - done: 2026-11-14 | evidence: P1 checkpoint `97b7d07`; `pytest -q` → **69 passed**; `ruff check .` → passed; `ruff format --check .` → 32 files formatted; `mypy` → success, 22 source files. No P1 feature work started.

### [x] D0-02 — Local git hygiene and branch policy (AGENT)
- depends: D0-01
- what: Create a clean local `main` containing P1-01, P1-02, DOC-01, and the P1-03 checkpoint; keep task branches for history; document the task-branch rule for phase threads; verify only `.env.example` is tracked among env/private paths.
- acceptance: Local `main` contains the work; task branches remain; `git ls-files` shows only `.env.example` for env/private paths; branch rule is in `docs/AGENT_PROTOCOL.md`.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: d0/build-ready
  - notes:
    - 2026-11-14 merged `p1/P1-03-llmclient` into local `main` as `6986af3`; created `d0/build-ready`.
    - Kept `p1/P1-01-bootstrap`, `p1/P1-02-settings`, `p1/P1-03-llmclient`, and `docs/scale-approach` for history.
  - done: 2026-11-14 | evidence: merge `6986af3`; local branches `main`, `d0/build-ready`, `p1/P1-03-llmclient`; `docs/AGENT_PROTOCOL.md` §3 branching rule; `git ls-files | Select-String '_private|\.env'` → only `.env.example`.

### [x] D0-03 — Full-history secret scan and provenance audit (AGENT)
- depends: D0-02
- what: Run a full-history secret scan with `gitleaks` or `detect-secrets` if available; otherwise use the strongest available fallback and record the limitation. Audit whether any tracked V2 file was copied from V1 or written fresh; update `docs/PROVENANCE.md` honestly.
- acceptance: Scan result recorded; `docs/PROVENANCE.md` states the copy/fresh status; no secrets found or every finding is explained.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: d0/build-ready
  - notes:
    - `gitleaks` and `trufflehog` were unavailable; installed `detect-secrets==1.5.0` into the local venv for the requested scan.
    - Exported 98 unique text blobs from all refs plus reflog, preserving original paths, then scanned with `detect-secrets scan --all-files --no-verify`.
    - 9 findings, all unverified false positives: repeated historical copies of the P1-01 evidence line containing the phrase "secret scan" (Secret Keyword) and the fake test env value in `tests/test_settings.py` (Base64 High Entropy String). No credential or private key was found.
    - The custom `scripts/check_secrets.py` working-tree scan passed. No history was rewritten.
  - done: 2026-11-14 | evidence: `detect-secrets` 1.5.0 full-history scan: 98 blobs, 9 unverified false positives, 0 verified secrets; `python scripts/check_secrets.py` → passed; `docs/PROVENANCE.md` fresh-vs-copied audit (59 V2 blobs vs 185 allowed V1 blobs; only empty `docs/reports/.gitkeep` hash match, not a substantive copy).

### [x] D0-04 — Minimal Neo4j Docker Compose (AGENT)
- depends: D0-02
- what: Add a minimal `docker-compose.yml` with Neo4j 5.x only, a healthcheck, loopback-only ports, password from the environment, and named volumes. Document it briefly.
- acceptance: Compose file validates with `docker compose config --quiet`; no Redis/worker/API services; no secret values committed.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: d0/build-ready
  - notes:
    - Added Neo4j 5.18 Community only; no V1 data volumes or extra services.
    - Validated with a temporary dummy process environment value; no real password printed.
  - done: 2026-11-14 | evidence: `docker-compose.yml`; `docs/LOCAL_SETUP.md`; `docker compose config --quiet` → PASS; loopback `127.0.0.1:7474` and `127.0.0.1:7887`; named `neo4j_data`/`neo4j_logs` volumes; healthcheck uses `cypher-shell`.
  - follow-up 2026-11-14: live start found two issues. Host ports were remapped to `7475`/`7888` so V1's stack keeps `7474`/`7887`, and the redundant `NEO4J_PASSWORD` service env var was removed because Neo4j strict validation reads it as setting `PASSWORD`. V2 container is healthy and `cypher-shell 'RETURN 1'` passed.

### [x] D0-05 — `day0-check` script and tests (AGENT)
- depends: D0-02
- what: Add `scripts/day0_check.py` and `make day0-check`; check Python version, env var names (never values), Docker, Neo4j when reachable, and opt-in Europe PMC/Crossref reachability with contact email. Add offline unit tests.
- acceptance: Offline tests pass; script prints PASS/FAIL/SKIP per check; network checks are opt-in; no secret values are printed.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: d0/build-ready
  - notes:
    - Added `scripts/day0_check.py`, `scripts/__init__.py`, `tests/test_day0_check.py`, and a `make day0-check` target.
    - Current local run reports honest failures/skips: missing owner env names, Docker daemon unreachable at this moment, Neo4j configured but not reachable. It prints names/status only, never values.
  - done: 2026-11-14 | evidence: `scripts/day0_check.py`; `tests/test_day0_check.py`; `pytest -q` → **89 passed, 1 skipped** (network test opt-in via `AXION_RUN_NETWORK=1`); `ruff check .` and `ruff format --check .` → passed; direct `python scripts/day0_check.py` prints PASS/FAIL/SKIP. `make` is unavailable on this Windows host, so the target was verified by running its command directly.
  - follow-up 2026-11-14: current host now passes all five checks after the owner filled `.env` and the V2 Neo4j stack was started.

### [x] D0-06 — Data-source terms research (AGENT)
- depends: D0-02
- what: Research Europe PMC OA-subset full-text use/redistribution and Retraction Watch data via Crossref (access, fields, license, redistribution), plus polite-usage rules and observed rate limits. Record source URLs, verification date, and "owner to confirm" on every row.
- acceptance: `docs/DATA_SOURCES.md` has verified rows and explicit unknowns; no unverified claim is stated as fact.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: d0/build-ready
  - notes:
    - Verified the Europe PMC OA-subset page, REST page, Crossref Retraction Watch documentation, Crossref API documentation, and the Retraction Watch GitLab README read-only on 2026-11-14.
    - Recorded explicit unknowns: Europe PMC numeric rate limit not published on the accessible page; site terms blocked by bot verification; Retraction Watch CSV repository has no `LICENSE`, and the Crossref site-content CC BY 4.0 footer does not clearly cover the dataset.
    - Observed Crossref public headers: 1 request/second, concurrency 1 (`public-array`). This is a point-in-time observation, not a promise.
  - done: 2026-11-14 | evidence: `docs/DATA_SOURCES.md` rewritten with source URLs, verification date, access methods, Retraction Watch fields, per-article Europe PMC licence rule, polite-usage rules, and an `Owner to confirm` column on every row; all unresolved points marked unclear.

### [x] D0-07 — Settings, `.env.example`, and pricing consistency (AGENT)
- depends: D0-02
- what: Confirm `.env.example` names match settings and local compose; keep `pricing.yaml` a blank fail-closed template; confirm no model names or prices are hard-coded in production code/config.
- acceptance: A test or documented check proves the name match; `pricing.yaml` has `models: {}`; search finds no hard-coded model/pricing values.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: d0/build-ready
  - notes:
    - Updated `NEO4J_URI` to `bolt://127.0.0.1:7887` to match the Compose host-port mapping; the existing `test_env_example_lists_every_setting` covers settings-name coverage.
    - Follow-up 2026-11-14: `NEO4J_URI` moved to `bolt://127.0.0.1:7888` after the V2 port remap; `.env.example` updated to match.
    - `pricing.yaml` remains `models: {}` and the packaged-template test asserts blank prices load.
    - Test fixtures use obviously fake `provider/model-a` and illustrative numbers; production code/CI has no model IDs or numeric prices.
  - done: 2026-11-14 | evidence: `.env.example`; `tests/test_settings.py::test_env_example_lists_every_setting`; `tests/test_pricing.py::test_packaged_template_loads_with_blank_prices`; `pytest -q` → **89 passed, 1 skipped**; `ruff`/format/mypy → passed; production search → no hard-coded model IDs or numeric prices.

### [x] D0-08 — Phase-thread protocol and handoff templates (AGENT)
- depends: D0-02
- what: Add a "Phase thread protocol" section to `docs/AGENT_PROTOCOL.md`; create a filled D0 `HANDOFF.md` and empty P1–P5 `HANDOFF.md` templates.
- acceptance: Protocol covers one thread per phase, previous-phase handoff, end-of-thread handoff, gate report, PROGRESS update, ADR/TODO capture, and stopping at the gate; all template files exist.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: d0/build-ready
  - notes:
    - Added §10 to `docs/AGENT_PROTOCOL.md` and updated the session-start reading order to include the previous phase handoff.
    - D0 handoff is filled in; P1–P5 handoffs are empty templates with the required state/decisions/gotchas/risks/next-step/gate sections.
  - done: 2026-11-14 | evidence: `docs/AGENT_PROTOCOL.md` §1 and §10; `docs/phases/D0-prerequisites/HANDOFF.md`; `docs/phases/P1-foundation/HANDOFF.md`; `docs/phases/P2-cost-cascade/HANDOFF.md`; `docs/phases/P3-blast-radius/HANDOFF.md`; `docs/phases/P4-demo/HANDOFF.md`; `docs/phases/P5-release/HANDOFF.md`. No source/tests/CI changes.

### [x] D0-09 — Fresh-thread phase prompts (AGENT, untracked)
- depends: D0-08
- what: Create `_private/phase-prompts/P1.md` … `P5.md` and `_private/phase-prompts/mid-phase-resume.md` with reading order, phase goal/gate, owner-only tasks, budget rules, stop conditions, and exact deliverables.
- acceptance: Files exist under `_private/` only; tailored to each phase; no private contents quoted in tracked files.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: d0/build-ready
  - notes:
    - Created six untracked prompts under `_private/phase-prompts/`.
    - Each includes the fresh-thread reading order, phase goal/gate, owner-only tasks (including P1-11/P3-03 labeling), budget rules, stop conditions, and end-of-thread deliverables.
  - done: 2026-11-14 | evidence: `_private/phase-prompts/{P1,P2,P3,P4,P5,mid-phase-resume}.md`; `git check-ignore -v _private/phase-prompts/P1.md` → `.gitignore:7:_private/`; `git ls-files _private` → empty. No tracked file quotes private contents.

### [x] D0-10 — P1 owner-dependency review and action sheet (AGENT, untracked)
- depends: D0-01, D0-06
- what: Review every P1 task for owner-only dependencies (keys, budget, V1 files, license, labeling time); write `_private/owner-action-sheet.md` ordered by what blocks soonest, with exact commands and realistic labeling-hour estimates.
- acceptance: Action sheet is untracked and complete; report states hard blockers vs can-wait and the first owner action.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: d0/build-ready
  - notes:
    - Reviewed P1-03 through P1-12 against the owner-only categories: visibility/push, contact emails/network, provider/prices/budget, Retraction Watch terms, V1 files, and P1-11/P3-03 labeling.
    - Confirmed the GitHub repo is private via unauthenticated API 404, but `origin/main` is still `f0eea8f` while local `main` is ahead; push remains the first owner action.
    - P1 actual V1-file needs are limited to `embeddings/store.py` and `graph/neo4j_{client,schema,queries}.py`; `agents/reader.py` is REDESIGN reference only.
    - Labeling estimate is an explicit assumption: ~3–6 owner hours for P1-11, ~3–6 for P3-03, with the P1-11 relabel 7-day gap.
  - done: 2026-11-14 | evidence: `_private/owner-action-sheet.md` (untracked); ordered hard blockers vs can-wait; P1 V1 path/destination table; exact push/Neo4j/provider/labeling commands; first action = push local `main` to the private remote and confirm CI.

### [x] D0-11 — Build-ready gate report and PROGRESS update (AGENT)
- depends: D0-01 … D0-10
- what: Write `docs/reports/D0-readiness.md` with a PASS/FAIL table for repo state, tests/lint/types, CI config, compose, day0-check, data-source rows, fresh-thread artifacts, and docs consistency. Update `docs/PROGRESS.md` with the Day-0 state and next action.
- acceptance: Every FAIL has an owner/agent classification; hard blockers vs can-wait are explicit; PROGRESS says fresh P1 thread resumes P1-03, then P1-03b, P1-04; Day 0 is not marked fully complete while owner-only blockers remain.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: d0/build-ready
  - notes:
    - Final checks: 89 passed/1 skipped; ruff/format/mypy clean; custom secret scan passed; pre-commit 8/8 under Python 3.12; Compose config passed; local Markdown links 0 missing.
    - Current host is not run-ready: `day0_check.py` reports missing owner env names, Docker daemon down, and Neo4j down. The report classifies those as owner/local blockers, not script defects.
    - Day 0 is explicitly **not** marked fully complete; the agent close-out is complete and P1-03 is the resumable first P1 task.
  - done: 2026-11-14 | evidence: `docs/reports/D0-readiness.md`; `docs/PROGRESS.md`; final checks above; owner blockers and first owner action (push private `main`) recorded.

## Owner tasks

**Owner status (2026-11-14):** O1 partial (B3 provider unresolved; B5 open-ended; renumber confirmation requested); O2 repo private confirmed but local `main`/branches not pushed and CI not run; O3 V1 tag/hash/scan reported done, key state still to reconcile with B3; O4 can wait until P1-09; O5 waits for P1-10; O6 local Docker/Neo4j down and env values missing; O7 later (P1-11/P3-03); O8 licence/terms approval open. Details: `_private/owner-action-sheet.md` and `docs/reports/D0-readiness.md`.

### [ ] D0-O1 — Confirm B1–B6 decisions (OWNER)
- depends: none
- what: Confirm license (MIT), repo name/visibility, LLM providers per tier, budget caps, weekly hours, and `_private/` backup location. Record anything still unresolved in `docs/DECISIONS.md` or `_private/`.
- acceptance: Every decision has an owner-confirmed value or an explicit open question; no silent defaults remain.
  - owner: — | started: — | due: —
  - notes:
  - done: — | evidence: —

### [ ] D0-O2 — Make the repo private, confirm it is V2, and push (OWNER)
- depends: D0-O1 (visibility)
- what: Set `Som007-builds/retractionscope` to private after confirming it is the V2 repo, then push local `main` and confirm CI. Future phase work uses one phase branch (`p1`, `p2`, …) per ADR-0010; historical task branches need not be pushed.
- acceptance: Repo is private; `origin` is the V2 remote; `main` and the P1-03 checkpoint are on the remote; CI is visible.
  - owner: — | started: — | due: —
  - notes:
  - done: — | evidence: —

### [ ] D0-O3 — V1 tag, scan, key rotation, fresh keys (OWNER)
- depends: none
- what: Confirm V1 `v1-final` and commit hash, run a full-history secret scan on V1, rotate/revoke any V1 keys ever exposed, and generate fresh keys only into local `.env`.
- acceptance: V1 scan result recorded; old keys revoked; fresh keys exist locally and never in chat or tracked files.
  - owner: — | started: — | due: —
  - notes:
  - done: — | evidence: —

### [ ] D0-O4 — Provide V1 files or confirm rewrite (OWNER)
- depends: none
- what: For P1-09, either provide the V1 files listed in the action sheet with their intended V2 destinations or confirm the agent should rewrite from the migration-map description. Never provide V1 `.env`, data, caches, or history.
- acceptance: Owner answer is recorded; P1-09 has a clear input path or a rewrite decision.
  - owner: — | started: — | due: —
  - notes:
  - done: — | evidence: —

### [ ] D0-O5 — Fill `pricing.yaml` before P1-10 (OWNER)
- depends: provider decision
- what: Enter verified provider/model prices in `src/axion/config/pricing.yaml` and supply the tier model IDs in local `.env`. Keep dry-run true until then.
- acceptance: Prices are complete for every configured tier; no invented numbers; dry-run can be turned off only with a budget cap.
  - owner: — | started: — | due: P1-10
  - notes:
  - done: — | evidence: —

### [ ] D0-O6 — Start Neo4j and run `make day0-check` (OWNER)
- depends: D0-04, D0-05
- what: Fill local Neo4j values, start the Day-0 compose stack, and run the offline and opt-in network checks.
- acceptance: Container healthy on loopback; `make day0-check` passes or every FAIL is understood.
  - owner: — | started: — | due: P1-09
  - notes:
  - done: — | evidence: —

### [ ] D0-O7 — Reserve labeling time for P1-11 and P3-03 (OWNER)
- depends: P1-10 and P3-02 respectively
- what: Reserve the owner's labeling blocks; the agent prepares exports/scripts but the owner labels. Plan the P1-11 7-day relabel gap in advance.
- acceptance: Calendar blocks exist; P1-11 and P3-03 are not stalled by unplanned owner time.
  - owner: — | started: — | due: P1-11 / P3-03
  - notes:
  - done: — | evidence: —

### [ ] D0-O8 — Verify and approve data-source terms (OWNER)
- depends: D0-06
- what: Review `docs/DATA_SOURCES.md`; confirm Retraction Watch licence/redistribution terms and Europe PMC per-article constraints; approve what may be cached, used, and released.
- acceptance: `docs/DATA_SOURCES.md` rows are approved; release/redistribution decisions are explicit.
  - owner: — | started: — | due: P1-06 / P5-02
  - notes:
  - done: — | evidence: —

## Phase handoff log (append newest first)
<!-- Format: YYYY-MM-DD — agent — what changed — next step -->
- 2026-11-14 — DeepSeek V4.1 Flash Free — Day-0 agent close-out complete: all D0-01…D0-11 done, build-ready report written, owner action sheet handed off, `d0/build-ready` merged into local `main` as `739d0b1` — next: owner pushes private `main`, then fresh P1 thread resumes P1-03 → P1-03b → P1-04.
- 2026-11-14 — DeepSeek V4.1 Flash Free — opened Day-0 close-out tracker; merged P1-03/DOC-01 into local `main`; started `d0/build-ready`.

## Phase exit checklist
- [x] All AGENT tasks `[x]` with evidence
- [x] Every OWNER task has an explicit status and unblocks the right phase task
- [x] Build-ready gate report committed in `docs/reports/D0-readiness.md`
- [x] `docs/PROGRESS.md` next action points to a fresh P1 thread
