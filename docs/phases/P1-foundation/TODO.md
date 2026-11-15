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

### [x] P1-03b — Ledger schema extension + training runs
- depends: P1-03
- what: Add model tier and `parent_call_id` (escalation link) to `llm_calls`; add `training_runs` (`run_id, model, data_hash, hardware, duration_s, estimated_usd`); ensure `teacher_label` stage and escalation provenance are reportable.
- acceptance: Idempotent schema migration; every escalated call links to its parent; training runs are recorded with local cost `0` unless a real external cost exists; ledger/cost-report tests updated.
  - branch: p1
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: p1
  - notes:
    - 2026-11-14 claimed; plan: in-place `ALTER TABLE` migration guarded by `PRAGMA table_info` (idempotent, no data loss), `tier` + `parent_call_id` on `llm_calls`, `training_runs` table with `estimated_usd` defaulting to 0 for local compute, `group_by=tier`, escalated-call counts in reports, and a `--training-runs` report view.
    - 2026-11-14 implementing: ledger migration + training-run API, `LLMRequest.parent_call_id`, `LLMResult.call_id`, tier recording on success/cache/error paths.
  - done: 2026-11-14 | evidence: `src/axion/llm/ledger.py` (idempotent `PRAGMA table_info`-guarded `ALTER TABLE llm_calls ADD COLUMN tier/parent_call_id`, `training_runs` table + `TrainingRun` upsert API, `tier` grouping, escalated-call counts); `src/axion/llm/models.py` (`LLMRequest.parent_call_id`, `LLMResult.call_id/parent_call_id`); `src/axion/llm/client.py` (tier + parent link recorded on success, cache-hit, and error paths); `src/axion/llm/cli.py` (`--group-by tier`, `escal` column, `--training-runs` table/JSON); `tests/test_llm_ledger.py` (+9 tests incl. legacy-schema migration run twice, escalation link, training-run local cost 0/upsert/validation, CLI); `tests/test_llm_client.py` (+2 tests: parent link + cache-hit call id). Commands: `python -m pytest -q` → **99 passed, 1 skipped**; `python -m ruff check .` → passed; `python -m ruff format --check .` → 35 files formatted; `python -m mypy` → success, 22 source files.

### [x] P1-04 — Europe PMC client
- depends: P1-01
- what: Search + fetch JATS by PMCID; polite rate limiting; raw cache with deterministic file names.
- acceptance: Fetches a known PMCID offline-cached; retry/backoff tested with mocks.
  - branch: p1
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: p1
  - notes:
    - 2026-11-14 claimed; owner approved live network use with polite rate limiting and the contact email from env. Tests stay offline/mocked; live calls only via an opt-in script or explicitly allowed test.
    - 2026-11-14 implemented; live acceptance fetch of `PMC3257301` succeeded and the second read came from cache with a transport that raises on any request.
  - done: 2026-11-14 | evidence: `src/axion/ingest/europepmc.py` (metadata search + JATS `fullTextXML`; identifying User-Agent with `mailto:`; minimum-interval throttle; exponential backoff on 429/5xx/OSError; 404 not retried; deterministic raw cache `fulltext/<PMCID>.xml` and `search/<sha256>.json` with atomic writes; PMCID validation against traversal); settings `EUROPEPMC_*` in `src/axion/config/settings.py` + `.env.example`; `tests/test_europepmc.py` (16 offline tests: parse/cache, cache-without-email, retry/backoff, 404, 403, spacing, user agent, invalid PMCID, non-JATS, settings; 1 opt-in network test). Commands: `python -m pytest -q` → **115 passed, 2 skipped**; `AXION_RUN_NETWORK=1 python -m pytest tests/test_europepmc.py -k known_pmcid` → **1 passed** (live fetch + cache reuse); ruff check/format and strict mypy clean.

### [x] P1-05 — JATS parser + citation contexts
- depends: P1-04
- what: Sections, paragraphs, reference list (DOI/PMID/PMCID), citation contexts from bibr xrefs. Golden-file tests from >=10 real samples across journals; coverage metrics.
- acceptance: Golden tests pass; coverage report shows % papers with >=1 parsed context.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | branch: p1
  - notes:
    - 2026-11-14 claimed; parser, 12-paper CC BY golden corpus, regeneration and coverage scripts, and tests implemented on `p1`.
    - References use element/mixed citations with a DOI → PMID → title → year fallback; contexts expand short sentences to neighbours and record the section path.
    - Fixtures are 12 real CC BY articles across 12 journals, gzipped deterministically with attribution, licence, source URL, and SHA-256 in `tests/fixtures/jats/manifest.json`; the redistribution exception is documented in `docs/DATA_SOURCES.md`.
    - DOI coverage is deliberately reported as measured (102/775 references); legacy single-string citations are not guessed.
  - done: 2026-11-14 | evidence: `src/axion/parse/jats.py`; `scripts/build_jats_golden.py`; `scripts/jats_coverage.py`; `tests/test_jats.py` (32 tests incl. 12 golden fixtures and unit cases for nested sections, mixed citations, short-sentence expansion, coverage maths); `tests/fixtures/jats/` (12 `.xml.gz` + `manifest.json` + `expected.json`); `docs/reports/P1-jats-coverage.md`; `docs/DATA_SOURCES.md` exception. Commands: `python -m pytest -q` → **147 passed, 2 skipped**; `python -m ruff check .` → passed; `python -m ruff format --check .` → 41 files formatted; `python -m mypy` → success, 24 source files; `python scripts/jats_coverage.py` → 12/12 papers with contexts, 1,133 contexts (100% resolved), 775 references (DOI 102, PMID 101, title 103, year 764), 362 sections, 768 paragraphs, 0 parser warnings.

### [x] P1-06 — Retraction data loader + linker
- depends: P1-04
- what: Load Retraction Watch data via Crossref; link by DOI/PMID/PMCID; coverage stats (retracted, full text available, citers present). Record license/terms in docs/DATA_SOURCES.md.
- acceptance: Linker unit-tested; coverage table generated by script.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | done: 2026-11-14 | branch: p1
  - notes:
    - 2026-11-14 owner approved use with conditions: verify Crossref's CC0 statement on the canonical crossref.org page, record URL + date, note the unofficial non-commercial claim, use the REST API for lookups and the GitLab CSV snapshot for bulk, never commit the raw CSV (ID-only manifests), and cite Crossref + Retraction Watch.
    - Verified CC0 on the canonical Metadata Retrieval page (not the retraction page): <https://www.crossref.org/documentation/retrieve-metadata/> — “Open Funder Registry, Retraction Watch database — CC0”. Recorded URL, date, the third-party non-commercial claim (unofficial), acquisition rules, and snapshot log in `docs/DATA_SOURCES.md`.
    - Snapshot: GitLab commit `560ad745cb621e240501422ad485bd81b4590860` (“Retraction Watch data for 2026-11-13”), CSV SHA-256 `4d0509f6…f917dd`, 68,092,153 bytes. Raw CSV kept under untracked `data/retraction-watch/`; committed manifest is ID-only.
    - Europe PMC does not accept `PMC/<id>/citations` (404); citations require a PMID (`MED/<id>/citations`). Added `find_by_doi`, `find_by_pmid`, `citations`, and `cited_by_count` to the client.
  - done: 2026-11-14 | evidence: `src/axion/ingest/retractions.py` (CSV loader, DOI/PMID index, PMCID resolver hook, ID-only manifest); `src/axion/ingest/europepmc.py` (batch-linkable lookups + citations); `scripts/retraction_coverage.py`; `tests/test_retractions.py`, `tests/test_retraction_coverage.py`, additions to `tests/test_europepmc.py`; `docs/reports/P1-retraction-coverage.md`; `docs/reports/P1-retraction-manifest.json`. Coverage: 73,822 rows, 68,369 retractions, 67,870 DOI (91.9%), 34,627 PMID (46.9%), 68,628 either (93.0%). Seeded sample 150 → 80 resolved (53.3%, Wilson 45.4-61.1%), 49 OA (61.3%), 54 full text/PMCID (67.5%); 77/80 with citers (96.2%), median 7, max 99.

### [x] P1-07 — Feasibility spike + sub-topic ADR
- depends: P1-05, P1-06
- what: For 3-5 candidate sub-topics count retracted OA papers with full text, in-corpus citers, and contexts. Choose per CONTEXT.md section 4; write ADR. Apply pivot rule if minimums fail.
- acceptance: Report in docs/reports/P1-feasibility.md; ADR Proposed for owner approval.
  - agent: DeepSeek V4.1 Flash Free | started: 2026-11-14 | done: 2026-11-14 | branch: p1
  - notes:
    - Owner delegated the shortlist and asked for 3-5 candidates, one unexpected if supported, and a check for a Europe PMC citations endpoint. Shortlist fixed in the script before measuring: oncology, cardiovascular, infectious disease, gastroenterology, rehabilitation/therapy (the non-obvious one).
    - All five pass the minimums at the lower bound. Infectious disease is proposed because its estimated corpus (4,749) is the only one inside the PRD’s 2,000-5,000 target; oncology has the largest context margin but ~17k papers.
    - `PMC/<id>/citations` returns 404; `MED/<pmid>/citations` works and was used for every citer list.
  - done: 2026-11-14 | evidence: `scripts/feasibility_spike.py`; `tests/test_feasibility.py` (9 tests); `docs/reports/P1-feasibility.md`; `docs/reports/P1-feasibility.json`; ADR-0012 Proposed in `docs/DECISIONS.md`. Measured: all candidates ≥653 est. source papers and ≥2,543 est. contexts at lower bound; infectious disease 741 (653-829) sources, 4,409 (3,498-5,332) contexts, 4,749 est. corpus; rehab (unexpected) 825 (733-918) sources, 6,958 (5,451-8,655) contexts, 6,624 corpus. Estimates are sampling-based; P1-08 will report exact counts.

### [x] P1-08 — Ingest corpus
- depends: P1-07 (owner-approved)
- what: Ingest the owner-approved infectious-disease corpus (retracted OA sources + discoverable citers) up to the ~5,000 hard cap; exact counts. Zero LLM cost.
- acceptance: Corpus manifest committed (IDs only, no full text); counts match report.
  - agent: Freebuff / DeepSeek V4.x Flash | started: 2026-11-14 22:56 | branch: p1
  - done: 2026-11-15 | evidence: commit `62433c8`; `docs/reports/P1-corpus-{papers.csv,cites.csv,manifest.json,md}`; `docs/reports/P1-corpus-coverage.{md,json}`; `scripts/corpus_coverage.py`. Exact result: **4,928 papers** (792 sources, 4,168 citers), **6,117 contexts**, 4,928/4,928 parsed (0 failures), 3,976 edges with contexts, 1 paper without PMID, 39 full-text failures. Both §4 minimums PASS (792 ≥ 30; 6,117 ≥ 300). Wall 3,065.9s for the resumed run; peak RSS 178.2 MiB; cache 4,928 files / 644.4 MiB.
  - link coverage: 285/792 source papers have an incoming citer edge; 507 have none. 34/4,168 citer papers have no outgoing edge; 533 papers have no edge in either direction. The 5,000-paper cap is not coverage-neutral; see `docs/reports/P1-corpus-coverage.md`.
  - notes:
    - 2026-11-14 22:56 resumed the interrupted session's unverified WIP (`d4f3171`); baseline checks green (226 passed, 2 skipped; ruff/format/mypy clean). Existing work-dir checkpoint (`data/corpus/infectious-disease-v1/`) inspected: 1,539 DOI + 31 PMID resolution rows, 797 citation lists, 13,426 citer rows, 724 cached full texts. It is resumed, not deleted. Partial-log yield: 798 unique eligible sources, 9,936 eligible citers, 4,202 selected before interruption; 5 full-text HTTP 500s (verified persistent).
    - Plan: refactor orchestration out of the 1,015-line script into `src/axion/ingest/` with tests; smoke-run 30 sources and re-run to prove resume; then full run in background.
    - 2026-11-14 owner approved ADR-0012: infectious disease; exact counts must clear ≥30 sources and ≥300 contexts or stop and propose oncology via a new Proposed ADR. Oncology is deferred as a later held-out transfer corpus; the manifest is config-driven (ADR-0012).
    - Corpus bound is the total including citers, hard cap ~5,000 (ADR-0013). Citer discovery is MEDLINE/PMID-only; the PMID gap and blast-radius recall cap must be reported.
    - **PARTIAL STATE 2026-11-14 23:51 (session ended by owner):** code refactor, tests, and live smoke are done; the full ingest is **not finished**. Full-text cache has 3,276/4,967 papers; detached run was at 3,200/4,967 when the session ended. No committed manifest yet. Known stage counts from this run: 798 eligible sources, 9,936 eligible MEDLINE citers, 4,202 included, 5,734 truncated by the 5,000 total cap; ~11 permanent HTTP 500s so far.
    - Exact next command: `.venv/Scripts/python.exe scripts/ingest_corpus.py >> data/corpus/infectious-disease-v1/full-run.log 2>&1` (resumes from cache/checkpoints), then inspect `docs/reports/P1-corpus.md` and `.json`.
    - Gotcha: the detached process may still be running; check for `scripts/ingest_corpus.py` before starting another. One ingest at a time.

### [x] P1-09 — Stores: Neo4j schema v2 + Chroma
- depends: P1-08
- what: Constraints/indexes per CONTEXT.md section 7.3; idempotent loaders; Chroma collections for claims and contexts; tests with mocks/ephemeral stores.
- acceptance: Schema script idempotent; load of corpus manifest succeeds twice with identical counts.
  - agent: Freebuff / DeepSeek V4.x Flash | started: 2026-11-14 22:56 | branch: p1
  - done: 2026-11-15 | evidence: `python scripts/load_stores.py --manifest docs/reports/P1-corpus-manifest.json --chroma-dir data/chroma-full --twice --embedder sentence-transformers` → exit 0, **491s**, load 1 == load 2: Paper 4,928; CITES 4,982; CitationContext/IN_PAPER/POINTS_TO 6,117; RetractionNotice/RETRACTED_BY 792; vectors papers 4,928, citation_contexts 6,117. Schema v2 idempotent; orphan/non-source edges rejected. MiniLM (384-d) semantic embeddings installed and used; Chroma dir 53 MB; Neo4j volume 545 MB.
  - notes:
    - 2026-11-14 22:56 claimed for verification: the interrupted session left `src/axion/store/*` and `scripts/load_stores.py` unverified. Clean V2 rewrite, no V1 port (ADR-0011).
    - Verification target: Neo4j schema v2 is idempotent; loading the smoke and full manifests twice yields identical graph/vector counts; in-memory path is the fallback if Docker is unavailable.
    - **VERIFIED 2026-11-14:** orphan/non-source cite rows are now rejected (`CorpusLoadError`); in-memory and real Neo4j 5.18 + persistent Chroma both loaded the 30-source smoke bundle twice with identical counts (14 papers, 10 CITES, 8 CitationContext, 4 RetractionNotice, 14/10/8 vector rows). Chroma telemetry disabled.
- **DONE 2026-11-15:** full manifest loaded twice; acceptance evidence is that second-load counts are identical. Load 1 == load 2: Paper 4,928; CITES 4,982; CitationContext/IN_PAPER/POINTS_TO 6,117; RetractionNotice/RETRACTED_BY 792; vectors 4,928 papers + 6,117 contexts. Re-queried live on 2026-11-15 and counts still match.

### [~] P1-10 — Baseline claim extractor
- depends: P1-03, P1-09
- what: Structured extraction with provenance: one large model, all target sections, via LLMClient. Evidence span must be verbatim in source. Parse failures recorded. Run `--dry-run` first; respect budget caps. Persist outputs as candidate **silver** labels with provenance (teacher model/version, prompt version, run_id); they are not gold.
- acceptance: Run completes within budget; ledger totals match report; failures logged not dropped; silver-label manifest with provenance is committed/reproducible and is never used to evaluate students.
  - agent: Freebuff / DeepSeek V4.x Flash | started: 2026-11-14 23:56 | branch: p1
  - notes:
    - 2026-11-14 owner scope decision (ADR-0014): seeded paper sample, not the full corpus; size from a dry-run estimate for ≥200 claims with margin and record the seed.
    - **2026-11-14 owner approval (this session):** build the offline portion now — versioned prompt, Pydantic claim schema, verbatim evidence-span validation, LLMClient runner with a fake provider + `--dry-run`, seeded 100-paper selector, silver-label manifest writer, provider adapter interface only. **No provider SDK dependency, no real calls.** Baseline sections: every body section except references, acknowledgements, funding/COI, supplementary. If 100 papers cannot plausibly yield ≥200 claims, recommend a larger sample.
    - Blocked for the *paid* run: verified prices in `pricing.yaml`, a paid budget cap, and provider SDK approval. Tier IDs remain `openai/gpt-oss-20b` / `openai/gpt-oss-120b`.
  - 2026-11-15 offline portion done: `claim-extraction-v1.md`, `claims.py`, `prompting.py`, `baseline.py`, `scripts/run_baseline_extraction.py`, fake-provider tests. Dry run on the real 100-paper sample (seed 20261114): 764,084 prompt tokens (mean 7,641/paper), 0 missing/failed; expected claims 200/500/1,000 at 2/5/10 per paper. Full report: `docs/reports/P1-baseline-estimate.md`.
  - **2026-11-15 paid-run checkpoint:** prices filled from the official Groq model pages (checked 2026-11-15), $3 cap recorded in untracked `_private/budget.md`, `groq==1.7.0` pinned and wired through `src/axion/llm/groq.py`, ledger reasoning-token column added. Pilot (5-paper request, seed 20261114, `openai/gpt-oss-120b`) stopped after **1 paper**: 21 silver claims / 28 extracted, 7 span-not-verbatim, 0 parse failures; prompt 6,809, completion 7,159 (3,011 reasoning), list price **$0.005317**, latency 16,459 ms, prompt gap **-10.3%** vs chars/4 for that paper. Next request was **12,111 tokens vs TPM 8,000** (HTTP 413 `rate_limit_exceeded`); the client retried/cooldown then stopped at a clean checkpoint. Free tier is **8,000 TPM / 200,000 TPD**, so the 5-paper pilot and 100-paper sample cannot complete without an owner decision. Report: `docs/reports/P1-baseline-pilot.{md,json}`; run artifacts under `eval/silver/claims_v1/pilot/` (untracked).
  - done (paid run): — | blocked: Groq free-tier TPM/TPD. Owner must choose: raise the limit/Dev tier, approve another provider, or explicitly approve a sampling rule that fits the limit. No workaround attempted.

### [!] P1-11 — Claim audit (human)
- depends: P1-10
- what: Draw seeded sample >=200 claims; label per AUDIT_RUBRIC; relabel 10% after >=7 days; commit labels with provenance; freeze dev/test split.
- acceptance: eval/audit/claims_audit_v1.csv committed; precision + Wilson CI + agreement computed by script. (Owner labels; agent prepares export and scripts.)
  - agent: DeepSeek V4.1 Flash Free (tooling only) | started: 2026-11-14 | branch: p1
  - notes:
    - Tooling is ready and tested; **no labels were created or invented**.
    - `src/axion/eval/audit.py` + `scripts/audit_sample.py`: seeded uniform sample (default seed 20261114), ≥200 minimum, corpus snapshot hash, paper-level dev/test split, rubric-aligned CSV export with blank label fields.
    - `scripts/audit_metrics.py`: precision, Wilson 95% CI, failure breakdown, per-section precision, and post-relabel raw agreement + Cohen's κ; rejects unknown labels and counts unlabelled rows.
    - `eval/audit/claims_audit_v1.template.csv` (header only) and `eval/audit/README.md` (procedure and provenance rules).
    - Blocked on the human steps only: the owner needs a claims JSONL from P1-10, ~3–6 hours to label ≥200 claims, and a ≥7-day gap to relabel 10%.
    - **2026-11-15 tooling update:** `eval/audit/claim_audit_tool.html` is a single-file blind labeler (no network/dependencies; keys `1`-`5`, `N`, `Z`, arrows; autosave; exact-column CSV download; span-missing warning); `scripts/audit_validate.py` enforces allowed labels/notes/no-unlabelled and calls the existing precision/Wilson/breakdown/κ metrics; `scripts/audit_sample.py --overlap-out` emits a seeded 20% second-labeler subset. The inline JS was syntax-checked with `node --check`, but **no interactive browser test was completed**; `eval/audit/tool_smoke_test.csv` is the owner smoke fixture. **No claims were labelled.**
    - The pilot export `eval/audit/claims_audit_v1_pilot.csv` has only **21 claims**, below the 200 minimum; it is a tooling fixture, not the official audit. ADR-0016 Proposed records the agreement choice (≥7-day self-relabel or independent 20% second labeler).
  - done: — | blocked: 2026-11-14 | unblocks: a P1-10 run that can export ≥200 claims + owner labeling time and ≥7-day relabel gap or approved second labeler.

### [~] P1-12 — Baseline report + gate review
- depends: P1-11
- what: Generate docs/reports/P1-baseline.md (precision, cost/paper, tokens, p95 latency, parse and linkage coverage). Propose ratification of provisional targets via ADR.
- acceptance: Report regenerable with `make report`; PROGRESS headline table filled; gate decision recorded.
  - agent: Freebuff / DeepSeek V4.x Flash | started: 2026-11-14 23:56 | branch: p1
  - notes:
    - 2026-11-14 owner approved offline report scaffolding. Build a regenerable report script with explicit "not yet measured" placeholders from ledger/audit/manifest inputs; no invented numbers. The gate review still waits for P1-11 labels and the paid P1-10 run.
  - 2026-11-15 scaffold done: `scripts/build_p1_report.py`, `make report`, `docs/reports/P1-baseline.md` with manifest/coverage values and NOT YET MEASURED placeholders for precision/cost/tokens/latency. Gate review remains blocked on P1-11.
  - 2026-11-15: the paid pilot report is measured for **one paper** (`docs/reports/P1-baseline-pilot.{md,json}`) but is not a baseline report; precision and the full-run tokens/cost remain blocked.
  - done: — | in progress: scaffold + one-paper pilot evidence only.

## Phase handoff log (append newest first)
<!-- Format: YYYY-MM-DD — agent — what changed — next step -->
- 2026-11-15 — DeepSeek V4.1 Flash Free — filled Groq prices, set $3 cap, pinned `groq==1.7.0`, added adapter + reasoning ledger; paid pilot stopped at 1 paper on TPM 8000 (request 12,111); built audit HTML/validator/overlap export, no labels — next: owner decides limit/provider/sampling, then finish pilot + seeded sample + ≥200-claim export
- 2026-11-14 — DeepSeek V4.1 Flash Free — P1-06 closed (RW loader/linker, citations client, coverage report) and P1-07 closed (5-candidate feasibility spike, report, ADR-0012 Proposed); P1-09 rewrite decided (ADR-0011) — next: owner approves ADR-0012 or names an alternative, then resume P1-08
- 2026-11-14 — DeepSeek V4.1 Flash Free — P1-03b/P1-04/P1-05 closed; P1-11 export+metrics tooling prepared; P1-06..P1-12 marked `[!]` with unblocks — next: owner clears Retraction Watch terms/sub-topics, then resume P1-06/P1-07
- 2026-11-14 — DeepSeek V4.1 Flash Free — workflow switched to one phase branch `p1` (ADR-0010); historical task branches retained — next: fresh P1 thread creates `p1` from `main` and resumes P1-03
- 2026-11-14 — DeepSeek V4.1 Flash Free — Day-0 close-out merged P1-03/DOC-01 into local `main` (`6986af3`); P1-03 left `[~]` with a fresh-thread resume checkpoint — next: fresh P1 thread re-runs checks, closes P1-03, then P1-03b; do not start P1-04 without owner confirmation
- 2026-11-09 — DeepSeek V4.1 Flash Free — P1-03 code + tests complete as uncommitted WIP on `p1/P1-03-llmclient` — next: owner Day-0 pass, then commit/push P1-03; do not start P1-04 without owner confirmation
- 2026-11-09 — DeepSeek V4.1 Flash Free — P1-01 and P1-02 complete and merged — next: P1-03

## Phase exit checklist
- [ ] All tasks `[x]` or `[-]` with ADR
- [ ] Gate criteria evaluated honestly (see PRD)
- [ ] `docs/PROGRESS.md` phase table and headline numbers updated
- [ ] Report committed in `docs/reports/`
