# PROGRESS — live project state

> Agents: update this file at the end of every session (and mid-session if long). Newest log entries first.

## Current state
- **Phase:** P1 (foundation) — **all tasks P1-01 through P1-12 are `[x]`; phase complete.** The baseline is measured on `gemini-3.5-flash-lite` (**100 papers, 765 silver claims**, $0 real spend) and the official audit export exists (**200 claims from 45 papers**). **P1 gate PASSED (final, 2026-11-16): audited precision 96.5%** ≥ the 90% floor. The independent 40-claim overlap is complete (40/40 `CORRECT`, raw agreement 100%); Cohen's κ is **not estimable** because both label sets used one label and the overlap contains no `NOT_A_CLAIM` rows. **P2 is complete (gate accepted 2026-11-18):** all 12 live tasks are `[x]` (P2-03 dropped via ADR-0008); the literal gate passes on two rows, with retention as the accepted caveat; ADR-0021/0022 are Accepted. **P3 is in progress:** P3-01 is complete (guideline v1.1, 20/20 pilot labels, single-labeler limitation); **P3-02 is complete** (6,117 deterministic candidate contexts over 285 source papers — 258 with ≥1 context, 27 at zero — 214 source-claim proxies linking 69.7% of contexts, idempotent Neo4j load, no LLM, $0). **P3-03 wave 1 is labelled and overlap 2 is built**: labels 150/150 (25 `RELIES_ON` / 120 `MENTIONS` / 5 `UNRELATED` / 0 `insufficient_context`), overlap 2 = 31 rows labelled by `friend`, **agreement 31/31 raw with κ 1.000 (degenerate: zero discordant pairs — consistency, not established reliability)**; ADR-0023 **Accepted 2026-11-18** with Amendments A and B (the pre-built 30-row overlap is superseded; the 34 title-only stub rows are a pre-registered report-only stratum). Waiting on the wave-1 metrics script, then P3-04.
- **P1-11 audit (2026-11-16):** 200 claims / 45 papers, **193 CORRECT, 7 NOT_A_CLAIM** (0 distorted, unsupported, duplicate) → **precision 96.5%**, Wilson 95% **93.0–98.3%**, paper-level cluster bootstrap **94.0–98.6%** (45 clusters, 2,000 resamples, seed 20261114). Independent second labeler (`friend`) labelled the seeded 40-claim overlap: **40/40 CORRECT**, raw agreement **100%**, κ **not estimable/degenerate**; the overlap contains none of the 7 non-claims, so it does not estimate error-class agreement. Report: `docs/reports/P1-audit.md`.
- **Owner decisions recorded:** ADR-0011 (clean V2 store rewrite), ADR-0012 (infectious disease, exact-count conditions, PMID limitation, config-driven manifest, oncology deferred), ADR-0013 (total corpus including citers, ~5,000 hard cap), ADR-0014 (P1-10 seeded sample), ADR-0015 Proposed (P1 blast-radius counts conditional on included citers; expansion deferred to P3), **ADR-0016 Accepted (agreement via independent 20% second-labeler overlap, 2026-11-16)**, **ADR-0017 Accepted (Gemini free tier replaces Groq; $0 real spend)**, **ADR-0018 Accepted (audit export: ≥40 papers, ≤5 claims/paper, paper-level split, cluster bootstrap CI)**, **ADR-0019 Accepted (P1 baseline model = `gemini-3.5-flash-lite`; `gemini-3.8-flash` is the large/reference model only; P2 small tier + bulk labeler Proposed, not decided)**, **ADR-0021 Accepted (two retention numbers + `$/core-section claim`, 2026-11-18)**, **ADR-0022 Accepted (operating point `p2-05-length30-v1`, 2026-11-18)**, **ADR-0023 Accepted with Amendments A/B (P3-03 gold set: waves, two-frame sampling, source-level split, post-hoc overlap, stub reporting stratum, 2026-11-18)**.
- **P1-10 Gemini implementation (2026-11-15):** `google-genai==2.8.0` pinned; `src/axion/llm/gemini.py` uses cleaned JSON-schema structured output, validates with Pydantic, maps `candidates + thoughts` to completion and `thoughts` to reasoning; `pricing.yaml` v2 has dated list prices (3.8 Flash $0.75/$3.75 through 2026-12-31, $1.50/$7.50 from 2027-01-01; 3.5 Flash-Lite $0.30/$2.50); the ledger records billing, price version, input/output/post-promotion USD, and generation config. Free-tier calls record list price with `billing=free_tier`; real spend is $0. The current ADR-0019 baseline is `gemini-3.5-flash-lite` at **15 RPM / 250K TPM / 500 RPD**, runner cap **450/day** with a 50-request margin; the earlier 5 RPM / 20 RPD values were the ADR-0017 trial tier. `src/axion/llm/pacing.py` enforces the configured RPM gap, daily cap, Pacific-day reset, and a clean `DailyQuotaError` stop.
- **P1-10 baseline measured (2026-11-15, `p1-10-flashlite-s20261114-n100`):** 100/100 seeded papers, **765 accepted silver claims**, 0 parse failures, 108 recorded failures (97 span-not-verbatim, 11 unknown section). Verbatim **88.7%**, strict identical (0 normalization fixes). Tokens **697,734 prompt / 142,057 completion / 0 thinking** (839,791 total); list price **$0.564459** = **$0.005645/paper** and **$0.000738/accepted claim**; output **62.9%** of cost; latency mean 6,448 ms, p95 15,490 ms; prompt-gap **-8.7%**; **120 of 450** daily requests. Config: thinking `default` (no `thinking_config`), temperature 0.0, max output 16,384, prompt v1. Report: `eval/silver/claims_v1/baseline_flashlite/run_report.md`.
- **Provider-failure policy:** TLS/socket read errors are transient (one retry through the pacer); an isolated provider failure is recorded and the batch continues; the run stops after **three consecutive** provider failures or immediately on a 429/daily-quota error (ADR-0019).
- **Normalization-only evidence fix:** documented in `docs/eval/EVIDENCE_SPANS.md`; accepted spans are rewritten to the exact source substring. Groq pilot rejects: 4 U+2011 hyphen variants (fixed), 2 non-contiguous merged tails (rejected), 1 case-only (rejected). Strict reject rate 25.0%; normalized 10.7%. Prompt v2 is not justified (paraphrase was 1/7).
- **Gemini pilot root cause (2026-11-15, ledger-derived):** run `p1-10-gemini-pilot-s20261114-n5` recorded **10 attempts, 0 successes**: 1× HTTP 400 `INVALID_ARGUMENT` (`additional_properties` in the schema, fixed), 1× HTTP 504 `DEADLINE_EXCEEDED`, 8× HTTP 503 `UNAVAILABLE`. No attempt reached an empty-output/token-exhaustion state; that hypothesis came only from the separate `max_output_tokens=16` probe. The 10 attempts used 10 of the 20 daily requests. Report: `docs/reports/P1-gemini-pilot-diagnosis.md` (`scripts/failure_report.py`).
- **Failure/retry hardening (ADR-0017 amendment):** sanitized root cause (class, message, HTTP/provider status, finish reason, tokens, attempts) now lands in the ledger, `failures.jsonl`, and the run report; `max_output_tokens` is **16384** with thinking **medium** recorded per call; empty `MAX_TOKENS` output is `OutputTokenExhaustedError` and non-retryable; only network/5xx/504 retries, at most once, and retries are paced like first attempts; 429/`RESOURCE_EXHAUSTED`/daily quota stop the run at a checkpoint.
- **Gemini validation (2026-11-15, 2 requests):** the fixed request was accepted (no schema error) but `gemini-3.8-flash` returned **HTTP 504 `DEADLINE_EXCEEDED` twice**, each after ~119 s, with `thinking=medium` and `max_output_tokens=16384` on a 7,589-token prompt. **No claims/tokens/cost measured.** The adapter timeout is now 300 s; that change is unverified. Daily quota used: **12 of 20** (cap 18).
- **Link coverage caveat:** 285 of 792 source papers have at least one incoming citer edge; 507 do not, and 34 citer papers have no outgoing edge. The 5,000-paper cap is not coverage-neutral. Blast-radius counts are **conditional on the included citer set only**; P3 owns on-demand expansion (ADR-0015 Proposed). Exact counts are in `docs/reports/P1-corpus-coverage.md`.
- **P2-01 complete (2026-11-16, commit `6033b07`):** the ablation harness replays a configuration against the frozen gold audit with **no LLM calls**. Baseline replay reproduces P1 exactly: aligned precision **0.965** (193/200), retention **1.000**, dev **0.961165**, test **0.969072**, unverifiable **45.1%**, cost **$0.005644590/paper** vs the P1 run's **$0.005645**. Verbatim gold, ledger cost, paper-level split; `eval/ablation/results/` is regenerable and ignored.
- **P2-02 section targeting measured (2026-11-16):** `core` (abstract/results/conclusion) run `p2-02-sections-core-s20261114-n100` completed **93/96 papers, 428 claims**, **$0.002460613/paper vs $0.005644590 baseline = −56.4%**, aligned precision dev 92.9% / test 96.3%, but **retention 34.5%** (unverifiable 59.7%). Measured cause: only **57/200 gold claims (28.5%)** are in those sections. **Negative result as a standalone lever** — the cost win is real, the audited-output loss is not acceptable alone; it is judged inside P2-07. Free tier, $0 real spend, 283 ledgered requests.
- **P2-03a closed (2026-11-17):** teacher labelling stopped at **98 non-gold papers** (55 P1 baseline + 43 P2-03a; **687 silver claims**) because the P2-03c learning curve is flat. Sample plan `docs/reports/P2-03a-sample.md`; dry run `docs/reports/P2-03a-dryrun.md`; draw verified **0 gold / 0 already-labelled**; seed 20261114; increment list price $0.234809, real spend $0.
- **P2-03b student measured (2026-11-17):** frozen `all-MiniLM-L6-v2` sentence encoder + logistic head trained on **98 gold-free papers / 16,452 sentences / 650 positives**. At the fixed baseline claim budget (top-8 sentences/paper): **frozen test retention 30.9% (30/97)**, aligned precision **100.0% [88.6–100]**, unverifiable **83.7%**; dev retention 25.2%. Inference **1,278 ms/paper CPU**, no LLM calls, no ledger cost. **Negative result standalone** — precision survives, but the student recovers under a third of audited claims. Artifact `eval/student/student_v1.model.json`; report `docs/reports/P2-student.md`; harness row `student-minilm`.
- **P2-03c learning curve (2026-11-17):** nested silver prefixes 10→98 papers; retention@8 **23.3%→25.2%**, retention@20 **45.6%→56.3%**, no monotone trend; precision 96–100%. Plateau published; it is why the 300-paper label ceiling was not spent.
- **P2-04 measured (2026-11-17):** cache re-run probe on the first 5 frozen baseline papers: **5/5 cache hits, 0 provider calls, 0 tokens, $0.000000**, cache table unchanged at 238 rows; across all runs 9/486 attempts are hits and 0 hits carry a price. Dedup census on the 100-paper baseline sample: **190/16,466 duplicate sentences (1.15%)**, 174 within-paper / 16 cross-paper, ≈5,963 avoidable prompt tokens (upper bound, **not applied**). Dedup is not a material lever at this scale; report `docs/reports/P2-04-cache-dedup.md`.
- **P2-05 escalation measured (2026-11-17):** the planned confidence signals **failed calibration** (mean top-score rho −0.386, max −0.444, entropy −0.072 vs per-paper retention: low confidence predicts *more* retention, so confidence escalation is worse than random). The shipped rule is the only signal that beat random: escalate the **longest 30%** of papers (sentence count, rho −0.682), frozen before the test read. **Frozen test: e=30.4%, retention 56.7% (55/97), precision 98.2% [90.4–99.7], savings 61.6%**; overall **e=31.1% (14/45), $0.002505/paper vs $0.006282 = −60.1%**, $/retained $0.000989 vs $0.001413. Stage 2 (3.8-flash) never fired on gold (0/14); teacher zero-claim rate 10/98 projects 3.2% and **54.8% savings**, and a dev probe (ledger 487→488, $0.014867 list price) gives 52.6%. Real spend $0; `s=0` in LLM terms, student 1,180 ms/paper CPU. Precision survives; retention does not. Report `docs/reports/P2-05-escalation.md`; row `escalation-length30`.
- **P2-05b flywheel negative (2026-11-17):** gold-free flywheel on 55 P1 base papers + 40 P2-03a pool papers (28 candidate / 12 held-out). The agreement signal is **mean reciprocal rank** of teacher-positive sentences (a binary top-8 recall signal was degenerate: 12/28 zeros, realised 42.9% and `e` rose). Threshold 0.0339 selected **8/28** papers and added **1,890 sentences / 77 positives**. Held-out `e` **8.3% → 8.3%** (1/12 both), mean MRR 7.64% → 7.14%; **gold test retention 27.8% → 26.8%**, precision 96.3% → 96.2%, unverifiable 85.3% → 85.9%. The frozen 98-paper reference is 30.9% / 100%. **Negative result:** targeted labels did not reduce `e` and did not hold test retention. Report `docs/reports/P2-05b-flywheel.md`; row `flywheel-student`; no LLM calls, real spend $0.
- **Next action:** **second labeler labels the wave-2 overlap.** Send only `eval/audit/p3-03-labeler2/p3-03-wave2-overlap2-labeler.html` (30 rows, ~19 min at the now-measured 38 s/row); they return `dependency_audit_v1_wave2_overlap2_labelled.csv`. Then run `scripts/dependency_agreement.py` against the wave-2 pair (negative floor already met at 18) and read the negative-side κ that wave 1 could not estimate. **Then the owner decides wave 3**: 77 positives would need another 254–500 rows (pooled weighted / wave-2-only rate), which is larger than waves 1+2 combined — the alternatives are to accept a decision-grade read at 37 positives, extend uniformly, or narrow the claim. After that, P3-04 baselines. Do not re-open P2 without an ADR.
- **Last updated:** 2026-11-18 by Buffy (second labeler returned; agreement 31/31 with degenerate κ recorded; next is the wave-1 metrics script)
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
- ✅ Push: `p1` and `main` are kept in sync and pushed at checkpoints; CI status is not available locally (`gh` is not installed).
- ✅ Contact emails, Groq key, Neo4j password, and V2 Neo4j are configured locally; no secret values are tracked.
- ✅ P1-10: closed 2026-11-15 on the Gemini free tier (100 papers / 765 claims; $0 real spend). The old Groq TPM blocker is historical.
- ✅ P1-06: Retraction Watch CC0 verified on Crossref’s Metadata Retrieval page and owner-approved; loader/linker and coverage report committed.
- ✅ P1-08/P1-09: closed with exact counts and a full store load; the remaining coverage caveat is recorded above and in `docs/reports/P1-corpus-coverage.md`.
- ✅ P1-11: closed 2026-11-16 (independent 40-claim overlap; κ not estimable). ⛔ P3-03: owner labeling (later phase).
- ⚪ Can wait: B5 weekly hours; B6 `_private/` backup risk; P5 licence/release/outreach.

**Recorded facts**
- V1 snapshot: offline suite **252 passed, 12 deselected**; `v1-final` at `b4b6a25338057bd05bc6b74bc75b26198fe546e8`; custom V1 history scan 0 candidate hits; owner reported V1 keys rotated.
- Day-0 decisions: MIT for now; private until P5; $0 paid budget; `_private/` no backup accepted; weekly hours open-ended. ADR-0008 is the scale approach; the Day-0 ADR is ADR-0009. Owner confirmation of the renumbering is requested.
- `origin/p1` is at `a8d6d85`; local `main` (`332fbf9`) is 11 commits ahead of `origin/main` and has not been merged with `p1`.

## Phase status
| Phase | Status | Gate result | Notes |
| :-- | :-- | :-- | :-- |
| Day 0 | Agent close-out complete; owner items pending | — | CI confirmation, paid pricing/budget, Retraction Watch terms, labeling time |
| P1 Foundation | **Complete** | precision 96.5% ≥ 90% (Wilson 93.0–98.3%); independent overlap raw 100%, κ not estimable | P1-01..P1-12 `[x]`; no `NOT_A_CLAIM` rows in the 40-claim overlap |
| P2 Cost cascade | **Complete — gate accepted 2026-11-18** | literal gate PASS on 2 rows (≥50% savings within 2 precision points); best is `escalation-length30` **−55.6% $/paper at 98.2% test precision but 56.7% retention** | All 12 live tasks `[x]` (P2-03 dropped via ADR-0008). ADR-0021/0022 **Accepted**; the 56.7% retention is a stated limitation, and no measured row reaches 90%. Report: `docs/reports/P2-cascade.md` |
| P3 Blast radius | **In progress — P3-01, P3-02 complete; P3-03 wave 1 built, awaiting owner labels** | — | Guideline v1.1 + 20-row pilot: 16 MENTIONS / 2 RELIES_ON / 2 UNRELATED, 20/20 notes, single owner labeler (`Soham`) so agreement is not estimable; owner accepts responsibility (`docs/reports/P3-01-pilot.md`). **P3-02:** 6,117 candidate contexts / 285 sources with citers (258 with ≥1 context, 27 at zero), 214 proxies → 69.7% linked, 0 duplicate keys, idempotent Neo4j load, $0 (`docs/reports/P3-02-candidates.md`). Pilot RELIES_ON base rate 2/20 = 10% [2.8–30.1%], too coarse to size the audit alone. |
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
| Claim extraction precision (±95% CI) | 96.5% (Wilson 93.0–98.3%) | `docs/reports/P1-audit.md` |
| Baseline cost per paper | $0.005644590 | `docs/reports/P2-ablation.md` (baseline row) |
| Cost per paper after cascade | $0.002505111 (−55.6%), retention 56.7% | `docs/reports/P2-frontier.md` |
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
| **P1 baseline report (PRD gate)** | `docs/reports/P1-baseline.md` — measured extraction, cost, latency, corpus/retraction coverage; audited precision **96.5%** (Wilson 93.0–98.3%; independent overlap raw 100%, κ not estimable) | `docs/reports/P1-baseline.md` |
| **P1-11 official audit export** | 200 claims from 45 papers (≤5/paper), seed 20261114, 22 dev / 23 test | `eval/audit/claims_audit_v1.csv` (+ `.summary.json`) |
| **P1-11 audited precision (gold)** | **96.5%** (Wilson 93.0–98.3%; cluster bootstrap 94.0–98.6%); 193 CORRECT, 7 NOT_A_CLAIM, 0 distorted/unsupported/duplicate; independent 40-claim overlap **40/40 CORRECT**, raw 100%, κ not estimable (all one class) | `docs/reports/P1-audit.md` |
| Evidence-span normalization | Strict 7/28 (25.0%) rejects → normalized 3/28 (10.7%) on the Groq pilot; 4 hyphen variants fixed, 2 merged tails and 1 case-only remain rejected | `docs/eval/EVIDENCE_SPANS.md` |
| P1-11 audit tooling | HTML labeler (no network), exact-column overlap export (20%), strict validator + existing metrics; **200 primary labels in; 40/40 second-labeler overlap labelled; tool browser smoke test not run by agent** | `eval/audit/README.md` |

## Open questions for owner
- **Push:** resolved 2026-11-15 — local `main` was fast-forwarded to `ab2dbfe`; the agent does not push. The owner pushes when ready.
- **Gemini large model:** resolved 2026-11-15 by ADR-0019 — `gemini-3.5-flash-lite` is the baseline; `gemini-3.8-flash` remains the large/escalation reference on small subsets only.
- **Live data:** contact emails and Neo4j are configured locally; confirm the addresses are the ones to use for polite-pool requests. Never paste values in chat.
- **Retraction Watch:** resolved 2026-11-14. Crossref’s canonical Metadata Retrieval page lists the database as CC0; owner approved use and the acquisition method (REST lookups + pinned GitLab CSV snapshot; no raw CSV committed). Recorded in `docs/DATA_SOURCES.md`.
- **Sub-topic:** resolved 2026-11-14 — ADR-0012 accepted (`(HSC) Medicine - Infectious Disease`), with the exact-count stop condition and PMID-gap reporting. Oncology deferred to its own ADR as a held-out transfer corpus.
- **Labeling:** P1-11 and its agreement step are complete (independent second labeler, 2026-11-16). **P3-01 pilot:** complete with one owner labeler (`Soham`), so inter-labeler agreement is not estimable; the pilot is calibration only, and the owner accepts responsibility for the labels. P3-03 still needs ~3-6 hours of owner labeling.
- **ADR renumbering:** confirm ADR-0008 (scale) and ADR-0009 (Day-0) are the intended final numbers.
- **Local tooling:** no GNU `make` on this host; equivalent Python commands are used. Hook environments must be built with the system **Python 3.12** (`py -3.12 -m pre_commit install --install-hooks`), because the 3.11 venv's base at `D:\` breaks virtualenv; `secret-scan` runs inside a pre-commit env, so it no longer depends on the host's broken bare `python`. `py -3.12 -m pre_commit run --all-files` passes every hook; CI uses Ubuntu. See `docs/LOCAL_SETUP.md`.
- **Provider SDK adapters:** the approved Groq adapter is `src/axion/llm/groq.py` (`groq==1.7.0`); Gemini/Anthropic remain deferred. Offline tests still use the scripted provider.

## Blocked tasks
- ✅ P1-10: closed 2026-11-15 — measured baseline 100 papers / 765 claims on `gemini-3.5-flash-lite`, $0 real spend.
- ✅ P1-11: closed 2026-11-16 — independent 40-claim overlap labelled; raw agreement 100%, κ not estimable (all one class; no `NOT_A_CLAIM` rows).
- ✅ P1-12: closed 2026-11-16 — gate report and audit report regenerated with the agreement result.
- P3-03: owner labeling (later phase).

## Session log (newest first)
### 2026-11-20 — Buffy — oracle answered: the right source sentence does not help v3
- **Ran the oracle** (owner's command, 22 requests, 6.4 s/request, 0 errors): positives caught at 30 went **6 of 11 → 6 of 11**, negatives fired **2 of 11 → 2 of 11**. **18 of 22 scores were identical.** Four moved (P3W1-007 50→92, P3W2-068 33→58, P3W1-058 25→33, P3W2-052 33→25) and the two threshold crossings **cancelled each other**, so the net counts are flat while a gain and a loss hide inside them — named in the report rather than netted away.
- **Cost from the ledger:** 22 attempts, 0 errors, 0 cache hits, 15,368 prompt + 1,808 completion, **$0.009129** list price on the free tier (estimate $0.010718, so the projection held within 15%).
- **P3-06 closes as a negative.** ADR-0027 Amendment A's rule applied literally: no movement means link quality is not the ceiling, so **the linker is not built** (Amendment B). ADR-0026 Amendment C stands; effort moves to P3-07.
- **What it does not say:** nothing about links in general, and at n=11 positives a single crossing either way is the whole difference. One gold positive (`P3W1-063`) was answered `none` — the owner found no supporting sentence in the full body, which is evidence about the label.

### 2026-11-20 — Buffy — oracle labels in; two pre-spend bugs caught
- **Owner labelled the 30-row oracle packet** (labeler `soham`): 30/30, **22 chose a sentence**, **8 said none**, every pick inside its own candidate list. The file came back as `chosen_candidate`/`decision_cue` with `0` for none.
- **My first check said "0 answered" and was wrong** — it read the page's column names, not the file's. The labels were complete. Corrected in the same session rather than trusted.
- **Two bugs fixed before any quota was spent:** the six `0` rows fell into the treatment arm with an **empty claim block** (six paid requests about nothing, then compared as if they were the oracle); and the before-scores path pointed at a file inside the wrong folder, so a live run would have **crashed after paying**. `interpret()` now reads either schema and treats `0` as none, `oracle_arm()` refuses an empty pick that is not a none answer, and the before-scores path is `eval/audit/p3-05/p3-05-llm-v3-dev.csv`.
- **Oracle armed, not fired:** 22 requests, 13,726 prompt tokens, **$0.010718** list price, free tier, stage `dependency_llm_oracle`. The live run is the owner's to start; no agent spends the quota.

### 2026-11-20 — Buffy — P3-06 packet built as an oracle test; linker still gated
- **Option B held:** test not evaluated, spec `6612eae9cbf24a60`, `test_evaluated: false`, no v3b, no extra rows, no live calls this session.
- **Built the oracle packet** (`scripts/p3_06_link_oracle_packet.py`, 15 tests): **30 rows** = all **14** text-bearing dev positives + **16** negatives, seed `20261120`, stratified by section; packet hash `511b788c48d6c502`. Blind labeler shows the citing sentence, the paragraph and up to **40 body sentences**; gold labels and the id map sit in a **separate manifest** the labeler never opens.
- **Two positives cannot be tested:** `P3W2-018` and `P3W2-023` have no source body text (retracted before the body could be parsed). They stay in the packet, marked, and the treatment arm is at most **28**.
- **Overlap under the Amendment C protocol:** **10 rows** (5 positives, 5 negatives) in `eval/audit/p3-06-oracle-labeler2/` — blind files only, no manifest, no first-labeler output.
- **Oracle planned, not run** (`scripts/p3_06_oracle.py`): `--mode estimate` bounds the arm at **28 requests**, **16,643** prompt tokens at the median candidate, **$0.013393-$0.014127** list price, stage `dependency_llm_oracle`. Quota at build time **127 of 450** on the Pacific day. `--mode live` refuses without a complete, named label file and refuses ids outside the packet.
- **ADR-0027 Amendment A (Proposed, no approval):** the packet is an **oracle test**, and linker code is **gated on the oracle outcome** with a pre-committed rule — larger positive count with no rise in negatives fired licenses a linker proposal; no movement kills the linker and leaves ADR-0026 Amendment C as the answer. Reading pre-registered: positives caught before vs after as raw counts out of 14, FAR *direction* on the 16 negatives, per-row vs heuristic, **no interval, no superiority claim, direction only at n=30**.
- **Labelling time is an estimate, not a measurement:** 38 s/row was the P3-05 pace on one-sentence contexts; this shows up to 40 source sentences, so **75-120 s/row**, i.e. **35-60 minutes** for 30 rows. Flagged as an estimate in the packet README.

### 2026-11-20 — Buffy — option B: P3-05 closed as a dev-negative, P3-06 diagnosed
- **Owner decision: option B.** Test is **not** evaluated and is not scheduled; spec `6612eae9cbf24a60` stays frozen with `test_evaluated: false`; v3b is not run (variant budget closed at 2 of 3); the last 3 rows stay unscored.
- **P3-05 dev-negative recorded (ADR-0026 Amendment C)** — cascade promoted as a **high-precision operating-point alternative**: at matched 50% recall, v3 FAR 12.2% [7.2, 19.7] vs v2 23.2% [16.2, 31.9], while the heuristic keeps R 85.7% [60.1, 96.0] at FAR 43.0% [34.0, 52.5]. Denominator **148/151** with `P3W1-041`, `P3W1-042`, `P3W2-054` named as provider failures.
- **P3-06 started with a diagnosis, not code** (`scripts/p3_06_linking_diagnosis.py`, 7 tests, no calls, dev only): body text exists for **115/151** dev rows; for the **93** rows carrying the abstract proxy, a body sentence matches clearly better **64/93 = 68.8% [58.8, 77.3]** — the proxy is often not the sentence the citation is about. The two positives the cascade ceiling drops (`P3W1-014`, `P3W1-034`) both sit at weak best coverage (0.25 / 0.22). v3 catches **7/12 [31.9, 80.7]** of positives with a pointer, **0/2** without.
- **A deterministic rule was swept, not picked:** 12 settings move accept from **3.3%** to **24.5%** and escalation from **96.7%** to **75.5%**, with accepted positives 1/16 to 4/16. Every cell is unvalidated, which is exactly why **ADR-0027 (Proposed)** puts a **30-row owner-labelled link gold set** before any linker code and forbids LLM calls until the plan is approved.
- **P3 gate stays open.** What a test look would tell us and would not: recorded in the summary, not in a claim.

### 2026-11-20 — Buffy — v3 measured on dev: graded, still not good enough
- **The resume worked.** 148 of 151 dev rows scored. `P3W1-018` — the row that failed 6 times before — **went through on its second attempt** in the new loop (fail 06:01:06, ok 06:01:19), which confirms it was transport flakiness, not content. Three different rows failed instead (`P3W1-041`, `P3W1-042`, `P3W2-054`), all SSL `ReadError`, and `--max-calls 134` was consumed exactly by the first pass so the retry pass never ran on them. My arithmetic: 134 rows meant 134 calls meant no headroom for retries.
- **v3 is graded** — the thing v2 failed: bands 0-20 **37**, 21-40 **103**, 41-60 **7**, 61-80 **1**, 81-100 **0**; interior share **75%**, 8 distinct scores.
- **Graded, but compressed at the bottom**, so discrimination is worse than v2 at high recall: threshold 20 → R 100% at **FAR 78.5%**; 30 → R 50% at FAR 12.2%; 40/50 → R 21.4% at 4.7%; 60/70 → R 7.1% at 0.0%. **No threshold holds R ≥ 0.80 at FAR < 42.6%**, and the 3 missing rows cannot change that (removing every missing negative still leaves ~77% FAR at the recall-0.80 point).
- **ADR-0026 Amendment C applied as pre-committed:** *"LLM verification stage did not beat the heuristic on dev; cascade reported as a high-precision operating-point alternative."* Spec stays **`6612eae9cbf24a60`**. **v3b not run** — permitted only if v3 were ungraded. Variant budget closes at **2 of 3**.
- **Two report bugs found and fixed while checking:** the flagged path computed v3's metrics but never rendered them (only the banner appeared), and it re-tuned the heuristic on the 148-row subset — which moved the baseline from R 85.7%/FAR 42.6% to R 50%/FAR 21.5% and would have flattered v3 by comparison. The heuristic is now tuned on the full dev frame and merely *applied* to the scored rows, and `heuristic_params` is returned so a test can assert it.
- Genuine internal win worth recording: v3 dominates v2 at matched recall (50% at 12.2% FAR vs 50% at 23.2%).

### 2026-11-19 — Buffy — resume #2 cost 3 requests and died on the row that always dies; loop rewritten
- **Every resume since the first one has been stopped by `P3W1-018`.** Resume #2 (10:57:48–10:58:05) spent **3 requests, all on that row, all `ReadError: SSLV3_ALERT_BAD_RECORD_MAC`, 0 tokens, $0**. Six attempts on that one row now, across three invocations, and the checkpoint has not moved off 17.
- **The row is not special by size.** Its v3 prompt is **2,731 chars / ~683 est tokens**, inside the range of the rows that succeeded (606–783 actual, median 647); two larger requests went through. Pure ASCII, a typical 477-char discussion sentence, no source claim (abstract only). **v2 answered it fine** at 08:52 (549 prompt tokens, 35 completion, score 10), so payload size and content are excluded as the obvious cause. The failure is transport-level and row-sticky; cause **unproven**, stated as such.
- **Root cause of the crash: the except clause caught `ProviderError` subtypes, but the client wraps an exhausted retry policy in `AllProvidersFailedError`, which is a plain `LLMError`.** It escaped as a raw traceback, exactly as reported.
- **Rewritten loop (`score_rows`)**: any `LLMError` except `ConfigurationError` is recorded and the run **continues**; one retry pass at the end; failures land in `p3-05-llm-{variant}-dev-failures.csv` with row id, error class, attempts and timestamp. `DailyQuotaError` still stops everything, and the daily cap and call cap still bind. Rows that keep failing stay **unscored** — no imputation, no silent drop.
- **Metrics gate**: refusal stays the default. `--allow-incomplete-metrics` is the only way to see partial numbers, and it prints the scored/frame denominators, names every unscored row, and states they failed at the provider and are not missing at random.
- **Self-inflicted mess, disclosed:** two test runs before the path was fixed appended **10 junk rows (`p0`–`p3`)** to `eval/audit/p3-05/p3-05-llm-v3-dev.csv`. `score_rows` now takes an explicit `checkpoint_path`, so a test cannot write to the real artefact again. Both `git checkout --` and a scripted rewrite were refused by the tool policy, so **the working tree still has those 10 junk rows and the owner needs to discard them**: `git checkout -- eval/audit/p3-05/p3-05-llm-v3-dev.csv`.

### 2026-11-19 — Buffy — the resume never ran: checkpoint still 17/151, guard fixed
- **The CSV is unchanged at 17 of 151 rows.** The resume made **zero requests**: the ledger has nothing after `2026-11-19T10:16:26`. My provider-window guard refused to start because it counted *any* failure among the last three attempts — the three SSL `ReadError`s on `P3W1-018` — and would have refused forever, since those rows never leave the ledger.
- **Fixed (`provider_window`)**: blocked only when the most recent attempt failed *inside* a 300s cooldown. Same ledger at 10:17 → blocked; now (34 minutes later) → `blocked: False`, with the reason printed. Estimate, budget, daily-cap and quota checks untouched.
- **Ledger reconciled to the checkpoint**: 23 attempts = **18 succeeded + 5 failed**, 0 cache hits, **12,661 prompt + 1,556 completion tokens, $0.007688**; the 17 unique successful rows are exactly the 17 checkpoint rows (no ok-but-unscored, no scored-but-not-ok). The 18th success is the discarded `P3W1-001` attempt from my schema bug.
- **v3 cost vs estimate: +18.4% per row.** Actual **744.8 prompt / 91.5 completion tokens, $0.000452 per row** against the stated 606.4 / 80.0 / $0.000382. Projected over the full 151 rows that is **112,459 + 13,821 tokens ≈ $0.068290**, not $0.057671 — the longer two-judgement answers cost more per row, as the prompt length implies.
- **No v3 metric, so no ADR-0026 decision.** Not re-frozen, and the dev-negative was **not** written: writing it now would report a result that does not exist. Amendment B records the status only.
- Next: 134 rows needed, 273 of 450 requests left today.

### 2026-11-19 — Buffy — v3 partial run (17/151), recovery from a transport failure and an inverter bug
- The owner ran the v3 dev command. **First run: 17 rows scored, then P3W1-018 failed 3 times on `ReadError: [SSL: SSLV3_ALERT_BAD_RECORD_MAC]`** (all three attempts are in the ledger, no tokens, $0). **Rerun: crashed in dev_metrics with `BaselineError: no prediction for P3W1-018` before making a single call** — my bug: `variant_metrics` was computed on the partial checkpoint at startup.
- **Checkpoint: 17 of 151 dev rows** (`P3W1-001`..`P3W1-017`), 0 blanks, 17 distinct ids, all `p3-05-llm-v3`. **Missing 134**, of which exactly one (`P3W1-018`) was ever attempted; the other 133 were never reached.
- **Ledger `dependency_llm_v3`: 23 attempts = 18 succeeded + 5 failed**, 0 cache hits, **12,661 prompt + 1,556 completion tokens, $0.007688 list price**. The 5 failures: 1 `structured_output` parse (my schema bug, 09:53), 1 `TransientProviderError` 503 on `P3W1-015` (recovered on retry), **3 `ReadError` SSL on `P3W1-018`** (no tokens, $0).
- **Fixed (`IncompleteCheckpoint`)**: metrics now refuse a partial checkpoint and print exactly `incomplete: 17 of 151 dev rows scored, run again to resume`, exit code 2. Nothing is imputed and no row is dropped: the missing rows are provider failures, not a random sample. A provider failure inside the loop now ends the run cleanly with `stopped_reason: provider_error: ...` instead of throwing away the rows already paid for.
- **Still to regenerate:** the report body. The environment refused to run the script again (off mode included), so `docs/reports/P3-05-llm-v2-calibration.md` keeps its previous generated body and the new incomplete/ledger section is proven by a test instead. Regenerate with `--variant v3` (off) once the run resumes.

### 2026-11-19 — Buffy — prompt v3 built and costed; live run blocked by the environment
- **Owner decision: option 1, capped** — build v3 on dev only, at most two variants beyond v2, log every variant, and only supersede the frozen spec if a variant reaches **recall >= 0.80 at FAR < 42.6%**. Test still **not evaluated**; silver plan still **NO-GO**.
- **v3 built**: two separate ordinal judgements (B's use of A's **result**, 0-3; B's use of A's **method**, 0-3), each with its own evidence quote, combined 3:1 into a 0-100 score (16 level pairs -> 13 distinct scores). **v3b built** as the single permitted fallback: a fact checklist weighted into a graded score, for the case where v3 still answers at the extremes.
- **The v2 problem is now quantified in the variant log**: 110 rows in 0-20, **1 row in 21-40**, 0 in 41-60, 0 in 61-80, 40 in 81-100 -> interior share **0.7%**, and the log records `graded: no`. The 30/70 split I reported earlier hid that single row; the 20-point bands show it and still refuse to call it a scale.
- **Cost stated before any live call** (dry-run over the 151 dev rows): v3 **91,569 prompt tokens, $0.057671** list; v3b **68,991 prompt tokens, $0.050897** list; both $0 real on the free tier. Quota at the time: **154/450** requests used today, **296** left, so v3 (151) fits and v3b (151) **would not** fit in the same Pacific day.
- **Two calls were paid for and produced nothing: $0.000758.** My own bug, twice: first the request pinned v2's answer schema while the v3 prompt asked for different fields; then the request was right but the client was still told to parse v2's model. Fixed by making the variant own the prompt, the request schema and the parse model (`build_request`), with a test asserting they travel together. Both failures are printed in the calibration report under "Calls paid for that produced no scored row", not netted out.
- **Then the environment refused further live calls** for v3 ("latest authorization covers v2, not v3"). I stopped there rather than work around it. **No v3 score exists**, so there is no v3 recall, no v3 FAR and no re-freeze: the spec stays **`6612eae9cbf24a60`**.
- ADR-0026 gained **Amendment A** recording the cap, the logging rule and the unchanged decision rule, written before any v3 score exists.

### 2026-11-19 — Buffy — v2 dev scores in; stage-2 tuned; spec re-frozen before any test look
- The owner authorised the dev-only v2 run and the checkpoint exists: `eval/audit/p3-05/p3-05-llm-v2-dev.csv`, **151/151 dev rows**, scores 0-100, mean 28.5, prompt `p3-05-llm-v2`.
- **Score distribution is nearly binary:** 111 rows <= 30, **0 rows between 31 and 69**, 40 rows >= 70. Every threshold from 31 to 80 therefore behaves identically; the model is expressing a decision, not a calibrated probability.
- **v2 on dev, text-bearing frame (14 positives):** P 21.9%, **R 50.0% [26.8, 73.2]**, **FAR 23.2% [16.2, 31.9]**. For comparison on the same rows: v1 R 14.3% [4.0, 39.9] / FAR 7.4% [3.8, 13.9]; heuristic **R 85.7% [60.1, 96.0] / FAR 42.6% [33.7, 52.0]**. v2 raises recall 4x over v1 but does not approach the heuristic's recall, and pays for its precision with 23% false alarms.
- **Stage-2 threshold tuned on dev only → 70.0, and it does NOT hold the pre-registered 0.80 recall floor:** the best the cascade reaches on dev is 50% recall (all thresholds 31-80 tie at 50.0% recall / 11.1% FAR; 90 gives 43.8% / 8.2%). The tuner now reports `meets_floor: false` and falls back to max-recall rather than raising or pretending.
- **Staged cascade on dev (text-bearing):** P 31.6%, **R 42.9% [21.4, 67.4], FAR 12.0%** — it trades recall for false alarms instead of dominating the heuristic. Per ADR-0026 that is recorded as **no superiority claim**, not spun as a precision win.
- **Cost reconciled against the real ledger:** run `p3-05-llm-v2-2026-11-19` = **154 attempts** (151 succeeded, 3 errored, 2 cache hits), 71,359 prompt + 5,948 completion tokens, **$0.036276** list price. Pre-run estimate was 72,283 prompt (**-1.3%**) and 12,080 completion (**-50.8%**), so the estimate overshot the price by **$0.0156 (-30%)**: output tokens were over-estimated ~2x. Per-context cost now uses the ledger: **$0.000108**; **$0.00232 per retraction**; corpus projection $0.63 list price.
- **New frozen spec `6612eae9cbf24a60`** (`test_evaluated: false`, history records the replaced `b85dc5d5c94eb375` and why). **Test has not been looked at**; evaluation still requires the owner's go.
- **Silver plan remains NO-GO** per the owner: v2 is not yet validated on dev (50% recall at 23% FAR is not validation).

### 2026-11-19 — Buffy — P3-05 pre-registered, diagnosed, staged and costed; live stage-2 blocked
- **ADR-0026 (Proposed)** fixed the comparison before any detector existed: citation-level is a scale reference, not an opponent; primary comparison is the staged detector vs the dev-tuned heuristic at recall >= 0.80 on the text-bearing test frame plus cost per context; intervals decide superiority; stubs separate; and the 61-row zero-discordance overlap is recorded as **no evidence about borderline rows**.
- **LLM v1 diagnosis (dev, 151 rows, no calls):** v1 flagged `RELIES_ON` on 12 rows — recall 4/16 = 25.0% [10.2, 49.5], FAR 8/135 = 5.9% [3.0, 11.3], zero parse failures. A's text was available for 122/151 rows (93 claim, 29 abstract-only), absent only for the 29 stubs, so missing context does not explain it. The defect was the question shape: a three-way label with no confidence left nothing to tune or escalate. **Prompt v2** asks only the counterfactual and returns a 0-100 score plus the phrase that would change.
- **Cost stated before any v2 call:** 151 dev rows, 72,283 prompt + 12,080 completion tokens (heuristic), list price **$0.0519**, free tier. **The live run was refused twice by this environment's tool policy** and no smoke call was made, so **no v2 score exists and no stage-2 number is reported**. The command is in `docs/reports/P3-05-llm-v2-calibration.md`, writes a resumable checkpoint, and refuses over budget, over the daily cap, or in a failing provider window.
- **Staged detector (dev, deterministic parts only):** the obvious design — stage 1 rejects easy negatives — was **rejected on evidence**: it cannot clear negatives without either dropping a positive or escalating 25-50% of rows, and its positive calls are less precise than the heuristic's (FAR 65%). Final shape: stage 1 is the **recall stage** (candidate threshold 0.0, e = 68/151 = **45.0%**, ceiling 14 of 16 positives), stage 2 verifies candidates. No staged number is printed without stage 2, because without it the cascade *is* the heuristic.
- **Scheduler (P3-05b, dev):** risk = linkage (+1.0), retraction mention (+0.5), heuristic score. Recall reached: 12.5% [3.5, 36.0] at top 10%, 43.8% [23.1, 66.8] at 20-25%, 68.8% [44.4, 85.8] at 50%. Weights are design choices, not fitted; the 10% point rests on 2 positives.
- **P3-08 scaffold:** e = 45.0%, **$0.000115 per context**, **$0.00247 per retraction analysed** at list price; corpus projection **$0.71** / 2,754.5 requests / 6.1 free-tier days — labelled PROJECTED with assumptions (285 of 792 sources, 6,117 contexts). `s` is **not applicable**: no student exists, so no number is invented.
- **Silver plan (sizing only, nothing run):** **2,908 eligible contexts** of 6,117 after excluding all 300 gold rows and all 2,909 remaining test-source contexts (whole sources, not just sampled rows); 705,225 prompt + 232,640 completion tokens (heuristic), **$0.793** list price, 6.5 free-tier days.
- **Freeze:** spec `b85dc5d5c94eb375` frozen with `test_evaluated: false`. **Test was not evaluated**: `--evaluate-test` refuses in code, and the one legitimate test look is deferred until the stage-2 scores exist and the stage-2 threshold is tuned on dev (re-freeze allowed only while test is unseen, recorded in `history`).
- **Blocked:** the live dev v2 run. Nothing else in this block is blocked.

### 2026-11-18 — Buffy — wave-2 agreement under Amendment C; ADR-0025 decided (narrow, no wave 3)
- `scripts/dependency_agreement.py --wave wave2` (+ 5 tests, 15 in the module): blinded-subset check, raw agreement, κ, PABAK, design-weighted κ, **negative-side κ**, off-diagonal count, and an isolation audit that reads the repo rather than asserting the rule.
- **Result: 30/30 = 100%, κ 1.000, PABAK 1.000, design-weighted κ 1.000 — degenerate again (zero discordant pairs).** Negative side is now estimable (18 rows, floor 15): **negative-class κ 1.000**, labeler 2 keeps the row negative **18/18 = 100% [82.4%, 100%]**, calls none of them `RELIES_ON`.
- Matrix is purely diagonal: 12 `RELIES_ON`, 9 `MENTIONS`, 9 `UNRELATED`, 0 skipped. The report says what that does and does not say: the partition is reproducible, but there is **no evidence about the ambiguous boundary**, and κ still cannot separate genuine reliability from a shared rubric reading or a shared heuristic.
- **Isolation audit, all pass:** distinct labeler ids (`Soham` vs `friend`); the export sits in the declared `eval/audit/p3-03-labeler2/` handoff directory; that directory holds only the blind CSV, labeler HTML and README (no labeler-1 export, manifest or selection file); the export's columns match the blind schema (no weights/strata/split/cue). Pace 38 s/row vs 120 s/row is consistent with two people but recorded as **weak** corroboration, since the owner reported it and the script cannot measure it.
- **ADR-0025 accepted with the narrowing option: no wave 3.** The gate becomes a measured recall with its interval plus the false-alarm reduction against the citation-level floor; the 0.70/0.80 recall floor may only be claimed if the interval supports it. Wave-3 rows stay recorded as a priced option, unscheduled.
- Next: P3-05 staged detector, with the frozen P3-04 baselines as the floor to beat.

### 2026-11-18 — Buffy — P3-04 baselines measured and frozen; ADR-0025 Proposed
- `scripts/dependency_baselines.py` (+ `tests/test_dependency_baselines.py`, 8 tests) scores citation-level, section/lexical heuristic and LLM-only on the 300 labelled rows: dev/test separately, weighted and unweighted, Wilson CIs, text-bearing (232) and stub (68) frames separate.
- Heuristic tuned on **dev only** (30-point grid recorded in the JSON). **Test computed once and frozen** (`eval/audit/p3-04/p3-04-test-frozen.json`, spec `21faf8c921c32fb8`); a later run recomputes and refuses if any frozen number or the spec moved, and a baseline added afterwards is stamped `added_at` rather than overwriting.
- **Text-bearing test, 18 positives:** citation-level P 16.4% / R 100% / FAR 100%; heuristic P 30.0% / R 83.3% [60.8, 94.2] / FAR 38.0% [28.8, 48.2]; LLM-only P 75.0% / R 16.7% [5.8, 39.2] / FAR 1.1%. **21 test positives overall** — the report states plainly that any recall claim has a wide interval.
- **LLM-only cost, stated before the call:** 300 rows, ~96k prompt + 18k completion tokens (heuristic token count), list price **$0.0739**, billing free tier. Ran live after a 3-call smoke: **300/300 rows, $0 real spend**, ledger run `p3-04-llm-2026-11-18`. 0 of 450 daily requests were used before the run.
- **ADR-0025 (Proposed):** a wave 3, if drawn, is test-split sources only, uniform, from the 2,909-context test pool (π = rows/2,909, weight 1/π, cap 8/source). Reaching 40 test positives needs **238 rows at 8.0%** (2 h 31 min at 38 s/row) or **121 at 15.8%** (1 h 17 min); 77 needs **700** (7 h 23 min) or **355** (3 h 45 min). The alternative — narrow the gate to a recall interval plus the false-alarm contrast — costs no labeling time and is the default.
- Next: owner reads P3-04 and decides wave 3 vs narrowing the claim; the wave-2 overlap agreement report follows when the export is handed over.

### 2026-11-18 — Buffy — wave-2 labels received; overlap built; stop rule applied
- Owner returned `eval/audit/p3-03/dependency_audit_v1_wave2_labelled.csv`: **150/150 rows, 0 blanks, 150 notes**, **12 `RELIES_ON` / 129 `MENTIONS` / 9 `UNRELATED`** (labeler field `soham`, normalised to `Soham` per the standing rule). **Measured pace: 1 h 35 min = 95 min for 150 rows = 38 s/row** — inside the 20–45 s assumption, upper half.
- **Wave 2 came in under target:** 8.0% positives, not ~35 (23.3%). Combined: **37 positives / 300 rows**. Uniform base rate now heterogeneous — wave 1 7/30 = 23.3% [11.8, 40.9] vs wave 2 12/150 = 8.0% [4.6, 13.5]; pooled design-weighted 15.8% [10.3, 24.9], pooled unweighted 10.6%. Recorded as provisional, with no homogeneity test claimed.
- **Stop rule applied:** 77 positives needed for a 0.70 lower bound at 0.80 observed recall, so 40 outstanding — 254 / 379 / 500 more rows depending on which rate you use. Positives per split: dev 16/151, test 21/149.
- **Overlap built under Amendment C:** `--overlap-wave wave2 --overlap-blind-dir eval/audit/p3-03-labeler2 --overlap-min-negatives 15` → **30 rows = 12 `RELIES_ON` + 18 negatives** (9 `MENTIONS`, 9 `UNRELATED`), floor met; handoff directory holds only the blind CSV, the labeler HTML and a README (no labeler-1 file, no manifest, no selection counts).
- Files: `docs/reports/P3-03-wave1-wave2-metrics.md`, `eval/audit/p3-03/p3-03-combined-metrics.json`, `eval/audit/p3-03-labeler2/*`, `eval/audit/p3-03/p3-03-wave2-overlap2-selection.json`.
- Next: **second labeler labels `p3-03-wave2-overlap2-labeler.html`**; then agreement under Amendment C, then P3-04 baselines.

### 2026-11-18 — Buffy — wave-2 packet built; combined metrics added
- `scripts/dependency_wave2.py` (+ `tests/test_dependency_wave2.py`, 7 tests) draws wave 2 and writes `p3-03-wave2-{blind.csv,manifest.csv,labeler.html,sampling.json}` plus `docs/reports/P3-03-wave2-packet.md`.
- **Measured (seed `20261220`):** 150 rows from the 5,967-context pool, π = 0.02513826, weight **39.78**, cap 8/source with **5 sources truncated**, **78 dev / 72 test** rows over 34 / 37 sources, **0 contexts shared with wave 1**, linked 63.3%, **116 text-bearing / 34 stub**.
- The blind CSV and labeler carry no weights, strata, cues or split; the separate manifest does.
- `scripts/dependency_metrics.py` now also writes the **combined wave 1 + wave 2 report** (`docs/reports/P3-03-wave1-wave2-metrics.md`, `eval/audit/p3-03/p3-03-combined-metrics.json`): counts per wave and combined, the updated weighted base rate over all uniform rows with a Wilson interval, positives per split, and the ADR-0024 stop-rule numbers (77 needed, extra rows at the updated rate). It self-skips with a printed note until the wave-2 labels exist.
- Next: **owner labels wave 2** (`p3-03-wave2-labeler.html`), returns `dependency_audit_v1_wave2_labelled.csv`; then the overlap is built from that export under Amendment C.

### 2026-11-18 — Buffy — ADR-0024 Proposed: uniform-only wave 2
- Owner accepted wave 2 = **150 rows, uniform only**, drawn from the remaining pool with equal inclusion probability, same per-source handling as ADR-0023's uniform frame, split inherited from the frozen source assignment, cues not used as filter or stratum. Recorded as **ADR-0024 (Proposed)** with the 77-positive target and the stop rule.
- Rule and weights: pool **5,967** contexts (6,117 − 150), π = 150/5,967 = **0.025137**, weight **39.78**, cap **8 rows/source**; truncated sources listed in the wave-2 report.
- Stop rule: after wave 2 the metrics script reports **positives per split**, the **updated weighted base rate with a Wilson interval**, and the **extra rows still needed for the 0.80 case** (77 positives). A shortfall is reported instead of starting wave 3.
- Wave 1 is not redrawn; no overlap file is built until the owner's wave-2 labels return (Amendment C applies).
- Next: build the wave-2 packet, then extend the metrics script with the combined wave-1 + wave-2 report.

### 2026-11-18 — Buffy — Amendment C: overlap isolation and negative floor
- ADR-0023 gained **Amendment C** (owner instruction): from wave 2 the labeler-1 export is never shared with labeler 2 (blind HTML/CSV only), the returned export is checked against the blinded subset, and an overlap needs **≥15 negative rows** or the report declares negative-side κ not estimable.
- Wave 1 is recorded as **not meeting the isolation rule** (its export sat in `eval/audit/p3-03/` beside labeler 2's packet), so its 31/31 agreement stays consistency only; the owner declined the test-retest for now.
- Enforcement is in code, not prose: `scripts/dependency_agreement.py` now carries `NEGATIVE_FLOOR = 15`, records `negative_side_estimable` in the JSON, and prints a **Protocol checks** section stating the blinded-subset check, the negative floor and the isolation failure.
- Files: `docs/DECISIONS.md` (Amendment C), `docs/reports/P3-03-agreement.md`, `eval/audit/p3-03/p3-03-agreement.json`, `tests/test_dependency_agreement.py`.
- Next: wave-2 decision (owner) and P3-04 baselines.

### 2026-11-18 — Buffy — wave-1 metrics measured
- New `scripts/dependency_metrics.py` (+ `tests/test_dependency_metrics.py`, 7 tests) reports class counts overall and by frame/split, the design-weighted uniform base rate, the Amendment B frames, the cue-enrichment comparison, the positives-needed table and a wave-2 recommendation.
- **Counts (150 rows):** 25 `RELIES_ON` / 120 `MENTIONS` / 5 `UNRELATED` / 0 `insufficient_context`. Uniform 30: 7/22/1. Enriched 120: 18/98/4. dev 73: 13/58/2. test 77: 12/62/3. Text-bearing 116: 22/92/2. Stub stratum 34: 3/28/3.
- **Base rate:** uniform **7/30 = 23.3%** (Wilson 95% 11.8-40.9%); enriched **18/120 = 15.0%** (9.7-22.5%). **No measured cue lift** - the enriched point estimate is *lower* than the uniform one and the intervals overlap, so the cues stay unvalidated and cannot be used as a positive filter. 72% of positives sit in the enriched frame, which is 80% of the rows.
- **Correction:** the stub stratum has **3 `RELIES_ON` of 34**, so Amendment B's assumption that stubs are near-certain negatives is withdrawn (the citing sentence alone sometimes decides it). The stratum stays separate and stays in the weighted base rate.
- **Plan (computed):** 30 positives clears a 0.70 lower bound at observed recall 0.85 (we have 25, so ~5 more, ~22 uniform rows); 77 positives clears it at 0.80 observed (+52, ~223 uniform rows).
- Files: `docs/reports/P3-03-wave1-metrics.md`, `eval/audit/p3-03/p3-03-wave1-metrics.json`. No LLM calls, $0.
- Next: wave-2 frame/size decision (owner) and P3-04 baselines.

### 2026-11-18 — Buffy — second labeler returned; agreement reported
- Owner supplied `eval/audit/p3-03/dependency_audit_v1_wave1_overlap2_labelled.csv`: 31/31 rows, labeler `friend`, a note on every row, no blanks. The row set matches the selection file exactly (the script rejects anything else).
- New `scripts/dependency_agreement.py` (tests: `tests/test_dependency_agreement.py`, 10 tests) validates both exports, confirms the overlap is the blinded subset, and reports raw agreement, Cohen's κ (bootstrap), PABAK, design-weighted κ, the confusion matrix and the disagreement list.
- **Measured:** raw agreement **31/31 = 100%**; κ **1.000**, PABAK 1.000, design-weighted κ 1.000; 25 `RELIES_ON` / 3 `MENTIONS` / 3 `UNRELATED` both sides. **κ is degenerate** (zero discordant pairs → bootstrap interval is the point 1.00), so it is recorded as *consistency, not established reliability*: it cannot separate real rubric reliability from a shared cue heuristic or from labeler 2 having seen labeler 1's labels. A blind test-retest subset is the cheap discriminator; the 6 negative rows are the fragile side.
- Files: `docs/reports/P3-03-agreement.md`, `eval/audit/p3-03/p3-03-agreement.json`. No LLM calls, $0, no labels created by the agent.
- State: branch `p3`; P3-03 `[~]` — wave-1 weighted/unweighted rates and the 116-row text-bearing vs 34-stub reporting split are still to be computed.
- Next: write the wave-1 metrics script (weighted and unweighted rates, Amendment B frames), then P3-04 baselines.

### 2026-11-18 — Buffy — wave-1 labels received; overlap 2 built
- Owner returned `eval/audit/p3-03/dependency_audit_v1_wave1_labelled.csv`: **150/150 rows, 0 blank labels, 150 notes**; **25 `RELIES_ON` / 120 `MENTIONS` / 5 `UNRELATED` / 0 `insufficient_context`**. The `labeler` column is **`Soham`**: the first return carried the mis-set id string `Muse-agent` and was corrected on the owner's instruction (2026-11-18), with the pre-correction export retained in `bbcd377`. Labeler identity is recorded as `Soham` from here on; **the agent created no label**.
- Ran `python scripts/dependency_sample.py --build-overlap eval/audit/p3-03/dependency_audit_v1_wave1_labelled.csv` → **31 rows** = 25 `RELIES_ON` + 3 `MENTIONS` + 3 `UNRELATED` + 0 `insufficient_context`, **20.7%** of the wave; blind file verified: 31/31 blank label, blank labeler, blank date, no `text_bearing`/`overlap`/`split`/weight columns, all row ids unique, hash-ordered.
- Recorded in ADR-0023 Amendment A: the realised overlap is **81% positive**, so the prevalence effect *depresses* κ (conservative, not inflated), and negative-class agreement rests on 6 rows. The empty `insufficient_context` class leaves a structurally empty row in the four-class matrix.
- Raw label count 25/150 is **not** a rate: the wave is two frames by design, so weighted and unweighted rates come from the metrics script that is still to be written.
- State: branch `p3`; P3-03 `[~]` — second-labeler labels and the metrics/agreement script pending.
- Next: send `eval/audit/p3-03/p3-03-wave1-overlap2-labeler.html` to the second labeler; they return `dependency_audit_v1_wave1_overlap2_labelled.csv`.

### 2026-11-18 — Buffy — P3-03 overlap 2 builder (no labels)
- Did: `scripts/dependency_sample.py --build-overlap <labelled.csv>` implements ADR-0023 Amendment A — validates labeler 1's export (known row ids, exactly one labeler, no blank labels, whole wave covered, labels in the four classes), then writes `p3-03-wave1-overlap2-blind.csv`, `p3-03-wave1-overlap2-labeler.html` and `p3-03-wave1-overlap2-selection.json` (counts and row ids only, never labeler-1 labels).
- Selection: all/nearly all `RELIES_ON` + round-robin across `MENTIONS`, `UNRELATED`, `insufficient_context`; floors are ≥30 rows AND ≥20% of the wave AND ≥6 negatives; blank labeler id; rows ordered by `sha256(seed:ctx_id)` so order leaks nothing. Tests: `tests/test_dependency_sample_overlap.py`, **13 passed**.
- Superseded: the pre-built 30-row overlap keeps its files, gains a visible SUPERSEDED header in the labeler HTML plus `p3-03-wave1-overlap-SUPERSEDED.md`, and is not sent to the second labeler.
- Amendment B in the data: `text_bearing` added to `p3-03-wave1-manifest.csv` **only** (116 text-bearing / 34 stub); no packet row, blind CSV or full labeler changed. Report regenerated text records the pre-registered stratum and the corrected cap wording.
- State: branch `p3`; P3-03 stays `[~]` — blocked on owner labels, not on agent work.
- Next: owner labels `eval/audit/p3-03/p3-03-wave1-labeler.html` and returns `dependency_audit_v1_wave1_labelled.csv`; then run the `--build-overlap` command.

### 2026-11-18 — Buffy — ADR-0023 accepted; CI numpy fix
- Did: ADR-0023 marked **Accepted (2026-11-18)** with two owner amendments. **A:** the pre-built 30-row overlap is superseded; overlap 2 is built from the owner's returned wave-1 labels (all/nearly all `RELIES_ON` + round-robin spread across the other three classes; ≥30 rows and ≥20% of the wave and ≥6 negatives; separate blind file, blank labeler id, hash-ordered) and κ is reported as conditioned on labeler 1, with the inflation/deflation directions and a corpus-prevalence reweighting. **B:** the 34 title-only stub rows stay in the gold file and the weighted base rate, but become a **pre-registered report-only stratum** — primary precision/recall on the 116-row text-bearing frame (101 linked + 15 with an abstract); `text_bearing` goes in the manifest only, never the labeler payload.
- Cap wording corrected from a replay of the sampler, not from memory: **7 sources truncated by the cap** (all enriched frame), **6 sources hold >8 wave rows in total, max 14**; the cap is applied **per frame**. Fixed in `docs/DECISIONS.md` §2, `docs/reports/P3-03-wave1-packet.md`, this file and the P3 TODO.
- CI: `dev` extra was missing `numpy`, which `src/axion/train/student.py` imports at module level; reproduced the collection failure locally (`ModuleNotFoundError: No module named 'numpy'`, `Interrupted: 1 error during collection`). Fixed by pinning `numpy==2.4.6` in `dev`. The mapping to the GitHub red run is **inferred, not log-confirmed**.
- State: branch `p3`; no push.
- Next: owner labels wave 1 and returns `dependency_audit_v1_wave1_labelled.csv`.

### 2026-11-18 — Buffy — P3-03 wave 1 packet built (no labels)
- Did: claimed P3-03, wrote ADR-0023 (Proposed), built `scripts/dependency_sample.py` and extended the blind labeler (`docs/eval/audit_labeler_template.html`).
- Wave 1, seed `20261119`: **150 rows** = **30 uniform** (π=30/6,117, weight 203.9) + **120 cue-enriched** stratified by section, **cap 8 rows/source applied per frame**: **7 sources truncated by the cap**, all in the enriched frame; **6 sources hold more than 8 wave rows in total, max 14**. Frames are disjoint, so the wave is exactly 150.
- Split fixed by source before any detector: **34 dev / 34 test sources, 3,059 / 3,058 contexts, 73 / 77 wave rows.**
- Linked 101/150 (67.3%); 49 unlinked — 15 with an abstract, 34 with none (retracted/withdrawn stubs) and kept deliberately.
- Overlap **30 rows** (24 enriched + 6 uniform) was pre-built in a separate blind packet; **superseded by ADR-0023 Amendment A** — overlap 2 is built from the owner's returned wave-1 labels instead (files kept, marked superseded, not sent to the second labeler).
- Cues measured on all 6,117 contexts: `we_used` 0.3%, `based_on` 3.5%, `numeric_effect` 2.2%, `comparison` 6.5%, `method_word` 3.7%, `inference_connector` 3.0%, `prior_finding` 1.0% → pool 1,080. A bare-digit cue fired on **99.8%** and was rejected after measuring it.
- **Risk stated plainly:** no cue fires on either pilot `RELIES_ON` row, so expected positives are **~3** (pilot reading) to **~21** (15% lift). Wave 1 measures the cues; if lift ≈ 0, wave 2 is uniform-heavy.
- State: branch `p3`; ruff/format/mypy clean, `pytest -q` **380 passed / 2 skipped**; no LLM calls; **$0**; **no labels created**.
- Next: owner labels wave 1 and returns the export; then metrics/agreement, then the wave-2 decision. **Not done until labels exist.**

### 2026-11-18 — Buffy — P3-02 candidate generator complete
- Did: P3-02 finished after the previous agent was cut off mid-lint. Fixed the test that could never match its own wrapped XML fixture (`re.sub` needed `DOTALL`; it had been asserting on a pointer that was still present), cleared the two E501s, reformatted, and committed as `feat(P3-02)` `d00112f`. No duplicated fixture blocks existed in the file.
- State: branch `p3` (not pushed — owner pushes). Neo4j V2 container healthy on `127.0.0.1:7888`; Docker Desktop was off and had to be started.
- Measured: **6,117 candidate contexts, 285 sources with citers, 258 with ≥1 context, 27 at zero, 3,357 citer papers, 3,976 edges with contexts** (both match the P1 manifest exactly, enforced by the script); **214 source-claim proxies → 4,262 linked (69.7%) / 1,855 unlinked**; idempotent on a populated graph (Claim 0→214, everything else unchanged), 0 duplicate `ctx_id`/`pmcid` in Cypher. `pytest -q` **380 passed / 2 skipped**; ruff + mypy clean. No LLM calls, **$0**.
- Planning input for P3-03: pilot RELIES_ON 2/20 = 10.0% [2.8–30.1%]; 17 sources hold 66% of contexts, so sample must be source-capped and stratified; 150 contexts ≈ 15 positives ≈ recall CI ±0.19, so certify with ~600 rather than 150.
- Next: **P3-03 is owner labeling** — do not start. No push, no history rewrite.

### 2026-11-18 — opencode — P3-01 pilot complete; guideline v1.1
- Received `eval/audit/dependency_pilot_v1_labelled.csv`: **20/20 rows, 20/20 notes, 0 blank labels**; labeler `Soham` (owner responsibility), date `2026-11-18`, guideline `P3-v1`. Labels: **16 MENTIONS (80.0%) / 2 RELIES_ON (10.0%) / 2 UNRELATED (10.0%)**.
- Added `scripts/dependency_pilot_metrics.py`; it validates the packet and generates `docs/reports/P3-01-pilot.md` + `eval/audit/dependency_pilot_v1.summary.json`. Input SHA-256 `cfda288d…`; no labels created by the agent.
- **Agreement:** single labeler, so raw agreement and Cohen's κ are **not estimable**; the pilot is calibration only, not gold or training data. Two rows (`P3P-010`, `P3P-014`) were corrected from `RELIES_ON` to `MENTIONS` during review; the v1.1 rule now says grouped corroboration is `MENTIONS` unless A's result is a premise/input.
- Guideline refined to **v1.1** with the corroboration rule, sole-citation clarification, two edge-case rows, and measured pilot summary. P3-01 `[x]`; next is **P3-02** deterministic candidate generator (no LLM).
- Verification: `ruff` clean, format clean, mypy clean for `src/axion` + the two P3 scripts, `pytest -q` **374 passed / 2 skipped**; real spend **$0**.

### 2026-11-18 — opencode — P3-01 blank-label labeler ready; blocked on owner labels
- Added `paragraph_text` and `source_claim_text` (first substantive abstract sentence; a context proxy, not a linked claim) to the 20-row packet via `scripts/dependency_pilot.py`; all labels remain blank.
- Built `eval/audit/dependency_pilot_labeler.html`: single self-contained HTML, one row at a time, citing sentence + highlighted paragraph + section + source claim proxy, no model output, keys/buttons for `RELIES_ON`/`MENTIONS`/`UNRELATED`/`insufficient_context`, note box, guideline copy/link, progress counter, localStorage autosave, and **Export CSV** with `labeler=Soham` / `date=2026-11-18`.
- A Node DOM harness exercised label selection, notes, pagination, skip export, and CSV columns: **PASS**; 20 rows / 20 sources, 0 labels. No LLM calls, real spend **$0**.
- **State:** P3-01 `[!]`; owner opens the HTML, exports `dependency_pilot_v1_labelled.csv`, and sends it back. Then agreement, guideline v1.1, P3-02.

### 2026-11-18 — opencode — P3-01 guideline and pilot packet; blocked on owner labels
- Claimed P3-01 on `p3`; committed `docs/eval/DEPENDENCY_GUIDELINE.md` v1 with the three labels, counterfactual decision procedure, edge cases, and explicitly **constructed** examples (not corpus labels).
- `scripts/dependency_pilot.py` generated `eval/audit/dependency_pilot_v1.csv`: **20 blank-label rows across 20 source papers**, seed `20261118`; the packet intentionally includes retraction notices, reference-list fragments, and grouped citations. No labels created by the agent.
- Committed as `dafa9dd`; no LLM calls, real spend **$0**. Verification: `ruff check` clean, `ruff format --check` clean, `pytest -q` **374 passed / 2 skipped**.
- **State:** P3-01 `[!]`; P3-02 depends on P3-01 and has not started. Next: owner labels the 20 rows; then compute agreement, refine the guideline to v1.1, and close P3-01.

### 2026-11-18 — opencode — P2 gate accepted and phase closed
- **Owner decision:** accepted **ADR-0021** (two retention numbers + `$/core-section claim`) and **ADR-0022** (operating point `p2-05-length30-v1`). The literal PRD gate is recorded as **PASS** on `escalation-length30`; **56.7% test retention is a stated limitation**, not a silent pass.
- **Config:** `src/axion/config/p2_operating_point.yaml` promoted from `proposed` to `accepted` (decided 2026-11-18); `tests/test_p2_operating_point.py` now asserts `accepted`.
- **Git:** `origin/main` already contained all of `p2` at `cd8f5aa` (PR #1). Local `main` was fast-forwarded, the `p2` branch deleted, and stale "not merged" / "gate review needed" statements corrected in the phase docs.
- **Verification:** `pytest -q` **374 passed / 2 skipped** on `main`; no new LLM calls, real spend **$0**.
- **Next:** P3-01 dependency guideline on branch `p3`.

### 2026-11-17 — Buffy — P2-09 projection, P2-08 lock/report, phase closed for review
- **P2-09:** `scripts/cost_model.py` → `docs/reports/P2-projection.md`. Reads baseline cost/tokens (ledger + ablation), `e`/`s`/stage-1 cost/stage-2 unit (escalation manifest); **no typed-in numbers**. MEASURED and PROJECTED sections separated. At measured `e`=31.1% with stage 2: **20M papers → $56,807 vs baseline $112,892 (−49.7%)**; `e`=5% → $9,408, `e`=50% → $91,096.
- **P2-08:** config initially locked as **proposed** (accepted 2026-11-18) in `src/axion/config/p2_operating_point.yaml` (identifiers only, no measured numbers, so nothing drifts); 5 regression tests assert it matches `escalation.POLICY_VERSION`/`RISK_SIGNAL`/`ESCALATION_FRACTION`, that both stage models are priced, the stage-1 prompt loads, and the projection is deterministic (byte-identical across runs). Phase report `docs/reports/P2-cascade.md` and `docs/phases/P2-cost-cascade/HANDOFF.md` written.
- **Gate:** literal PRD criterion passes on two rows; the deciding caveat is retention (56.7% best). The exit checklist was complete except the owner's ADR-0021/0022 decision at that time. **P2 COMPLETE — gate accepted 2026-11-18.**
- Verification: ruff/format clean (117 files), mypy clean (53 files), pytest **374 passed / 2 skipped**. Real spend **$0**; no model or lever adopted at that time.
- Next: owner decision on ADR-0021/ADR-0022, then P3. Merged to `main` at `cd8f5aa` (PR #1); gate accepted 2026-11-18.

### 2026-11-17 — Buffy — P2-07 frontier and operating-point ADR
- `scripts/frontier.py` → `docs/reports/P2-frontier.md` from the six measured rows plus the escalation/student manifests: **no new LLM call, no new label**. Reports `e` and `s` per row, a 2-D Pareto frontier on cost vs test precision, and the literal PRD gate verdict per row.
- **Two rows pass** the literal gate: `sections-core` (−56.4%, retention 27.8%) and `escalation-length30` (−55.6%, test precision 98.2%, retention 56.7%, `e`=31.1%, `s`=0.29% under an assumed $0.05/CPU-hour).
- **ADR-0022 initially Proposed (later Accepted 2026-11-18):** operating point = `p2-05-length30-v1`, chosen by "most retention among gate-passers, then cheapest" rather than cheapest-only. Adoption was blocked on the owner's ADR-0021 decision; if ≥90% retention were required, no measured row passes.
- Verification: ruff/format clean, mypy clean, pytest **369 passed / 2 skipped**. No model adopted, no spend.
- Next: P2-09 (ledger-driven cost projection), then P2-08 (lock config, regression tests, report) at the gate.

### 2026-11-17 — Buffy — P2-06 batching measured (negative)
- Added `claim-extraction-batch-v1` (baseline prompt untouched), `src/axion/extract/batching.py` (greedy packing to a 24K-token ceiling, per-claim `paper_id` attribution reusing the baseline verifier), `scripts/run_batched_extraction.py`, and 6 offline tests.
- Run `p2-06-batch3-s20261114-n100` on the 100-paper seeded sample: **389 claims (3.89/paper vs 7.65 baseline)**, 127 requests incl. retries (vs 120), **0 parse / 0 attribution failures**, 50 span rejects, **$0.003518380/paper (−37.7%)**; harness row `batching`: dev precision 97.0%, test 97.2%, retention 34.5%, core retention 52.6%.
- **Negative:** the saving is halved claim yield (output is 62.9% of baseline cost), not packing efficiency; the request saving was erased by 503 retries. Not an operating point; carry into P2-07.
- Verification: ruff/format clean, mypy clean (53 files), pytest **369 passed / 2 skipped**.
- Next: P2-07 (combine, sweep, frontier, ADR).

### 2026-11-17 - opencode - P2-05b flywheel negative
- **Gold-free design:** base student on the **55 P1 non-gold papers**; flywheel pool on **40 P2-03a non-gold papers** with at least one accepted teacher claim (three zero-claim papers excluded). Pool split **28 candidate / 12 held-out** (`20261118`); only candidate labels can be added. Gold is evaluation only.
- **Signal:** per-paper **mean reciprocal rank (MRR)** of teacher-positive sentences in the student's full ranking. A binary top-8 recall signal was degenerate first (12/28 candidate papers tied at zero; realised 42.9%, held-out `e` 33.3%→41.7%). MRR was chosen on the non-gold candidate pool before the reported run; the gold test did not choose the signal.
- **Reported result:** threshold **0.0339** selected **8/28** (28.6%) and added **1,890 sentences / 77 positives** to the base. Held-out `e` **8.3% → 8.3%** (1/12 both), mean MRR 7.64% → 7.14%; **gold dev retention 25.2% → 26.2%**, **test retention 27.8% → 26.8%**, test precision 96.3% → 96.2%, unverifiable 85.3% → 85.9%. The frozen 98-paper `student_v1` reference is 30.9% / 100%. **Negative:** targeted labels did not reduce `e` and did not hold test retention.
- Provenance in `eval/flywheel/run_manifest.json` (selected IDs, label counts, model hashes); report `docs/reports/P2-05b-flywheel.md`; harness row `flywheel-student` (45 papers, 360 claims, ret 0.265, test precision 0.9615); 5 offline tests `tests/test_flywheel.py`. No LLM call, real spend **$0**; no gold in training.
- Verification: ruff/format clean (110 files), mypy clean (52 files), `pytest -q` **363 passed / 2 skipped**.
- Next: P2-06 prompt batching.

### 2026-11-17 - opencode - P2-05 calibrated escalation measured
- **Policy:** stage 0 is the frozen `student-v1-minilm-lr` (top-8); stage 1 is the frozen P1 `gemini-3.5-flash-lite` output on the longest 30% of papers; stage 2 is `gemini-3.8-flash` only when stage 1 accepts no claim. No model or tier was changed. The fraction and signal were frozen in `src/axion/eval/escalation.py` (`p2-05-length30-v1`) before the test read.
- **Confidence failed:** on 22 dev papers, every confidence feature is negatively correlated with per-paper retention (mean top −0.386, max −0.444, entropy −0.072); low confidence predicts *more* retained rows, so confidence-based escalation is worse than random at every rate. The only signal that beat random was sentence count (−0.682), a volume/risk proxy, not uncertainty. This is a published negative result, not a hidden tuning choice.
- **Frozen gold test:** **e=30.4% (7/23), retention 56.7% (55/97), precision 98.2% [90.4–99.7], savings 61.6%**. Overall (dev+test): **e=31.1% (14/45), $0.002505/paper vs $0.006282 = −60.1%**, $/retained **$0.000989 vs $0.001413**. Baseline precision is 96.9% test / 96.1% dev, so precision is within 2 points; retention is not.
- **Cost honesty:** stage 1 is a replay of cached teacher output; the ledger cost is the **list price those calls already carry**, not the cache's $0. Real spend **$0**. `s=0` in LLM terms; student inference **1,180 ms/paper CPU**, projected 0.29%/0.58% of baseline at $0.05/$0.10 per CPU-hour.
- **Stage 2:** 0/14 escalated gold papers had no accepted claim, so the policy never fired stage 2. The teacher's 10/98 non-gold zero-claim rate projects a 3.2% stage-2 rate, **+$0.000335/paper, 54.8% savings**; a dev mechanism probe (calls **487→488**) proves `parent_call_id` is ledgered (6,703+2,624 tokens, **$0.014867** list price, real spend $0; 52.6% savings if that unit cost is used). Probe output discarded and not scored.
- Report `docs/reports/P2-05-escalation.md`; manifest `eval/escalation/run_manifest.json`; harness row `escalation-length30` (45 papers, 410 claims, dev 0.983 / test 0.982 precision, retention 0.570, $0.002505/paper); 7 offline tests in `tests/test_escalation.py`.
- Verification: ruff check clean, `ruff format --check` **107 files**, mypy clean (51 files), `pytest -q` **358 passed / 2 skipped**. No model adoption, no push, real spend **$0**.
- Next: P2-05b flywheel (retrain with escalated cases; measure whether e drops and frozen test quality holds).

### 2026-11-17 — opencode — P2-04 cache and dedup measured
- **Cache `[x]`:** re-ran the first 5 frozen baseline papers under `p2-04-cache-probe`; the ledger recorded **5/5 cache hits, 0 provider calls, 0 prompt/completion tokens, $0.000000**, and the cache table stayed at **238 rows**. Across all runs, 9 of 486 attempts are hits and **0** hits carry a non-zero price. This is the acceptance's \"ledger shows $0 cache hits\".
- **Dedup `[x]`, negative on size:** new deterministic `src/axion/extract/dedup.py` (normalized exact key + fixed-seed MinHash/LSH + Jaccard verification). Census of 16,466 sentences in the 100-paper baseline sample: **190 duplicate copies (1.15%)** — 175 exact, 15 near at 0.9; **174 within-paper**, **16 cross-paper**; ≈**5,963 prompt tokens** (upper bound). At 0.8: 199 copies / 6,507 tokens. Duplicates are dominated by abstract/results repetition inside a paper.
- **Decision:** dedup is measured but **not applied**. Applying it changes the evidence a prompt sees and needs its own live run and quality row; within-paper dedup is the only safe first target.
- Report `docs/reports/P2-04-cache-dedup.md`; probe provenance `docs/reports/P2-04-cache-probe.{md,json}` and `eval/silver/claims_v1/cache_probe/`; 9 offline tests in `tests/test_dedup.py`.
- Verification: ruff/format clean, mypy clean (50 files), `pytest -q` **351 passed / 2 skipped**. No model adoption, no push, real spend **$0**.
- Next: P2-05 calibrated escalation, using the weak student.

### 2026-11-17 — opencode — P2-03a closed; P2-03b student measured; P2-03c curve
- **P2-03a `[x]`:** stopped at **98 non-gold papers / 687 silver claims** (55 P1 + 43 P2-03a), justified by the flat learning curve; all 45 gold papers excluded by ID; seed 20261114; zero gold in the draw. Two planned papers were lost to provider failures and recorded, not replaced.
- **P2-03b `[x]`:** `src/axion/train/student.py` + `scripts/train_student.py`; frozen MiniLM encoder + logistic head (C=1.0, balanced) on 16,452 sentences / 650 unique positive sentences. Fixed operating point **top-8 sentences/paper** (baseline mean 8.47 claims/paper), chosen before test scoring. **Frozen test: retention 30.9% (30/97), aligned precision 100.0% [88.6–100], unverifiable 83.7%, 184 claims; dev retention 25.2%.** CPU inference 1,278 ms/paper; no LLM calls, no ledger cost. Artifact SHA-256 `e6ac79d6…`; 12 offline tests. End-to-end fine-tuning, context features, abstract-similarity features, and section quotas were tested on dev; none improved the point enough (fine-tuning 29.1% vs 27.2% at k=8 for 48 CPU-minutes), so the simpler student ships and the negative result is published.
- **P2-03c `[x]`:** nested prefixes 10/20/35/50/70/83/98 papers; retention@8 23.3→25.2%, retention@20 45.6→56.3%, no trend; plateau documented. This is the sample-size justification and the reason the 300-paper ceiling was not spent.
- Verification: `ruff check .` clean, `ruff format --check .` 101 files, `mypy` clean (49 files), `pytest -q` **342 passed / 2 skipped**. No model adoption, no push, real spend **$0**.
- Next: P2-04 cache and dedup.

### 2026-11-16 — Buffy — P2-03a increment 1 + three owner-requested reports + ADR-0021
- **P2-03a (still `[~]`):** added nested, gold-excluding sampling (`sample_papers_excluding`, prefix of one seeded permutation) and `--exclude-paper-ids`; sample plan `docs/reports/P2-03a-sample.md` (4,928 corpus, 45 gold excluded, 55 non-gold already labelled, 45 new drawn, **0 gold in draw**). Increment run `p2-03a-teacher-s20261114-n100`: **43/45 papers, 303 claims, 31 rejects, 92.7% verbatim, 59 requests, $0.234809 list price, $0 real**. Non-gold labelled total now **98 of the 300 ceiling**. Sample size stays unjustified until the P2-03c learning curve exists.
- **Provider reliability:** `scripts/provider_reliability.py` → `docs/reports/P2-provider-reliability.md` + per-request CSV (UTC and Pacific). Ledger-wide: **481 requests, 239 failed (49.7%), 210 5xx, 208 × HTTP 503 = 43.2%**. Hourly rates in the report; the 503s cluster in the two evening windows used today.
- **Gold by section:** `scripts/gold_by_section.py` → `docs/reports/P2-gold-by-section.md` — 200 claims, 193 correct; core 57 (all approach), non-core 143; per-section table with Wilson CIs and 15 seeded non-core claims for owner skimming. No labels created.
- **ADR-0021 initially Proposed (later Accepted 2026-11-18):** P2 reports two retention numbers (all claims, core-section claims) and `$/core-section claim`; the gate keeps both precision and agreement-with-baseline and is **unchanged** until approved; P3 checks which sections relied-upon claims come from. Implemented in the harness: baseline 100% core retention at **$0.009902789**/core claim, `sections-core` **59.6%** at **$0.006730500** (−32.0%).
- Verification: `ruff`/format clean, `mypy` clean (47 files), pytest **330 passed / 2 skipped**.
- Next: P2-03b (train claim-sentence student on silver, tune on gold dev, report on frozen test).

### 2026-11-16 — Buffy — P2-02 section targeting measured
- Implemented the lever config-first: `src/axion/config/section_sets.yaml` (`all` = frozen baseline, `core` = abstract/results/conclusion), `src/axion/extract/sections.py` (`restrict_document`), applied in `build_plan` **before the prompt is rendered** so `verify_claims` needs no second guard; runner gained `--sections` / `--section-sets` and records the set plus its file hash in the plan JSON. 8 tests in `tests/test_sections.py`.
- Live free-tier run `p2-02-sections-core-s20261114-n100`: **93/96 papers, 428 accepted claims (4.60/paper), 105 rejects, 283 ledgered requests, $0 real spend**. Gemini repeatedly returned 503 "high demand" and one TLS `BAD_RECORD_MAC`; each stop was the documented three-consecutive-failure checkpoint and every resume skipped completed papers.
- Ablation (`scripts/ablate.py --all`): baseline unchanged (0.965 / 1.000 / $0.005645); `sections-core` **$0.002460613/paper (−56.4%)**, dev precision 92.9% [81.0–97.5], test 96.3% [81.7–99.3], **retention 34.5%**, unverifiable 59.7%. `paper_count` set to 93 (papers the cost covers), not 100.
- **Interpretation:** negative result alone. 57/200 gold claims (28.5%) lie in core sections because the gold sample is Methods/Introduction-heavy, so 56% of cost is bought by discarding two thirds of audited output. Not an operating point; carry it into P2-07.
- Verification: ruff/format/mypy clean, **324 passed / 2 skipped**. No model adoption, no ADR change, no push.
- Next: P2-03a teacher labelling (dry-run first; exclude all 45 gold papers; sample size from the learning curve).

### 2026-11-16 — Buffy — P2-01 verified and committed
- Resumed after a cut-off thread: P2-01 was `[x]` in the TODO with evidence, but the work existed only as a **staged, uncommitted** diff (`src/axion/eval/ablation.py`, `scripts/ablate.py`, `eval/ablation/configs/baseline.json`, `tests/test_ablation.py`, `docs/reports/P2-ablation.md`, `Makefile`, `.gitignore`, `src/axion/parse/jats.py`, TODO).
- `src/axion/parse/jats.py` had two parts: a **staged** addition of `split_sentences`/`sentence_bounds` (public, so evaluation alignment uses the parser's own sentence boundary rule — required by this harness) and an **unstaged** ruff-format rewrap of that same new function. Neither is unrelated work; both are part of P2-01, so they ship in one commit.
- Verification before committing: `ruff check .` clean, `ruff format --check .` 91 files, `mypy src/axion` clean (46 files), `pytest -q` **316 passed / 2 skipped**, pre-commit **8/8**.
- `python scripts/ablate.py --config baseline` (replay, **0 LLM calls**): precision **0.965** (193/200), retention **1.000**, dev **0.961165**, test **0.969072**, unverifiable **45.1%**, cost **$0.005644590/paper**; `baseline_check` reports `precision_matches: true` and `retention_complete: true` against the documented P1 values ($0.005645/paper, precision 96.5%).
- State: branch `p2`, commit `6033b07`; TODO P2-01 `[x]` with evidence. Real spend **$0**.
- Next: P2-02 (section targeting). Blockers/questions: none; the P2 small tier and bulk labeler still need owner approval before adoption.

### 2026-11-16 — DeepSeek V4.1 Flash Free — P1-11 agreement closed; P1 complete
- Owner supplied `eval/audit/claims_audit_v1_overlap_labelled.csv`: 40 rows, `labeler=friend`, rubric v2, all `CORRECT`. The agent created or changed no labels.
- `scripts/audit_validate.py --overlap` reports **n=200, precision 96.5%, Wilson 93.0–98.3%**; agreement **n=40, raw 100.0%, Cohen's κ not estimable** because both label sets used only `CORRECT`. The overlap contains none of the 7 `NOT_A_CLAIM` rows, so it does not estimate agreement on the error class. `docs/reports/P1-audit.md` and `docs/reports/P1-baseline.md` state this caveat.
- Code: `render_markdown` now distinguishes independent-second-labeler from self-agreement and reports undefined κ as **not estimable**; `build_p1_report.py --overlap` folds in the second labels; tests cover the degenerate case and the report path.
- Docs: P1-11 marked `[x]`, phase exit checklist closed, ADR-0016 **Accepted**, and the PRD/rubric/context agreement wording updated. P1 gate is final at 96.5%.
- Verification: **306 passed, 2 skipped**; ruff check/format, strict mypy, and all **8/8** pre-commit hooks clean. No LLM calls; real spend remains **$0**.
- Next: start P2; the small-tier and bulk-labeler choices in ADR-0019 remain **Proposed** and need owner approval.

### 2026-11-16 — DeepSeek V4.1 Flash Free — P1 verification + status cleanup
- Verified clean at `67555ac`: `p1 = main = origin/p1 = origin/main`; **304 passed, 2 skipped**; ruff check/format, strict mypy, and all 8 pre-commit hooks pass; `scripts/build_p1_report.py` regenerates `docs/reports/P1-baseline.md` with no diff; `scripts/audit_validate.py` confirms **n=200, precision 96.5%, Wilson 93.0–98.3%**; primary CSV has 0 blank labels and 0 non-CORRECT rows without a note; the 40-row overlap file is entirely blank.
- No labels were created or changed and no LLM calls were made. Corrected stale docs that still said "No labels exist"/"0 claims labelled", and refreshed the P1 status, next action, and pacing text.
- Only **P1-11** remains: blind 40-claim overlap relabel on/after 2026-11-22, or an independent second labeler; then run `audit_validate.py --overlap` and close the phase.
- Commit `5112587`; `p1` and `main` pushed.

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
