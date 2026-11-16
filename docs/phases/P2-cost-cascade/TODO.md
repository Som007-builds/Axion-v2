# TODO — P2 — Cost cascade

**PRD:** `docs/PRD.md` (PRD §P2) · **Gate:** see PRD · **Update this file as you work.**

## Status legend
`[ ]` todo · `[~]` in progress (needs agent/started/branch) · `[x]` done (needs evidence) · `[!]` blocked (needs reason) · `[-]` dropped (needs ADR ref)

## Rules (read `docs/AGENT_PROTOCOL.md` for full text)
- Claim a task (`[~]`) before starting; mark `[x]` with evidence when done; checkpoint notes at every step.
- If you may run out of budget: write a PARTIAL-state note (done / left / exact next command) and commit WIP.
- Take the **first** task that is `[ ]` or a stale `[~]`, respecting `depends:`.
- Update `docs/PROGRESS.md` at session end.

## Reality check and amendments (2026-11-16, ADR-0020 Proposed — read before starting)

Since this TODO was written, P1 measured a baseline and the provider changed. These amendments apply
to every task below; task IDs are unchanged.

- **Provider and baseline are frozen.** Gemini free tier; baseline `gemini-3.5-flash-lite`, thinking
  `default`, max output 16,384, temperature 0.0, prompt `claim-extraction-v1`. `gemini-3.8-flash` is
  the large/reference tier (5 RPM / 20 RPD). Billing off, real spend $0, list price ledgered.
- **Gold is precision-only.** 200 audited baseline claims over 45 papers, 22 dev / 23 test, split by
  paper and frozen. Gold labels the P1 output; **absolute recall is unknown**.
- **Three quality numbers, always reported together:** (a) precision on gold dev/test over *aligned*
  output; (b) retention of the 200 gold baseline claims (agreement relative to baseline output —
  **not recall**); (c) cost from the ledger. Output that aligns with no gold row is **unverifiable**
  and reported separately, never counted as correct.
- **Training excludes all 45 gold papers.** Silver trains; gold evaluates; split by paper; never
  tune on the frozen test split.
- **Silver labelling is a seeded corpus sample, not the corpus.** Daily caps (450 teacher
  requests/day) forbid corpus-wide labelling. The sample size is justified by the measured learning
  curve (P2-03c), not chosen to hit a round number.
- **No new model is adopted without owner approval.** `gemini-3.1-flash-lite` and Gemma 4
  (`gemma-4-26b-a4b-it`, `gemma-4-31b-it`) are candidates. No list price exists for Gemma and
  structured-output support is unverified; test on small samples and ask.
- **Structured claim fields are not measured by gold.** A sentence-level student emits
  `claim_type="other"`; report that honestly.
- **No GNU `make` on this host.** "`make ablate`" means `python scripts/ablate.py`; "`make report`"
  means the documented Python script.

## Tasks

### [x] P2-01 — Ablation harness
- depends: P1 gate passed
- what: Frozen dev/test claim audit split; scripted configs; JSON + markdown outputs; seeds and config hashes recorded; cost from ledger.
- acceptance: `python scripts/ablate.py --config baseline` reproduces the P1 baseline within tolerance **without new LLM calls** (replays the frozen silver run). Reports aligned precision, retention, unverifiable rate, and cost.
  - agent: opencode (implementation), Buffy (verify + commit) | started: 2026-11-16 | branch: p2
  - notes:
    - 2026-11-16 Buffy: resumed the stale work per protocol §5 — the task was already `[x]` with evidence but **committed nowhere**; all nine files were staged and `jats.py` also had an unstaged ruff-format rewrap of the function added in the same diff. Decision: **continue**, not restart. Re-ran the whole suite and the replay before committing; the `jats.py` addition (`split_sentences`, `sentence_bounds`) is required by the harness's sentence alignment, and the unstaged part is only its formatting, so both belong to this task rather than a separate commit.
    - Unit of precision is the **gold row**: a config covers a gold claim when it emits a claim in the same sentence. A replay is therefore exact, not approximate (193/200), and duplicate output cannot inflate precision.
    - Baseline replay makes **no LLM calls**; cost is read from the existing ledger run `p1-10-flashlite-s20261114-n100`. Config file hash and input file hashes are recorded in `eval/ablation/results/results.json`.
    - Output that matches no gold row is reported as unverifiable and never counted as correct. This is expected to be large (~45%) because gold sampled only 200 of the baseline's claims.
    - 10 offline tests in `tests/test_ablation.py` cover exact replay, duplicate handling, sentence alignment, split leakage, and ledger cost.
  - done: 2026-11-16 | evidence: commit `6033b07`; `python scripts/ablate.py --config baseline` → precision **0.965** (193/200 exact), retention **1.000**, dev **0.961165**, test **0.969072**, unverifiable **45.1%**, cost **$0.005644590/paper** vs the P1 run report **$0.005645**, 0 calls (replay); `baseline_check` → `precision_matches: true`, `retention_complete: true`.
  - verification 2026-11-16 (Buffy): `ruff check .` clean; `ruff format --check .` 91 files formatted; `mypy src/axion` clean (46 files); `pytest -q` **316 passed, 2 skipped** (306 before + 10 in `tests/test_ablation.py`); pre-commit **8/8** on the commit. No LLM calls; real spend remained **$0**.

### [ ] P2-02 — Lever: section targeting
- depends: P2-01
- what: Restrict extraction to configurable sections; measure delta cost, aligned precision, retention of gold baseline claims, unverifiable rate, and claim yield.
- acceptance: Isolated ablation row in results table.
  - agent: — | started: — | branch: p2
  - notes:
  - done: — | evidence: —

### [-] P2-03 — Lever: sentence-level claim filter (superseded)
- depends: P2-01
- what: Superseded by ADR-0008 on 2026-11-14. Original: embedding features + simple classifier trained on audited labels; threshold on dev; evaluate on test.
- acceptance: Superseded; use P2-03a/b/c (teacher-student track).
  - agent: — | started: — | branch: p2
  - notes:
    - 2026-11-14: replaced by ADR-0008; audited-label-only classifier was too small a lever for corpus scale.
  - done: — | evidence: ADR-0008.

### [ ] P2-03a — Silver-label generation by teacher
- depends: P2-01, P1-10
- what: Budget-capped, dry-run-first teacher labeling on a **seeded sample of corpus papers excluding all 45 gold papers**; persist provenance (teacher model/version, prompt version, run_id); paper-level split; write to the silver-label store. Sample size is justified by the learning curve (P2-03c).
- acceptance: Dry-run estimate produced; sample size and seed recorded and justified from the learning curve; silver manifest + hashes committed (large labels may be external with manifest); **zero gold papers in the sample**; ledger stage `teacher_label`; daily-quota stop is clean and resumable.
  - agent: — | started: — | branch: p2
  - notes:
  - done: — | evidence: —

### [ ] P2-03b — Train claim-sentence student + gold evaluation
- depends: P2-03a
- what: Train a small encoder on the silver TRAIN split; tune thresholds on gold DEV; report on frozen gold TEST; record student version/hash. Never evaluate on teacher-labeled data.
- acceptance: Gold-test aligned precision, **retention of gold baseline claims**, and unverifiable rate with CIs; absolute recall is reported as **unmeasured**; no paper overlap between train and gold dev/test; isolated ablation row; model metadata/hash recorded.
  - agent: — | started: — | branch: p2
  - notes:
  - done: — | evidence: —

### [ ] P2-03c — Learning curve
- depends: P2-03b
- what: Measure student quality vs. number of silver labels at geometric steps up to the label budget; report marginal value.
- acceptance: Curve/table generated by script; budgets and assumptions recorded; negative result published if it plateaus.
  - agent: — | started: — | branch: p2
  - notes:
  - done: — | evidence: —

### [ ] P2-04 — Lever: cache and dedup
- depends: P2-01
- what: Content-hash keys; near-duplicate sentence dedup; measure hit rates on re-runs and across papers.
- acceptance: Hit-rate report; ledger shows $0 cache hits.
  - agent: — | started: — | branch: p2
  - notes:
  - done: — | evidence: —

### [ ] P2-05 — Lever: calibrated escalation
- depends: P2-01, P2-03b
- what: Define confidence/agreement signals and calibrated or conformal thresholds; escalate low-confidence items to a small LLM, then a large LLM. Measure escalation rate `e`, escalation cost, and net cost; log `parent_call_id`.
- acceptance: Isolated ablation row; escalation rule + calibration documented; `e` measured; net cost reported.
  - agent: — | started: — | branch: p2
  - notes:
  - done: — | evidence: —

### [ ] P2-05b — Flywheel experiment
- depends: P2-05, P2-03c
- what: Retrain the student including escalated cases as new silver labels; measure whether `e` drops and whether gold-test quality holds.
- acceptance: Before/after `e` and gold-test quality reported; provenance of new labels recorded; negative result published if no improvement.
  - agent: — | started: — | branch: p2
  - notes:
  - done: — | evidence: —

### [ ] P2-06 — Lever: prompt batching
- depends: P2-01
- what: Batch sentences/sections per call within token limits; measure parse-failure rate.
- acceptance: Isolated ablation row; failure rate reported.
  - agent: — | started: — | branch: p2
  - notes:
  - done: — | evidence: —

### [ ] P2-07 — Combine, sweep, frontier
- depends: P2-02..P2-06
- what: Evaluate combinations; produce cost-vs-quality frontier chart/table; report `e`, `s`, and net cost per configuration; choose operating point; ADR.
- acceptance: Frontier artifact generated by script; `e` and `s` included; ADR Proposed.
  - agent: — | started: — | branch: p2
  - notes:
  - done: — | evidence: —

### [ ] P2-08 — Lock config, regression tests, report
- depends: P2-07, P2-09
- what: Lock chosen config; tests for ledger logging and determinism; write docs/reports/P2-cascade.md including negative results, measured `e` and `s`, and a separately labeled projection section.
- acceptance: Report regenerable; measured/projected values separated; gate decision recorded in PROGRESS.
  - agent: — | started: — | branch: p2
  - notes:
  - done: — | evidence: —

### [ ] P2-09 — Cost projection script + report section
- depends: P2-05, P2-07
- what: Add `scripts/cost_model.py` that reads ledger measurements and projects to `N` papers (e.g., 1M, 20M) with ranges and sensitivity to `s`, `e`, tokens/paper, and prices. Output separates MEASURED from PROJECTED and prints assumptions.
- acceptance: Script reproduces the projection section; no hand-typed ledger numbers; assumptions and ranges printed; projection is never presented as a measurement.
  - agent: — | started: — | branch: p2
  - notes:
  - done: — | evidence: —

## Phase handoff log (append newest first)
<!-- Format: YYYY-MM-DD — agent — what changed — next step -->
- (empty)

## Phase exit checklist
- [ ] All tasks `[x]` or `[-]` with ADR
- [ ] Gate criteria evaluated honestly (see PRD)
- [ ] `docs/PROGRESS.md` phase table and headline numbers updated
- [ ] Report committed in `docs/reports/`
