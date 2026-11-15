# PROGRESS — live project state

> Agents: update this file at the end of every session (and mid-session if long). Newest log entries first.

## Current state
- **Phase:** P1 (foundation) — P1-01 through **P1-10** are `[x]`. The baseline is measured on `gemini-3.5-flash-lite` (**100 papers, 765 silver claims**, $0 real spend) and the official audit export exists (**200 claims from 45 papers**). **P1 gate PASSED (2026-11-15): audited precision 96.5%** ≥ the 90% floor. P1-11 needs only the blind relabel (due ≥7 days later); P1-12 is done (regenerable report).
- **P1-11 audit (2026-11-15, owner-labelled):** 200 claims / 45 papers, **193 CORRECT, 7 NOT_A_CLAIM** (0 distorted, unsupported, duplicate) → **precision 96.5%**, Wilson 95% **93.0–98.3%**, paper-level cluster bootstrap **94.0–98.6%** (45 clusters, 2,000 resamples, seed 20261114). Single labeler; self-agreement pending the blind relabel. Report: `docs/reports/P1-audit.md`.
- **Owner decisions recorded:** ADR-0011 (clean V2 store rewrite), ADR-0012 (infectious disease, exact-count conditions, PMID limitation, config-driven manifest, oncology deferred), ADR-0013 (total corpus including citers, ~5,000 hard cap), ADR-0014 (P1-10 seeded sample), ADR-0015 Proposed (P1 blast-radius counts conditional on included citers; expansion deferred to P3), ADR-0016 Proposed (agreement by ≥7-day self-relabel or independent 20% second-labeler overlap), **ADR-0017 Accepted (Gemini free tier replaces Groq; $0 real spend)**, **ADR-0018 Accepted (audit export: ≥40 papers, ≤5 claims/paper, paper-level split, cluster bootstrap CI)**, **ADR-0019 Accepted (P1 baseline model = `gemini-3.5-flash-lite`; `gemini-3.8-flash` is the large/reference model only; P2 small tier + bulk labeler Proposed, not decided)**.
- **P1-10 Gemini implementation (2026-11-15):** `google-genai==2.8.0` pinned; `src/axion/llm/gemini.py` uses cleaned JSON-schema structured output, validates with Pydantic, maps `candidates + thoughts` to completion and `thoughts` to reasoning; `pricing.yaml` v2 has dated list prices (3.8 Flash $0.75/$3.75 through 2026-12-31, $1.50/$7.50 from 2027-01-01; 3.5 Flash-Lite $0.30/$2.50); the ledger records billing, price version, input/output/post-promotion USD, and generation config. Free-tier calls record list price with `billing=free_tier`; real spend is $0. `src/axion/llm/pacing.py` enforces 5 RPM / 20 RPD with a 2-request margin, Pacific-day reset, and a clean `DailyQuotaError` stop.
- **P1-10 baseline measured (2026-11-15, `p1-10-flashlite-s20261114-n100`):** 100/100 seeded papers, **765 accepted silver claims**, 0 parse failures, 108 recorded failures (97 span-not-verbatim, 11 unknown section). Verbatim **88.7%**, strict identical (0 normalization fixes). Tokens **697,734 prompt / 142,057 completion / 0 thinking** (839,791 total); list price **$0.564459** = **$0.005645/paper** and **$0.000738/accepted claim**; output **62.9%** of cost; latency mean 6,448 ms, p95 15,490 ms; prompt-gap **-8.7%**; **120 of 450** daily requests. Config: thinking `default` (no `thinking_config`), temperature 0.0, max output 16,384, prompt v1. Report: `eval/silver/claims_v1/baseline_flashlite/run_report.md`.
- **Provider-failure policy:** TLS/socket read errors are transient (one retry through the pacer); an isolated provider failure is recorded and the batch continues; the run stops after **three consecutive** provider failures or immediately on a 429/daily-quota error (ADR-0019).
- **Normalization-only evidence fix:** documented in `docs/eval/EVIDENCE_SPANS.md`; accepted spans are rewritten to the exact source substring. Groq pilot rejects: 4 U+2011 hyphen variants (fixed), 2 non-contiguous merged tails (rejected), 1 case-only (rejected). Strict reject rate 25.0%; normalized 10.7%. Prompt v2 is not justified (paraphrase was 1/7).
- **Gemini pilot root cause (2026-11-15, ledger-derived):** run `p1-10-gemini-pilot-s20261114-n5` recorded **10 attempts, 0 successes**: 1× HTTP 400 `INVALID_ARGUMENT` (`additional_properties` in the schema, fixed), 1× HTTP 504 `DEADLINE_EXCEEDED`, 8× HTTP 503 `UNAVAILABLE`. No attempt reached an empty-output/token-exhaustion state; that hypothesis came only from the separate `max_output_tokens=16` probe. The 10 attempts used 10 of the 20 daily requests. Report: `docs/reports/P1-gemini-pilot-diagnosis.md` (`scripts/failure_report.py`).
- **Failure/retry hardening (ADR-0017 amendment):** sanitized root cause (class, message, HTTP/provider status, finish reason, tokens, attempts) now lands in the ledger, `failures.jsonl`, and the run report; `max_output_tokens` is **16384** with thinking **medium** recorded per call; empty `MAX_TOKENS` output is `OutputTokenExhaustedError` and non-retryable; only network/5xx/504 retries, at most once, and retries are paced like first attempts; 429/`RESOURCE_EXHAUSTED`/daily quota stop the run at a checkpoint.
- **Gemini validation (2026-11-15, 2 requests):** the fixed request was accepted (no schema error) but `gemini-3.8-flash` returned **HTTP 504 `DEADLINE_EXCEEDED` twice**, each after ~119 s, with `thinking=medium` and `max_output_tokens=16384` on a 7,589-token prompt. **No claims/tokens/cost measured.** The adapter timeout is now 300 s; that change is unverified. Daily quota used: **12 of 20** (cap 18).
- **Link coverage caveat:** 285 of 792 source papers have at least one incoming citer edge; 507 do not, and 34 citer papers have no outgoing edge. The 5,000-paper cap is not coverage-neutral. Blast-radius counts are **conditional on the included citer set only**; P3 owns on-demand expansion (ADR-0015 Proposed). Exact counts are in `docs/reports/P1-corpus-coverage.md`.
- **Next action:** P1-11 needs **owner labeling** — open `eval/audit/claim_audit_tool.html`, load `eval/audit/claims_audit_v1.csv`, label the 200 claims, export the CSV back to the same path, then run the validator/metrics. No further model work is required for the baseline; the optional `gemini-3.8-flash` 5-paper reference comparison never becomes silver.
- **Last updated:** 2026-11-15 by Freebuff / DeepSeek V4.x Flash (P1-11 audit + gate session)
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
- ✅ Push: `p1` is pushed at `a8d6d85` (same as `origin/p1`); local `main` is 11 commits ahead of `origin/main` and was not merged or pushed. CI status is not available locally (`gh` is not installed).
- ✅ Contact emails, Groq key, Neo4j password, and V2 Neo4j are configured locally; no secret values are tracked.
- ⛔ P1-10: prices, the $3 cap, and the Groq SDK are now in place. The paid run is blocked by the Groq free-tier limit (TPM 8000 / TPD 200,000): the sample contains prompts above 8,000 tokens and the daily budget cannot cover 100 papers. Owner decision required before any workaround.
- ✅ P1-06: Retraction Watch CC0 verified on Crossref’s Metadata Retrieval page and owner-approved; loader/linker and coverage report committed.
- ✅ P1-08/P1-09: closed with exact counts and a full store load; the remaining coverage caveat is recorded above and in `docs/reports/P1-corpus-coverage.md`.
- ⛔ P1-11/P3-03: owner labeling time (P1-11 also needs a 7-day relabel gap).
- ⚪ Can wait: B5 weekly hours; B6 `_private/` backup risk; P5 licence/release/outreach.

**Recorded facts**
- V1 snapshot: offline suite **252 passed, 12 deselected**; `v1-final` at `b4b6a25338057bd05bc6b74bc75b26198fe546e8`; custom V1 history scan 0 candidate hits; owner reported V1 keys rotated.
- Day-0 decisions: MIT for now; private until P5; $0 paid budget; `_private/` no backup accepted; weekly hours open-ended. ADR-0008 is the scale approach; the Day-0 ADR is ADR-0009. Owner confirmation of the renumbering is requested.
- `origin/p1` is at `a8d6d85`; local `main` (`332fbf9`) is 11 commits ahead of `origin/main` and has not been merged with `p1`.

## Phase status
| Phase | Status | Gate result | Notes |
| :-- | :-- | :-- | :-- |
| Day 0 | Agent close-out complete; owner items pending | — | CI confirmation, paid pricing/budget, Retraction Watch terms, labeling time |
| P1 Foundation | **Gate passed** | precision 96.5% ≥ 90% (Wilson 93.0–98.3%) | P1-01..P1-10, P1-12 `[x]`; P1-11 labels done, relabel due 2026-11-22 |
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
| Corpus link coverage | 285/792 sources have an incoming citer edge; 507 do not; 34/4,168 citer papers have no outgoing edge; 533 papers have no edge | `docs/reports/P1-corpus-coverage.md` |
| Full store load (twice) | Paper 4,928; CITES 4,982; contexts 6,117; notices 792; vectors 4,928 + 6,117 | `data/corpus/infectious-disease-v1/store-load.log` (untracked); re-queried 2026-11-15 |
| P1-10 100-paper dry-run (estimate) | 764,084 prompt tokens; mean 7,641/paper; expected 500 claims at 5/paper | `docs/reports/P1-baseline-estimate.md` |
| P1-10 Groq pilot (historical, n=1 paper) | 21 silver claims from 28 extracted; 7 span-not-verbatim; 0 parse failures; 6,809 prompt + 7,159 completion (3,011 reasoning) tokens; $0.005317 list price; 16,459 ms latency; prompt gap -10.3% vs chars/4 | `docs/reports/P1-baseline-pilot.md` |
| P1-10 Gemini pilot (n=5 papers) | NOT MEASURED — 10 attempts, 0 successes: 1× HTTP 400, 1× HTTP 504, 8× HTTP 503 | `docs/reports/P1-gemini-pilot-diagnosis.md` |
| P1-10 Gemini validation (n=1 paper) | 0 claims; 2 attempts, both HTTP 504 `DEADLINE_EXCEEDED` at ~119 s; thinking medium, max output 16,384 | `eval/silver/claims_v1/gemini_pilot_v2/run_report.json` (untracked, partial) |
| **P1-10 Flash-Lite baseline (n=100 papers)** | **100 papers, 765 claims**; 88.7% verbatim; 0 parse failures; 97 span + 11 unknown-section rejects; 697,734 prompt / 142,057 completion (0 thinking); $0.564459 list price; $0.005645/paper, $0.000738/accepted claim; output 62.9% of cost; mean 6,448 ms / p95 15,490 ms; 120 of 450 requests; prompt gap -8.7% | `eval/silver/claims_v1/baseline_flashlite/run_report.md` |
| P1-10 3.8 Flash reference (n=5, not baseline) | 74 claims; 100% verbatim; 0 failures; 28,087 prompt / 22,073 completion (9,177 thinking); $0.103838 list ($0.001403/claim); latency mean 196,588 ms, p95 290,982 ms; 17/18 requests | `eval/reference/claims_v1/flash38/run_report.md` (see `REFERENCE_ONLY.md`) |
| **P1 baseline report (PRD gate)** | `docs/reports/P1-baseline.md` — measured extraction, cost, latency, corpus/retraction coverage; audited precision pending owner labels | `docs/reports/P1-baseline.md` |
| **P1-11 official audit export** | 200 claims from 45 papers (≤5/paper), seed 20261114, 22 dev / 23 test | `eval/audit/claims_audit_v1.csv` (+ `.summary.json`) |
| **P1-11 audited precision (gold)** | **96.5%** (Wilson 93.0–98.3%; cluster bootstrap 94.0–98.6%); 193 CORRECT, 7 NOT_A_CLAIM, 0 distorted/unsupported/duplicate; single labeler | `docs/reports/P1-audit.md` |
| Evidence-span normalization | Strict 7/28 (25.0%) rejects → normalized 3/28 (10.7%) on the Groq pilot; 4 hyphen variants fixed, 2 merged tails and 1 case-only remain rejected | `docs/eval/EVIDENCE_SPANS.md` |
| P1-11 audit tooling | HTML labeler (no network), exact-column overlap export (20%), strict validator + existing metrics; **0 claims labelled** | `eval/audit/README.md` |

## Open questions for owner
- **Push:** resolved 2026-11-15 — local `main` was fast-forwarded to `ab2dbfe`; the agent does not push. The owner pushes when ready.
- **Gemini large model:** resolved 2026-11-15 by ADR-0019 — `gemini-3.5-flash-lite` is the baseline; `gemini-3.8-flash` remains the large/escalation reference on small subsets only.
- **Live data:** contact emails and Neo4j are configured locally; confirm the addresses are the ones to use for polite-pool requests. Never paste values in chat.
- **Retraction Watch:** resolved 2026-11-14. Crossref’s canonical Metadata Retrieval page lists the database as CC0; owner approved use and the acquisition method (REST lookups + pinned GitLab CSV snapshot; no raw CSV committed). Recorded in `docs/DATA_SOURCES.md`.
- **Sub-topic:** resolved 2026-11-14 — ADR-0012 accepted (`(HSC) Medicine - Infectious Disease`), with the exact-count stop condition and PMID-gap reporting. Oncology deferred to its own ADR as a held-out transfer corpus.
- **Labeling:** when can the owner block ~3–6 hours for P1-11 and ~3–6 hours for P3-03, including the P1-11 7-day relabel gap?
- **ADR renumbering:** confirm ADR-0008 (scale) and ADR-0009 (Day-0) are the intended final numbers.
- **Local tooling:** no GNU `make` on this host; equivalent Python commands are used. Hook environments must be built with the system **Python 3.12** (`py -3.12 -m pre_commit install --install-hooks`), because the 3.11 venv's base at `D:\` breaks virtualenv; `secret-scan` runs inside a pre-commit env, so it no longer depends on the host's broken bare `python`. `py -3.12 -m pre_commit run --all-files` passes every hook; CI uses Ubuntu. See `docs/LOCAL_SETUP.md`.
- **Provider SDK adapters:** the approved Groq adapter is `src/axion/llm/groq.py` (`groq==1.7.0`); Gemini/Anthropic remain deferred. Offline tests still use the scripted provider.

## Blocked tasks
- ✅ P1-10: closed 2026-11-15 — measured baseline 100 papers / 765 claims on `gemini-3.5-flash-lite`, $0 real spend.
- P1-11: labels are in and precision is computed (96.5%). Remaining: the blind 10% relabel **due ≥7 days after 2026-11-15 (2026-11-22)** or a second labeler on `claims_audit_v1_overlap.csv`; then `audit_validate.py --overlap` reports κ.
- P1-12: follows from P1-11 (and the full P1-10 run).
- P3-03: owner labeling (later phase).

## Session log (newest first)
### 2026-11-15 — Freebuff / DeepSeek V4.x Flash — P1 audit labelled, gate passed
- Status: **P1 gate PASSED**; branch `p1`; nothing pushed by this session's agent-owned steps until the owner asked (then `p1` + `main` were pushed together).
- Owner labelled all 200 audit claims: 193 `CORRECT`, 7 `NOT_A_CLAIM` (each with a note), labeler `owner`, rubric v2. The agent created no labels.
- Measured: **precision 96.5%** (Wilson 95% 93.0–98.3%), paper-level cluster bootstrap **94.0–98.6%** (45 papers, 2,000 resamples, seed 20261114), 0 distorted/unsupported/duplicate. Report `docs/reports/P1-audit.md` (195 lines of per-section detail, agreement pending).
- `scripts/build_p1_report.py` now regenerates the gate report from the run report, audit, and corpus manifest: headline table plus gate decision. **P1-12 done** — `make report` reproduces `docs/reports/P1-baseline.md` byte-for-byte with no invented values; missing inputs still print NOT YET MEASURED.
- Fixed a rendering bug in `render_markdown`: the failure-breakdown rows were emitted after the cluster-bootstrap section, breaking the table.
- Verification: **304 passed, 2 skipped**; ruff, ruff format, strict mypy, pre-commit clean.
- Next: blind 10% relabel on 2026-11-22 (or second labeler on the overlap file) to close P1-11; P2 can start on the measured 96.5% baseline.

### 2026-11-15 — Freebuff / DeepSeek V4.x Flash — P1-10 Flash-Lite baseline completed
- Status: **P1-10 done**; branch `p1`; local `main` fast-forwarded to `p1`; nothing pushed (the owner pushes).
- Model switch (ADR-0019 Accepted, amends ADR-0017): baseline `gemini-3.5-flash-lite` at 15 RPM / 250K TPM / 500 RPD with a 450/day runner cap and 50-request margin; `gemini-3.8-flash` demoted to the large/escalation reference for small subsets; P2 small tier + bulk labeler stay **Proposed** (`gemini-3.1-flash-lite`, Gemma 4 26B/31B — structured output, 16K TPM, and pricing untested). Config fixed at thinking `default`, temperature 0.0, max output 16,384, prompt v1; the runner records the literal `default` and sends no `thinking_config`.
- Measured baseline `p1-10-flashlite-s20261114-n100`: **100/100 papers, 765 accepted silver claims**, 0 parse failures, verbatim 88.7% (strict identical; 0 normalization fixes), 11 claims rejected for naming a missing section. 697,734 prompt / 142,057 completion / **0 thinking** tokens; list price **$0.564459**; **$0.005645 per paper**, **$0.000738 per accepted claim**; output tokens 62.9% of cost; latency mean 6,448 ms, p95 15,490 ms; prompt estimate -8.7%; **120 of 450** daily requests; $0 real spend. The 3-paper checkpoint (36 claims, 97.3% verbatim, 5.5 s mean) preceded it and was a true prefix of the seeded order.
- Failure handling: a 503 and a TLS `ReadError` each stopped a resume before the policy change; TLS/socket read errors are now transient (one retry through the pacer) and an isolated provider failure is recorded while the batch continues, stopping only after three consecutive failures (quota errors stop immediately). Both affected papers were recovered; 20 of 120 requests were failed attempts.
- Audit export (ADR-0018): `eval/audit/claims_audit_v1.csv` — 200 claims from **45 papers**, max 5 per paper, seed 20261114, 22 dev / 23 test papers, every label field blank; `claims_audit_v1.summary.json` records the corpus snapshot. **No labels were created.**
- Bug fixed while measuring: strict/normalization counters were per-invocation, so a resumed run reported a meaningless 100% strict rate; they now persist in `strict_state.json` and the final report carries recomputed cumulative values.
- Tooling: hook envs are built with the system Python 3.12 (the 3.11 venv's `D:\` base breaks virtualenv), so `py -3.12 -m pre_commit run --all-files` passes every hook, including `secret-scan`, with no `SKIP=`. Offline checks: **302 passed, 2 skipped**; ruff, ruff format, strict mypy clean.
- Optional reference comparison `p1-10-ref-flash38-s20261114-n5` (first 5 seeded papers, not baseline, not silver): **74 claims, 100% verbatim, 0 failures**, 9,177 of 22,073 completion tokens were thinking, list price $0.103838 (**$0.001403/claim**, 1.9× Flash-Lite), latency mean 196.6 s / p95 291.0 s (≈30× slower), 17 of 18 daily requests.
- Next: owner labeling for P1-11, then P1-12.

### 2026-11-15 — Freebuff / DeepSeek V4.x Flash — P1 SESSION IN PROGRESS (failure diagnosis)
- Status: **IN PROGRESS / HANDOFF**; branch `p1`. No push; local `main` was fast-forwarded to `p1` with `--ff-only` at the end of the session.
- Plan: (A) diagnose the Gemini pilot offline from the ledger; (B) make failures record a sanitized root cause everywhere; (C) enforce the retry/quota rules; (D) one or two live validation requests; (E) implement the ≥40-paper audit-export rule with a cluster bootstrap CI; (F) verify the earlier owner items; (G) checkpoint docs.
- **Root cause (A):** 10 attempts, 0 successes on the pilot — 1× HTTP 400 `INVALID_ARGUMENT` (schema `additional_properties`), 1× HTTP 504, 8× HTTP 503. Nothing reached token exhaustion; the run report only said “all LLM providers failed”. Report: `docs/reports/P1-gemini-pilot-diagnosis.md`.
- **Fixes (B/C):** `FailureDetail` on every provider error; ledger columns `error_class`/`error_status`/`http_status`/`finish_reason` (idempotent migration); `failures.jsonl` and the run report carry class, sanitized message, statuses, finish reason, tokens, and attempts; `OutputTokenExhaustedError`/`EmptyResponseError` are permanent; retries are network/5xx only, at most once, gated by the free-tier pacer; 429/daily quota stop the run. `max_output_tokens` 16384, thinking medium recorded per call. 296 tests pass; ruff/format/strict mypy clean (third-party type stubs are skipped in mypy config because mypy 1.14 cannot parse them).
- **Validation (D):** 2 requests (1 + one allowed retry), both HTTP 504 `DEADLINE_EXCEEDED` at ~119 s. **0 claims.** Daily quota 12/20 used. Adapter timeout raised to 300 s (unverified).
- **Audit rule (E, ADR-0018):** seeded export capped at 5 claims/paper and ≥40 papers (`sample_claims_by_paper`), wired into `scripts/audit_sample.py` and the runner's automatic export; metrics report a paper-level cluster bootstrap CI next to Wilson with the dependence limitation. **No labels exist.**
- **Verification of earlier items (F):** ADR-0017 Accepted; `pricing.yaml` v2 matches the official page (checked 2026-11-15, 3.8 Flash $0.75/$3.75 → $1.50/$7.50 on 2027-01-01; 3.5 Flash-Lite $0.30/$2.50); `google-genai==2.8.0` was uploaded 2026-06-03 (outside the 14-day window, confirmed on PyPI); generation config and silver provenance are recorded.
- Next: one validation call after the Pacific reset; if 504 persists, lower thinking or per-paper claims with a recorded config change.

### 2026-11-15 - DeepSeek V4.1 Flash Free - Gemini switch, normalization, pacing
- Status: **PARTIAL**; branch `p1`. Local `main` fast-forwarded to `72f2dad` and **not pushed**. Worktree contains the Gemini implementation.
- ADR-0017 Accepted: Gemini free tier replaces Groq for P1-10. Large `gemini-3.8-flash`, small `gemini-3.5-flash-lite`; `google-genai==2.8.0` pinned; Groq adapter/tests kept unused. Real spend stays **$0**.
- Implemented: dated list-price versions and post-promotion estimates; ledger fields for billing/price version/input-output USD/generation config; `billing=free_tier` with list price; Gemini adapter with cleaned JSON-schema structured output and thinking-token accounting; free-tier pacing with Pacific reset and clean daily stop; strict-vs-normalized span matching with source-span rewrite and failure evidence/category; seeded sample order; resumable daily runs.
- Normalization result on the historical Groq pilot: 7/28 (25.0%) strict rejects → 3/28 (10.7%) after normalization. 4 U+2011 hyphen variants fixed; 2 non-contiguous merged tails and 1 case-only remain. Prompt v2 not justified; prompt stays v1.
- Live Gemini attempts: first request rejected Pydantic `additionalProperties`; fixed by sending cleaned `responseJsonSchema` and validating locally. `gemini-3.5-flash-lite` minimal call succeeded. `gemini-3.8-flash` returned repeated HTTP 503 `UNAVAILABLE` (“high demand”), so the 5-paper pilot is **not measured**. No baseline claims/tokens/cost are claimed.
- Verification: **286 passed, 2 skipped**; `ruff check`, `ruff format --check`, and strict `mypy` clean. Docs: ADR-0017, `docs/eval/EVIDENCE_SPANS.md`, TODO/PROGRESS updates.
- Next: retry the 5-paper pilot when `gemini-3.8-flash` is available; do not silently change the large tier. Then continue the 100-paper sample in seeded order across days and export the audit once ≥250 claims exist.
### 2026-11-15 - DeepSeek V4.1 Flash Free - P1-10 paid pilot + P1-11 tooling
- Status: **PARTIAL**; branch `p1`, clean tree at start (`ab2dbfe`); local `main` fast-forwarded to `ab2dbfe` and **not pushed**. The owner pushes.
- Pricing/SDK: filled `src/axion/config/pricing.yaml` with the official Groq list prices checked 2026-11-15, recording both model URLs and the check date; set the P1-10 cap to **$3 total** in untracked `_private/budget.md`; added `groq==1.7.0` (published 2026-08-26, outside the 14-day window) and `src/axion/llm/groq.py` behind `ProviderAdapter`. The ledger now records `reasoning_tokens` (idempotent migration).
- Pilot: first paper succeeded (**21 claims / 28 extracted**; 7 verbatim-span rejects; 0 parse failures; prompt 6,809; completion 7,159 incl. 3,011 reasoning; list price **$0.005317**; 16,459 ms). The second paper's request was **12,111 tokens against a TPM limit of 8,000**; Groq returned HTTP 413 `rate_limit_exceeded`. After the existing retry/cooldown, the run stopped at a clean one-paper checkpoint. No workaround was attempted.
- Why the full run did not start: the free tier is **8,000 TPM and 200,000 TPD**; the 100-paper sample's mean prompt alone is 7,641 tokens (p95 15,867) and 100 papers exceed the daily cap. The 5-paper pilot cannot complete on this tier. Owner decision required (raise the limit, approve another provider, or approve a different sampling rule).
- Audit tooling: `eval/audit/claim_audit_tool.html` (single file, no network/dependencies, blind, keyboard, autosave, undo, exact CSV download, span-missing warning); `scripts/audit_validate.py` (strict labels/notes, `--allow-partial`, overlap merge, existing precision/Wilson/failure/κ metrics); `--overlap-out` seeded 20% export; `eval/audit/tool_smoke_test.csv`; README 5-line procedure. **No claims were labelled.**
- Honesty note: the HTML inline JS was syntax-checked with `node --check`; an interactive browser test was **not** completed. The owner should smoke-test with `eval/audit/tool_smoke_test.csv`.
- Pilot audit export: `eval/audit/claims_audit_v1_pilot.csv` has **21 claims**, below the 200 minimum. It exists only to exercise tooling; it is not the official audit sample.
- Verification: full suite **257 passed, 2 skipped**; `ruff check`, `ruff format --check`, and strict `mypy` clean. (The count includes the new Groq adapter/413/500 tests, audit-validator, overlap, HTML-column, and context tests.)
- Next: owner decides on the Groq limit/provider/sampling; then finish the 5-paper pilot, run the seeded 100-paper sample (extend if claim yield <250), export ≥200 claims, and label. P1-12 stays blocked on measured audit values.
### 2026-11-15 - DeepSeek V4.1 Flash Free - P1 verification pass
- Status: **VERIFIED** on branch `p1`; clean tree at `a8d6d85`; `origin/p1` is the same commit. No corpus ingest, store reload, LLM call, label, or paid call was performed.
- Re-ran: **245 passed, 2 skipped**; `ruff check` and `ruff format --check` clean (79 files); strict `mypy` clean (42 source files).
- Re-queried live stores: Neo4j `Paper 4,928`, `CITES 4,982`, `CitationContext/IN_PAPER/POINTS_TO 6,117`, `RetractionNotice/RETRACTED_BY 792`; Chroma `papers 4,928`, `citation_contexts 6,117`, `claims 0`. This independently matches the committed store-load evidence.
- Verified the committed CSVs: SHA-256 values match the manifest; 4,928 paper rows, 4,982 cite rows, 6,117 contexts; all cite endpoints resolve to a paper.
- Found and recorded **link coverage**: 285/792 source papers have an incoming citer edge and 507 do not; 4,134/4,168 citer papers have an outgoing edge and 34 do not; 533 papers have no edge in either direction. The cap is not coverage-neutral. Added the count to `scripts/corpus_coverage.py` (with a unit test) and regenerated `docs/reports/P1-corpus-coverage.{md,json}`.
- Checkpoint diagnosis of the 507 isolated sources: 1 has no PMID, 52 have no MEDLINE citation rows, 15 have no eligible OA/full-text citer, and 439 have at least one eligible citer but no included edge (cap-dominated; full-text failure can also remove an edge).
- No data or manifest values changed. The P1-08 minimums still pass (792 sources, 6,117 contexts).
- Next: owner decides whether a future ingest should rebalance citer selection toward one citer per source; paid P1-10 remains blocked on prices, budget cap, SDK approval, and sample confirmation.
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
