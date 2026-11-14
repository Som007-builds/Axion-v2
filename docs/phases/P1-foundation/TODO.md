# TODO — P1 — Foundation, ledger, corpus, baseline

**PRD:** `docs/PRD.md` (PRD §P1) · **Gate:** see PRD · **Update this file as you work.**

## Status legend
`[ ]` todo · `[~]` in progress (needs agent/started/branch) · `[x]` done (needs evidence) · `[!]` blocked (needs reason) · `[-]` dropped (needs ADR ref)

## Rules (read `docs/AGENT_PROTOCOL.md` for full text)
- Claim a task (`[~]`) before starting; mark `[x]` with evidence when done; checkpoint notes at every step.
- Work the whole phase on the `p1` branch (ADR-0010). `branch:` fields name that phase branch; task branches created before ADR-0010 are history, not a precedent.
- Merge into `main` at task boundaries only when lint, types, and tests are green. Delete `p1` after the gate.
- If you may run out of budget: write a PARTIAL-state note (done / left / exact next command) and commit WIP.
- Take the **first** task that is `[ ]` or a stale `[~]`, respecting `depends:`.
- Update `docs/PROGRESS.md` at session end.

## Tasks

### [x] P1-01 — Repo bootstrap
- depends: Day-0 checklist
- what: pyproject.toml, src/axion skeleton, ruff, mypy, pytest, pre-commit (incl. secret scan), CI, .env.example, Makefile (lint/typecheck/test/report).
- acceptance: `make lint typecheck test` passes in CI on an empty skeleton.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-09 11:20 | branch: p1
  - notes:
    - 2026-11-09 11:20 claimed; creating packaging, package skeleton, lint/types/tests, pre-commit, CI, Makefile.
    - Soft dependency: Day-0 owner items are still open (see `docs/PROGRESS.md` Day-0 status); P1-01 is offline and does not need them.
    - 2026-11-09 11:40 implementation complete; local checks green. Host has no GNU `make`, so the exact underlying commands were run (CI runs the Makefile targets on Ubuntu).
  - done: 2026-11-09 | evidence: commits f5bd0c7 (claim), 8e89feb (implementation); `pyproject.toml`, `.gitattributes`, `.pre-commit-config.yaml`, `Makefile`, `.github/workflows/ci.yml`, `src/axion/**` (10 packages), `tests/test_smoke.py`, `scripts/check_secrets.py`, `README.md`; local run: `ruff check .` + `ruff format --check .` → all checks passed; `mypy` → success, 10 files; `pytest` → 2 passed; `scripts/check_secrets.py` → passed; `pre-commit validate-config` → exit 0. CI workflow added but not executed this session (no push/network).

### [x] P1-02 — Settings and config
- depends: P1-01
- what: Pydantic settings, config package, `pricing.yaml` template (owner fills prices), stage config schema.
- acceptance: Settings load from env; missing price fails closed in dry-run; unit tests.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-09 11:45 | branch: p1
  - notes:
    - 2026-11-09 11:45 claimed; implementing settings, pricing loader/template, stage schema, tests, and `.env.example` sync.
    - 2026-11-09 12:05 done; 22 offline tests pass. Pricing stays blank in the template by design (owner fills).
  - done: 2026-11-09 | evidence: commits bb09f8f (claim), 80865d8 (implementation); `src/axion/config/settings.py`, `pricing.py`, `stages.py`, `pricing.yaml`, `__init__.py`; `tests/test_settings.py`, `tests/test_pricing.py`, `tests/test_stages.py`; `.env.example`, `pyproject.toml`; local run: `ruff check .` + `ruff format --check .` → passed; `mypy` → success, 13 files; `pytest` → 22 passed; secret scan → passed. Missing/incomplete price raises `MissingPriceError` under `dry_run=True` and warns loudly otherwise. CI not executed this session (no push/network).

### [x] P1-03 — LLMClient + cost ledger
- depends: P1-02
- what: Port ideas from V1 llm.py: fallback chain, retry, cooldown, content-hash cache. Add tiers small/large, structured-output validation, SQLite `llm_calls` ledger, `cost_report` CLI. Fake provider for offline tests.
- acceptance: Every call logged (incl. cache hits at $0); report CLI prints cost by stage/model; tests cover retry, cooldown, cache, ledger.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-09; fresh P1 thread resumed 2026-11-14 | branch: p1
  - notes:
    - 2026-11-09 claimed; V1 reference read from `D:\AI-Projects\schimesh` at commit `b4b6a25338057bd05bc6b74bc75b26198fe546e8` (`llm.py`, router tests, cache, parser). No V1 secrets, `.env`, data, or caches read.
    - Implemented a clean-room typed client, not a V1 file copy: `Provider` protocol + registry, injected clock/sleep for deterministic tests, per-provider retry/cooldown, persistent content-hash cache, SQLite ledger, Pydantic structured output, tier model resolution, and `axion-cost-report`.
    - Real provider SDK adapters are intentionally deferred until the provider packages/deps are approved and installed; the client is provider-agnostic and offline tests use `ScriptedProvider`.
    - Implementation and checks were **uncommitted WIP** on `p1/P1-03-llmclient`, per owner instruction to hold commits/push until Day-0 passes.
    - 2026-11-14: owner requested the DOC-01 scale-approach docs-only task. Code/tests/config checkpointed locally as commit `0c79b02` before branching; no push while the repo is public / Day-0 is open.
    - **2026-11-14 DAY-0 RESUME CHECKPOINT (fresh P1 thread starts here):**
      - **Done:** `src/axion/llm/*` (client, providers, cache, ledger, cooldown, structured output, errors, models, CLI), settings additions, `.env.example`, script entry in `pyproject.toml`, and the LLM tests are committed. Local `main` contains this checkpoint via merge `6986af3`; task branch `p1/P1-03-llmclient` is at `97b7d07`. Last verified: 69 tests passed; ruff, ruff format, strict mypy, and secret scan passed.
      - **2026-11-14 ADR-0010:** P1 work continues on the single phase branch `p1`. The old `p1/P1-03-llmclient` branch (`97b7d07`) is retained as history and is not used for new commits.
      - **Left:** the fresh P1 thread must re-run the checks, inspect the checkpoint diff, and either close P1-03 with fresh evidence or record a defect. Then claim P1-03b (ledger schema extension); P1-04 remains blocked by the owner confirmation rule.
      - **Next commands:** `git switch main` → `git switch -c p1` (or `git switch p1` if it exists) → `python -m pytest -q` → `python -m ruff check .` → `python -m ruff format --check .` → `python -m mypy` → `git log --oneline -5`. Do not call a live LLM. Keep `AXION_DRY_RUN=true`.
      - **Gotchas:** real provider SDK adapters are deferred; the venv lacks `wheel`/setuptools>=68 so verify the CLI via `python -m axion.llm.cli --help`, not the console script; prices are intentionally blank and fail closed; remote push/PR may still be pending the owner's Day-0 actions (see `docs/phases/D0-prerequisites/TODO.md`).
    - **2026-11-14 fresh P1 thread:** created `p1` from `main` (`0269a65`). The literal branch name `p1` collided with the retained historical `p1/P1-01-bootstrap` ref namespace; the three local historical task branches were renamed to `archive/P1-03-llmclient` etc. (all still exist on `origin` under their original names; no history rewritten). Re-ran the full check suite on `p1`: 89 passed, 1 skipped (network opt-in); ruff check, ruff format --check, and strict mypy clean. Inspected the checkpoint: `client.py` resolves tiers, checks cache, walks the provider chain with retry/cooldown, validates structured output, and ledgers every success/cache hit/error; `ledger.py` records every attempt with stage/provider/model/tokens/usd/latency/cache_hit; `cli.py` reports by stage/model/provider. Every acceptance area has tests (`test_success_writes_ledger`, `test_cache_hit_is_logged_at_zero_cost`, `test_transient_retries_then_succeeds`, `test_rate_limit_exhaustion_cools_down_and_falls_back`, `test_cooldown_expiry_puts_provider_back`, `test_structured_output_failure_is_ledgered`, ledger CLI tests). No defect found. Tier persistence and `parent_call_id` are intentionally P1-03b scope.
  - done: 2026-11-14 | evidence: checkpoint commits `0c79b02`, `16a37fc`, `96fe8f8`, `97b7d07` (inherited via merge `6986af3`); verified on `p1` at `0269a65`: `python -m pytest -q` → **89 passed, 1 skipped**; `python -m ruff check .` → passed; `python -m ruff format --check .` → 35 files formatted; `python -m mypy` → success, 22 source files; `python -m axion.llm.cli --help` → works. Files: `src/axion/llm/{client,providers,cache,ledger,cooldown,structured,errors,models,cli}.py`, `tests/test_llm_{client,cache,ledger,structured,errors}.py`.

### [~] P1-03b — Ledger schema extension + training runs
- depends: P1-03
- what: Add model tier and `parent_call_id` (escalation link) to `llm_calls`; add `training_runs` (`run_id, model, data_hash, hardware, duration_s, estimated_usd`); ensure `teacher_label` stage and escalation provenance are reportable.
- acceptance: Idempotent schema migration; every escalated call links to its parent; training runs are recorded with local cost `0` unless a real external cost exists; ledger/cost-report tests updated.
  - branch: p1
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: p1
  - notes:
    - 2026-11-14 claimed; plan: in-place `ALTER TABLE` migration guarded by `PRAGMA table_info` (idempotent, no data loss), `tier` + `parent_call_id` on `llm_calls`, `training_runs` table with `estimated_usd` defaulting to 0 for local compute, `group_by=tier`, escalated-call counts in reports, and a `--training-runs` report view.
    - 2026-11-14 implementing: ledger migration + training-run API, `LLMRequest.parent_call_id`, `LLMResult.call_id`, tier recording on success/cache/error paths.
  - done: 2026-11-14 | evidence: `src/axion/llm/ledger.py` (idempotent `PRAGMA table_info`-guarded `ALTER TABLE llm_calls ADD COLUMN tier/parent_call_id`, `training_runs` table + `TrainingRun` upsert API, `tier` grouping, escalated-call counts); `src/axion/llm/models.py` (`LLMRequest.parent_call_id`, `LLMResult.call_id/parent_call_id`); `src/axion/llm/client.py` (tier + parent link recorded on success, cache-hit, and error paths); `src/axion/llm/cli.py` (`--group-by tier`, `escal` column, `--training-runs` table/JSON); `tests/test_llm_ledger.py` (+9 tests incl. legacy-schema migration run twice, escalation link, training-run local cost 0/upsert/validation, CLI); `tests/test_llm_client.py` (+2 tests: parent link + cache-hit call id). Commands: `python -m pytest -q` → **99 passed, 1 skipped**; `python -m ruff check .` → passed; `python -m ruff format --check .` → 35 files formatted; `python -m mypy` → success, 22 source files.

### [ ] P1-04 — Europe PMC client
- depends: P1-01
- what: Search + fetch JATS by PMCID; polite rate limiting; raw cache with deterministic file names.
- acceptance: Fetches a known PMCID offline-cached; retry/backoff tested with mocks.
  - agent: — | started: — | branch: p1
  - notes:
  - done: — | evidence: —

### [ ] P1-05 — JATS parser + citation contexts
- depends: P1-04
- what: Sections, paragraphs, reference list (DOI/PMID/PMCID), citation contexts from bibr xrefs. Golden-file tests from >=10 real samples across journals; coverage metrics.
- acceptance: Golden tests pass; coverage report shows % papers with >=1 parsed context.
  - agent: — | started: — | branch: p1
  - notes:
  - done: — | evidence: —

### [ ] P1-06 — Retraction data loader + linker
- depends: P1-04
- what: Load Retraction Watch data via Crossref; link by DOI/PMID/PMCID; coverage stats (retracted, full text available, citers present). Record license/terms in docs/DATA_SOURCES.md.
- acceptance: Linker unit-tested; coverage table generated by script.
  - agent: — | started: — | branch: p1
  - notes:
  - done: — | evidence: —

### [ ] P1-07 — Feasibility spike + sub-topic ADR
- depends: P1-05, P1-06
- what: For 3-5 candidate sub-topics count retracted OA papers with full text, in-corpus citers, and contexts. Choose per CONTEXT.md section 4; write ADR. Apply pivot rule if minimums fail.
- acceptance: Report in docs/reports/P1-feasibility.md; ADR Proposed for owner approval.
  - agent: — | started: — | branch: p1
  - notes:
  - done: — | evidence: —

### [ ] P1-08 — Ingest corpus
- depends: P1-07 (owner-approved)
- what: 2k-5k papers in the chosen sub-topic plus all discoverable citers of its retracted papers. Zero LLM cost.
- acceptance: Corpus manifest committed (IDs only, no full text); counts match report.
  - agent: — | started: — | branch: p1
  - notes:
  - done: — | evidence: —

### [ ] P1-09 — Stores: Neo4j schema v2 + Chroma
- depends: P1-08
- what: Constraints/indexes per CONTEXT.md section 7.3; idempotent loaders; Chroma collections for claims and contexts; tests with mocks/ephemeral stores.
- acceptance: Schema script idempotent; load of corpus manifest succeeds twice with identical counts.
  - agent: — | started: — | branch: p1
  - notes:
  - done: — | evidence: —

### [ ] P1-10 — Baseline claim extractor
- depends: P1-03, P1-09
- what: Structured extraction with provenance: one large model, all target sections, via LLMClient. Evidence span must be verbatim in source. Parse failures recorded. Run `--dry-run` first; respect budget caps. Persist outputs as candidate **silver** labels with provenance (teacher model/version, prompt version, run_id); they are not gold.
- acceptance: Run completes within budget; ledger totals match report; failures logged not dropped; silver-label manifest with provenance is committed/reproducible and is never used to evaluate students.
  - agent: — | started: — | branch: p1
  - notes:
  - done: — | evidence: —

### [ ] P1-11 — Claim audit (human)
- depends: P1-10
- what: Draw seeded sample >=200 claims; label per AUDIT_RUBRIC; relabel 10% after >=7 days; commit labels with provenance; freeze dev/test split.
- acceptance: eval/audit/claims_audit_v1.csv committed; precision + Wilson CI + agreement computed by script. (Owner labels; agent prepares export and scripts.)
  - agent: — | started: — | branch: p1
  - notes:
  - done: — | evidence: —

### [ ] P1-12 — Baseline report + gate review
- depends: P1-11
- what: Generate docs/reports/P1-baseline.md (precision, cost/paper, tokens, p95 latency, parse and linkage coverage). Propose ratification of provisional targets via ADR.
- acceptance: Report regenerable with `make report`; PROGRESS headline table filled; gate decision recorded.
  - agent: — | started: — | branch: p1
  - notes:
  - done: — | evidence: —

## Phase handoff log (append newest first)
<!-- Format: YYYY-MM-DD — agent — what changed — next step -->
- 2026-11-14 — DeepSeek V4.1 Flash Free — workflow switched to one phase branch `p1` (ADR-0010); historical task branches retained — next: fresh P1 thread creates `p1` from `main` and resumes P1-03
- 2026-11-14 — DeepSeek V4.1 Flash Free — Day-0 close-out merged P1-03/DOC-01 into local `main` (`6986af3`); P1-03 left `[~]` with a fresh-thread resume checkpoint — next: fresh P1 thread re-runs checks, closes P1-03, then P1-03b; do not start P1-04 without owner confirmation
- 2026-11-09 — DeepSeek V4.1 Flash Free — P1-03 code + tests complete as uncommitted WIP on `p1/P1-03-llmclient` — next: owner Day-0 pass, then commit/push P1-03; do not start P1-04 without owner confirmation
- 2026-11-09 — DeepSeek V4.1 Flash Free — P1-01 and P1-02 complete and merged — next: P1-03

## Phase exit checklist
- [ ] All tasks `[x]` or `[-]` with ADR
- [ ] Gate criteria evaluated honestly (see PRD)
- [ ] `docs/PROGRESS.md` phase table and headline numbers updated
- [ ] Report committed in `docs/reports/`
