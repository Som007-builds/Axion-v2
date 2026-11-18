# TODO — P3 — Blast radius

**PRD:** `docs/PRD.md` (PRD §P3) · **Gate:** see PRD · **Update this file as you work.**

## Status legend
`[ ]` todo · `[~]` in progress (needs agent/started/branch) · `[x]` done (needs evidence) · `[!]` blocked (needs reason) · `[-]` dropped (needs ADR ref)

## Rules (read `docs/AGENT_PROTOCOL.md` for full text)
- Claim a task (`[~]`) before starting; mark `[x]` with evidence when done; checkpoint notes at every step.
- If you may run out of budget: write a PARTIAL-state note (done / left / exact next command) and commit WIP.
- Take the **first** task that is `[ ]` or a stale `[~]`, respecting `depends:`.
- Update `docs/PROGRESS.md` at session end.

## Tasks

### [x] P3-01 — Dependency labeling guideline
- depends: P2 gate passed
- what: Write docs/eval/DEPENDENCY_GUIDELINE.md (RELIES_ON / MENTIONS / UNRELATED) with examples and edge cases; pilot on 20 contexts and refine.
- acceptance: Guideline v1 committed; pilot notes recorded.
  - agent: opencode | started: 2026-11-18 16:02 | branch: p3
  - notes:
    - 2026-11-18 16:02: P2 gate accepted; claiming P3-01. Plan: guideline v1 with illustrative edge cases, a seeded 20-context pilot packet, and blank labels. The agent will not create labels; the owner labels the packet and the notes drive guideline v1.1.
    - 2026-11-18 16:09: guideline v1 + `scripts/dependency_pilot.py` + `eval/audit/dependency_pilot_v1.csv` committed as `dafa9dd`. Packet: **20 blank-label rows across 20 source papers**, seed `20261118`; it intentionally includes retraction notices, reference-list fragments, and grouped citations as edge cases. No labels created by the agent.
    - 2026-11-18: packet extended with `paragraph_text` and a source-abstract `source_claim_text` proxy (not a linked claim); built the blank-label labeler `eval/audit/dependency_pilot_labeler.html` (self-contained, blind, localStorage autosave, CSV export). No labels created.
    - 2026-11-18: received `eval/audit/dependency_pilot_v1_labelled.csv`: 20/20 rows, 20/20 notes, labeler `Soham` (owner responsibility), date `2026-11-18`; labels **16 MENTIONS / 2 RELIES_ON / 2 UNRELATED**, 0 blank. Single labeler, so agreement/κ is not estimable. Two review corrections (`P3P-010`, `P3P-014`) drove the v1.1 corroboration rule. Summary: `docs/reports/P3-01-pilot.md`; metrics: `scripts/dependency_pilot_metrics.py`.
  - done: 2026-11-18 | evidence: `docs/eval/DEPENDENCY_GUIDELINE.md` v1.1; `eval/audit/dependency_pilot_v1_labelled.csv`; `docs/reports/P3-01-pilot.md`; `eval/audit/dependency_pilot_v1.summary.json`; `python scripts/dependency_pilot_metrics.py` → 20 rows / 16 MENTIONS / 2 RELIES_ON / 2 UNRELATED / 0 blank, single-labeler agreement not estimable; `pytest -q` 374 passed / 2 skipped.

### [x] P3-02 - Candidate generator
- depends: P3-01
- what: For each retracted paper, collect all in-corpus citing contexts via JATS xrefs; link to source paper claims; store in Neo4j. No LLM.
- acceptance: Counts per retracted paper reported; idempotent run.
  - agent: Buffy | started: 2026-11-18 18:20 (claimed by opencode) | branch: p3
  - notes:
    - 2026-11-18 18:20: Claiming P3-02. Plan: reuse the deterministic JATS parser and reference matcher, emit stable candidate context IDs, report counts per source, and load idempotently into Neo4j. No LLM calls. The 20-row P3-01 pilot is calibration only and will not be treated as gold or training data.
    - 2026-11-18 19:05 (Buffy, resumed after a usage-limit cut): found the WIP untracked and green-except-lint. Fixed `tests/test_candidates.py` (the abstract-removal helper could never match the wrapped fixture, so the unlinked-context test was passing/failing for the wrong reason — it asserted a pointer that was still there; now `re.sub(..., flags=re.DOTALL)`), removed the two E501s, reformatted. No duplicate fixtures were present in the file: each fixture has one `journal-meta`, one `abstract`, one entry per paper, one `mkdir`.
    - Deeper Neo4j container was down at handover; started Docker Desktop and the project container (healthy on `127.0.0.1:7888`) to do the real load rather than only the in-memory one.
    - **Measured (`--twice`, Neo4j):** 285 source papers with a citer edge, **258 with ≥1 candidate context, 27 with zero**, **6,117 candidate contexts**, 3,357 citer papers, **3,976 citer→source edges with contexts** (both totals equal the P1 manifest's `contexts_total` 6117 and `edges_with_contexts` 3976, which the script enforces). **214 of 285 sources (75.1%)** yield an abstract-sentence source-claim proxy, so **4,262 contexts (69.7%) carry a pointer and 1,855 (30.3%) are unlinked** — the unlinked ones are contexts whose source abstract yields no usable sentence (missing, withdrawn, background-only, or shorter than 60 chars).
    - **Idempotency:** loaded onto an already-populated graph (Claim 0 → 214, EXTRACTED_FROM 0 → 214, every other count unchanged); second load identical. Independent Cypher checks after the run: 6,117 contexts, 4,262 with a pointer, 258 distinct sources, **0 duplicate `ctx_id`, 0 duplicate `pmcid`**, all `IN_PAPER`/`POINTS_TO`/`EXTRACTED_FROM` edges `stage='rules'`.
    - **Skew that matters for P3-03:** contexts per source are mean 21.5, **median 4**, max 775; **17 sources hold 4,054 of the 6,117 contexts (66%)**, while 45 sources have exactly 1. A context-level uniform sample would be dominated by a handful of papers, so P3-03 must stratify by source paper as well as by section.
    - **P3-03 planning input (pilot + corpus):** the 20-label pilot gives a RELIES_ON base rate of 2/20 = 10.0%, Wilson 95% **[2.8%, 30.1%]** (`axion.eval.audit.wilson_interval`). At 10%, n=150 yields ~15 RELIES_ON and a recall estimate at 0.80 has CI 0.55–0.93 (±0.19) — too wide to certify the ≥0.70/≥0.80 recall gate. ±0.10 needs ~60 positives, i.e. ~600 contexts at that rate. The pilot also deliberately over-samples edge cases (retraction notices, reference-list fragments, grouped citations), so 10% is not a corpus estimate.
  - done: 2026-11-18 | evidence: commit `d00112f` (`src/axion/link/candidates.py`, `scripts/generate_candidates.py`, `tests/test_candidates.py`, store backends); reports `docs/reports/P3-02-candidates.md` + `docs/reports/P3-02-candidate-counts.csv` (285 rows); `.venv/Scripts/python.exe scripts/generate_candidates.py --twice` → backend `bolt://127.0.0.1:7888`, run `p3-02-candidates-aba53804bf5c`, 6,117 contexts / 285 sources / 258 with contexts / 214 proxies / 4,262 linked / idempotent `true`; `pytest -q` → **380 passed, 2 skipped**; ruff + `mypy src/axion` clean (54 files). No LLM calls, real spend **$0**.

### [~] P3-03 — Gold labeling set
- depends: P3-02
- what: Stratified sample (>=100-150 contexts) by section and retracted paper; label; double-label >=20%; agreement stats; freeze paper-level dev/test. Gold is for evaluation only; exclude every gold dev/test paper from student training.
- acceptance: eval/audit/dependency_audit_v1.csv committed; agreement reported; split is by paper. (Owner labels.)
  - agent: Buffy | started: 2026-11-18 20:10 | branch: p3
  - notes:
    - 2026-11-18 20:10 (Buffy): claiming. Owner instruction: waves (wave 1 = 150, extendable without invalidating earlier draws), source + section stratification with a per-source cap, cue-enriched rows plus a uniform slice for an unbiased base rate, dev/test split by source frozen before any detector, an explicit linked/unlinked policy, a ≥20% overlap for a second labeler, and an extended blind labeler. ADR-0023 (Proposed) written first. The agent creates **no labels**.
    - Agent-side work (packet, labelers, report, ADR) is complete now; **P3-03 stays `[~]` until the owner's labels exist.**
    - **Built:** `scripts/dependency_sample.py` (deterministic sampler + packet + labelers + report), `docs/eval/audit_labeler_template.html` (extended blind tool: labeler-id field, autosave/resume, keyboard shortcuts, `insufficient_context`, note box, CSV export with labeler + date, unlinked-source abstract view), ADR-0023 (Proposed).
    - **Wave 1 (measured, seed `20261119`):** **150 rows** = 30 uniform (weight 203.9) + 120 cue-enriched, stratified by section; **cap 8 rows/source applied per frame**: **7 sources truncated by the cap** (all in the enriched frame), and **6 sources hold more than 8 wave rows in total, max 14** (17 sources hold 66% of contexts). Split by source, frozen: **34 dev / 34 test sources, 3,059 / 3,058 contexts, 73 / 77 wave rows**. Linked 101/150 (67.3%); 49 unlinked, 15 with an abstract and 34 with none (retracted/withdrawn stubs). Overlap: the pre-built **30 rows** (24 enriched + 6 uniform) is **superseded** by ADR-0023 Amendment A; overlap 2 is built from the owner's labels.
    - **Cue measurement:** `we_used` 0.3%, `based_on` 3.5%, `numeric_effect` 2.2%, `comparison` 6.5%, `method_word` 3.7%, `inference_connector` 3.0%, `prior_finding` 1.0% → cue-positive pool 1,080 (17.7%). A bare-digit cue fired on 99.8% and was rejected after measurement.
    - **Honest risk:** the cues are unvalidated — no cue fires on either pilot `RELIES_ON` row, so expected positives are **~3 under the pilot's reading** or **~21 if enrichment lifts the rate to 15%**. Wave 1 measures the cues; if the lift is ~0, wave 2 shifts to the uniform frame.
    - **Files for the owner:** `eval/audit/p3-03/p3-03-wave1-labeler.html` (label this), `eval/audit/p3-03/p3-03-wave1-overlap-labeler.html` (**SUPERSEDED — do not label**; see `p3-03-wave1-overlap-SUPERSEDED.md`). Design report: `docs/reports/P3-03-wave1-packet.md`.
    - **Overlap 2 builder (2026-11-18, after the owner's Amendments A/B):** `scripts/dependency_sample.py --build-overlap <labelled.csv>` validates labeler 1's export (known row ids, one labeler, no blanks, whole wave covered) and writes `p3-03-wave1-overlap2-{blind.csv,labeler.html,selection.json}`. Rule: all/nearly all `RELIES_ON` + round-robin spread over `MENTIONS`/`UNRELATED`/`insufficient_context`; ≥30 rows and ≥20% of the wave and ≥6 negatives; blank labeler id; rows in `sha256(seed:ctx_id)` order. `tests/test_dependency_sample_overlap.py` (13 tests) pins the rule, determinism, blindness and rejection paths. `text_bearing` added to the manifest only (116 text-bearing / 34 stub) and never to the labeler payload; no packet row was redrawn.
    - **Wave-1 labels received (2026-11-18, owner):** `eval/audit/p3-03/dependency_audit_v1_wave1_labelled.csv` — 150/150 rows, 0 blank labels, 150 notes, `labeler` = **`Soham`** (the first return carried the mis-set id string `Muse-agent`; corrected on the owner's instruction, pre-correction export kept in `bbcd377`). Labels: **25 `RELIES_ON` / 120 `MENTIONS` / 5 `UNRELATED` / 0 `insufficient_context`**. No label value was altered; no agent created a label.
    - **Overlap 2 built (2026-11-18):** `python scripts/dependency_sample.py --build-overlap eval/audit/p3-03/dependency_audit_v1_wave1_labelled.csv` → **31 rows** = 25 `RELIES_ON` + 3 `MENTIONS` + 3 `UNRELATED` + 0 `insufficient_context`, 20.7% of the wave, floors met (≥30 rows, ≥20%, ≥6 negatives); blind file has blank label/labeler/date and no internal columns. Files: `p3-03-wave1-overlap2-{blind.csv,labeler.html,selection.json}`. **Realised mix is 81% positive, so overlap κ is conservative (prevalence effect runs opposite to the ~50/50 assumption), and the negative side rests on 6 rows** — recorded in ADR-0023 Amendment A.
    - **Still open:** the second labeler has not labelled yet, and no metrics/agreement script exists, so P3-03 stays `[~]`.
    - **Agreement measured (2026-11-18):** second labeler returned `dependency_audit_v1_wave1_overlap2_labelled.csv` (31/31, `friend`). `python scripts/dependency_agreement.py` → raw agreement **31/31 = 100%**, Cohen's κ **1.000** (PABAK 1.000, design-weighted 1.000), **degenerate because there are zero discordant pairs** — recorded as consistency, not established reliability; 6 negative rows are the fragile side. Reports: `docs/reports/P3-03-agreement.md`, `eval/audit/p3-03/p3-03-agreement.json`; tests `tests/test_dependency_agreement.py` (10).
    - **Still open:** wave-1 weighted/unweighted rates and the Amendment B split (116-row text-bearing frame vs 34-stub stratum) are not computed yet, so P3-03 stays `[~]`.
    - **Wave-1 metrics measured (2026-11-18):** `python scripts/dependency_metrics.py` → **150 rows: 25 `RELIES_ON` / 120 `MENTIONS` / 5 `UNRELATED` / 0 `insufficient_context`**; uniform slice **30 rows: 7 / 22 / 1**; enriched **120 rows: 18 / 98 / 4**; dev **73: 13 / 58 / 2**, test **77: 12 / 62 / 3**; text-bearing frame **116 rows: 22 / 92 / 2**; stub stratum **34 rows: 3 / 28 / 3**. Uniform base rate **7/30 = 23.3%**, Wilson 95% **[11.8%, 40.9%]**; enriched **18/120 = 15.0%** [9.7%, 22.5%] — **no measured cue lift** (the point estimate is lower in the enriched frame), so the cues are unvalidated and must not be used as a positive filter. **72% of positives come from the enriched frame**, which is 80% of the rows. The stub stratum contains **3 `RELIES_ON`**, so Amendment B's "stubs are near-certain negatives" reasoning is withdrawn. Report: `docs/reports/P3-03-wave1-metrics.md`; summary `eval/audit/p3-03/p3-03-wave1-metrics.json`; tests `tests/test_dependency_metrics.py` (7).
    - **Amendment C (2026-11-18, owner instruction):** from wave 2 on, labeler 1's labelled file must never be shared with labeler 2 (blind HTML/CSV only), the returned export is checked against the blinded subset before comparison, and an overlap must carry **≥15 negative rows** (MENTIONS + UNRELATED + insufficient_context) or the report states negative-side κ is not estimable. Wave 1 did not meet the isolation rule (its export sat beside labeler 2's packet), so its agreement is consistency only. Enforced in `scripts/dependency_agreement.py` (`NEGATIVE_FLOOR`, protocol section of the report).
    - **Wave-2 packet built (2026-11-18, ADR-0024):** `scripts/dependency_wave2.py` → 150 uniform rows from the 5,967-context pool, π = 0.02513826, weight 39.78, cap 8/source (5 truncated), 78 dev / 72 test, 0 contexts shared with wave 1, 116 text-bearing / 34 stub. Files `p3-03-wave2-{blind.csv,manifest.csv,labeler.html,sampling.json}` + `docs/reports/P3-03-wave2-packet.md`; tests `tests/test_dependency_wave2.py` (7). Nearest labeler: **`eval/audit/p3-03/p3-03-wave2-labeler.html`**.
    - **Combined metrics (2026-11-18):** `scripts/dependency_metrics.py` also writes `docs/reports/P3-03-wave1-wave2-metrics.md` and `eval/audit/p3-03/p3-03-combined-metrics.json` (per-wave and combined counts, updated weighted base rate over all uniform rows, positives per split, ADR-0024 stop-rule numbers); it prints "wave 2 labels not present yet" and skips until the export exists.
    - **Wave-2 labels received (2026-11-18, owner):** `dependency_audit_v1_wave2_labelled.csv` — 150/150, 0 blanks, 150 notes, **12 `RELIES_ON` / 129 `MENTIONS` / 9 `UNRELATED`** (labeler normalised to `Soham`). Measured pace **95 min = 38 s/row**.
    - **Combined metrics:** 300 rows, **37 positives**; uniform base rate heterogeneous (wave 1 23.3% [11.8, 40.9] vs wave 2 8.0% [4.6, 13.5]); pooled weighted 15.8% [10.3, 24.9], unweighted 10.6%; dev 16/151, test 21/149; text-bearing 232 rows / 32 positives; stubs 68 rows / 5 positives. Stop rule: 77 needed, 40 outstanding, 254–500 more rows depending on rate. Report `docs/reports/P3-03-wave1-wave2-metrics.md`.
    - **Wave-2 overlap built (Amendment C):** 30 rows = 12 `RELIES_ON` + 18 negatives (9 + 9), floor met; blind files isolated in `eval/audit/p3-03-labeler2/` (no labeler-1 file, no manifest, no selection counts).
    - **Wave-2 agreement (2026-11-18):** `scripts/dependency_agreement.py --wave wave2` — **30/30 = 100%, κ 1.000 degenerate (zero discordant pairs)**, negative side estimable at last: **negative-class κ 1.000**, specificity 18/18 = 100% [82.4, 100]. Matrix fully diagonal (12/9/9). Isolation audit all pass (distinct ids, declared handoff dir, no foreign export, blind schema only; pace 38 vs 120 s/row recorded as weak). Report `docs/reports/P3-03-wave2-agreement.md`.
    - **Wave-3 decision (ADR-0025, accepted 2026-11-18): narrow the gate claim, no wave 3.** P3-05 reports measured recall with its interval plus the false-alarm reduction vs the citation-level floor; the 0.70/0.80 recall floor is only claimable if the interval supports it.
    - **Still open:** P3-05 staged detector. P3-03 stays `[~]` until the P3-05 gate report exists.
  - done: — (in progress: labels, overlap 2, agreement and wave-1 metrics are in; wave-2 decision and P3-04 pending) | evidence: — `eval/audit/p3-03/{dependency_audit_v1_wave1_labelled.csv,dependency_audit_v1_wave1_overlap2_labelled.csv,p3-03-wave1-overlap2-*,p3-03-agreement.json,p3-03-wave1-metrics.json}`; `scripts/dependency_{agreement,metrics}.py`; no LLM calls, $0; **no labels created by the agent**.

### [x] P3-04 — Baselines
- depends: P3-03
- what: Implement and score citation-level, section/lexical heuristic, and LLM-only baselines (ledger cost included).
- acceptance: Baseline table generated by script.
  - agent: Buffy | started: 2026-11-18 | branch: p3
  - notes: `scripts/dependency_baselines.py` scores all three on the 300 labelled rows, dev/test separately, weighted and unweighted, with Wilson CIs, on the 232-row text-bearing frame and the 68-row stub stratum separately. Heuristic tuned on **dev only** (30-point grid in the JSON); **test computed once and frozen** in `eval/audit/p3-04/p3-04-test-frozen.json` — a later run refuses if a frozen number or the spec moved. LLM-only ran live through `LLMClient` on the Gemini free tier after a dry-run estimate: **300/300 rows, list price $0.0739, real spend $0**, 3+297 calls, ledger run `p3-04-llm-2026-11-18`.
  - done: 2026-11-18 | evidence: `docs/reports/P3-04-baselines.md`, `eval/audit/p3-04/{p3-04-baselines.json,p3-04-test-frozen.json,p3-04-llm-predictions.csv}`, `tests/test_dependency_baselines.py` (8 tests). Text-bearing test (18 positives): citation-level P 16.4% / R 100% / FAR 100%; heuristic P 30.0% / R 83.3% [60.8, 94.2] / FAR 38.0% [28.8, 48.2]; LLM-only P 75.0% / R 16.7% [5.8, 39.2] / FAR 1.1%. 21 test positives overall — recall claims are wide, stated in the report. ADR-0025 (Proposed) records the wave-3 option and the narrow-the-claim alternative.

### [ ] P3-05 — Staged detector
- depends: P3-04, P2-03b
- what: Heuristic features -> teacher-distilled student (silver labels from teacher on candidate contexts, paper-level split, gold dev/test) -> calibrated LLM escalation; tune on gold dev; evaluate on frozen gold test; report per-stage cost, `e`, and `s`.
- acceptance: Gold-test metrics with CIs; per-stage cost share; `e` and `s` reported; no student evaluation on teacher-labeled data; no paper overlap between train and gold dev/test.
  - agent: — | started: — | branch: p3
  - notes:
  - done: — | evidence: —

### [ ] P3-05b — Priority / lazy scheduling
- depends: P3-05
- what: Implement a risk-ordered queue (contexts citing flagged papers first), idempotent hash-keyed incremental runs, and explicit hot/cold corpus states. Cold items remain unprocessed until needed.
- acceptance: Re-running produces identical counts/decisions; queue order documented; cold corpus items demonstrably untouched; no duplicate processing.
  - agent: — | started: — | branch: p3
  - notes:
  - done: — | evidence: —

### [ ] P3-06 — Claim linking
- depends: P3-05
- what: Match relying contexts to specific claims in the retracted paper (embedding match, LLM only if ambiguous); evaluate on labeled subset.
- acceptance: Link accuracy reported with CI.
  - agent: — | started: — | branch: p3
  - notes:
  - done: — | evidence: —

### [ ] P3-07 — Propagation rule v2
- depends: P3-06
- what: Document and implement parameterized trust propagation (strength-weighted, capped, limited transitivity); unit tests and sensitivity analysis.
- acceptance: Rule spec in docs; tests green; sensitivity plot/table generated.
  - agent: — | started: — | branch: p3
  - notes:
  - done: — | evidence: —

### [ ] P3-08 — Cost accounting
- depends: P3-05
- what: Compute $/retraction analyzed, per-stage breakdown, escalation rate `e`, and student cost ratio `s` from the ledger; compare against baselines.
- acceptance: Script outputs table; numbers match ledger; `e` and `s` reported.
  - agent: — | started: — | branch: p3
  - notes:
  - done: — | evidence: —

### [ ] P3-09 — Case studies
- depends: P3-07, P3-08
- what: Select >=3 real retractions; document blast radius and include honest failure cases.
- acceptance: docs/reports/P3-case-studies.md.
  - agent: — | started: — | branch: p3
  - notes:
  - done: — | evidence: —

### [ ] P3-10 — Report + gate review
- depends: P3-09
- what: docs/reports/P3-blast-radius.md; apply gate rule honestly (beat citation-level on false alarms at recall >=0.70 or stop and write up).
- acceptance: Gate decision recorded in PROGRESS and an ADR.
  - agent: — | started: — | branch: p3
  - notes:
  - done: — | evidence: —

## Phase handoff log (append newest first)
<!-- Format: YYYY-MM-DD — agent — what changed — next step -->
- 2026-11-18 — Buffy — P3-03 wave 1 built: 150 rows (30 uniform + 120 cue-enriched, cap 8/source per frame: 7 truncated, 6 sources >8 rows, max 14), 34/34 source split frozen, labelers + ADR-0023 **Accepted with Amendments A/B** (pre-built 30-row overlap superseded; overlap 2 comes from the owner's labels); no labels created, $0 — next: **owner** labels `eval/audit/p3-03/p3-03-wave1-labeler.html` and returns the exported CSV
- 2026-11-18 — Buffy — P3-02 closed: 6,117 candidate contexts across 285 sources (258 with ≥1, 27 at zero), 214 source-claim proxies → 69.7% of contexts linked, idempotent on a populated Neo4j (0 duplicate keys), no LLM, $0 — next: **owner** labels the P3-03 gold set (agent must not start it)
- 2026-11-18 — opencode — P3-01 closed: 20/20 pilot labels returned, guideline v1.1, measured pilot summary; single labeler so no agreement estimate — next: P3-02 candidate generator
- 2026-11-18 — opencode — P3-01 blank-label HTML labeler added; packet now carries paragraph and source-claim proxy — next: owner exports labels, then guideline v1.1 and P3-02
- 2026-11-18 — opencode — P3-01 guideline v1 + 20-context blank pilot packet committed (`dafa9dd`); owner labeling pending — next: owner labels, then guideline v1.1 and P3-02

## Phase exit checklist
- [ ] All tasks `[x]` or `[-]` with ADR
- [ ] Gate criteria evaluated honestly (see PRD)
- [ ] `docs/PROGRESS.md` phase table and headline numbers updated
- [ ] Report committed in `docs/reports/`
