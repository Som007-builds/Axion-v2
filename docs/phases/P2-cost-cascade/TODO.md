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

### [x] P2-02 — Lever: section targeting
- depends: P2-01
- what: Restrict extraction to configurable sections; measure delta cost, aligned precision, retention of gold baseline claims, unverifiable rate, and claim yield.
- acceptance: Isolated ablation row in results table.
  - agent: Buffy | started: 2026-11-16 | branch: p2
  - notes:
    - 2026-11-16 Buffy: section targeting applied **before the prompt is rendered** (`restrict_document` in `src/axion/extract/sections.py`), so `verify_claims` already rejects a claim naming an excluded section — no second guard needed. Named sets live in `src/axion/config/section_sets.yaml` (`all` = P1 behaviour, `core` = abstract/results/conclusion), selected with `--sections`.
    - Planned command (free tier, billing off, $0 real spend):
      `AXION_DRY_RUN=false python scripts/run_baseline_extraction.py --execute --sections core --run-id p2-02-sections-core-s20261114-n100 --silver-dir eval/silver/claims_v1/sections_core --out docs/reports/P2-02-sections-core --audit-out eval/audit/p2-02-sections-core.csv`
      (the `--audit-out` override keeps the official `claims_audit_v1.csv` untouched).
  - done: 2026-11-16 | evidence: commits `79bda17` (lever + tests) and `f21393a` (measured result); config `eval/ablation/configs/sections-core.json`, run `p2-02-sections-core-s20261114-n100`, report row in `docs/reports/P2-ablation.md`, run report `eval/silver/claims_v1/sections_core/run_report.md`.
  - **Measured (free tier, $0 real spend, 283 ledgered requests incl. retries):** 93 of 96 planned papers completed (3 lost to repeated 503/`SSLV3_ALERT_BAD_RECORD_MAC`, all recorded), **428 accepted claims (4.60/paper, 105 rejects)**. Cost **$0.002460613/paper vs $0.005644590 baseline = −56.4%**. Aligned precision dev **92.9%** [81.0–97.5], test **96.3%** [81.7–99.3]. **Retention 34.5%** (dev 40.8%, test 27.8%); unverifiable **59.7%**.
  - **Interpretation (negative result as a standalone lever):** precision survives within tolerance on the frozen test split (−0.6 pt), but retention collapses. Cause measured, not guessed: only **57 of 200 gold claims (28.5%)** sit in abstract/results/conclusion, because the gold sample is dominated by Methods/Introduction claims. The lever therefore buys 56% of the cost by discarding two thirds of the audited output; it is not a viable operating point alone and must be judged inside the P2-07 combination. The 59.5% retention gap is *not* recall — absolute recall remains unmeasured.
  - **Caveat:** `paper_count` in the config is **93**, the papers the ledger cost actually covers — not the 100 planned (3 papers failed permanently), so the $/paper figure is not diluted.
  - 2026-11-16 Buffy: the run was interrupted repeatedly by provider 503 spikes; each stop was the documented three-consecutive-failure checkpoint, and every resume skipped completed papers (no duplicate work, no duplicate claims). Verification: `ruff check .` clean, `ruff format --check .` clean, `mypy src/axion` clean (47 files), `pytest -q` **324 passed / 2 skipped**.

### [-] P2-03 — Lever: sentence-level claim filter (superseded)
- depends: P2-01
- what: Superseded by ADR-0008 on 2026-11-14. Original: embedding features + simple classifier trained on audited labels; threshold on dev; evaluate on test.
- acceptance: Superseded; use P2-03a/b/c (teacher-student track).
  - agent: — | started: — | branch: p2
  - notes:
    - 2026-11-14: replaced by ADR-0008; audited-label-only classifier was too small a lever for corpus scale.
  - done: — | evidence: ADR-0008.

### [~] P2-03a — Silver-label generation by teacher
- depends: P2-01, P1-10
- what: Budget-capped, dry-run-first teacher labeling on a **seeded sample of corpus papers excluding all 45 gold papers**; persist provenance (teacher model/version, prompt version, run_id); paper-level split; write to the silver-label store. Sample size is justified by the learning curve (P2-03c).
- acceptance: Dry-run estimate produced; sample size and seed recorded and justified from the learning curve; silver manifest + hashes committed (large labels may be external with manifest); **zero gold papers in the sample**; ledger stage `teacher_label`; daily-quota stop is clean and resumable.
  - agent: Buffy | started: 2026-11-16 | branch: p2
  - notes:
    - **Owner decisions (2026-11-16):** sample ceiling **300 teacher-labelled papers total**, excluding all 45 gold papers; the ~55 non-gold papers already labelled by the P1 baseline count toward it; nested seeded increments 50/100/200/300 with the learning curve deciding when to stop (stop early if it flattens); teacher stays `gemini-3.5-flash-lite` with the frozen baseline config and prompt v1.
    - Sample draw is a **prefix of one seeded permutation** (`sample_papers_excluding`, seed 20261114) after removing gold and already-labelled papers, so increments never re-label a paper. Gold exclusion is enforced by `--exclude-paper-ids`, not by eyeballing.
    - Planned increment command: `AXION_DRY_RUN=false python scripts/run_baseline_extraction.py --execute --sample 45 --exclude-paper-ids eval/audit/claims_audit_v1.csv --exclude-paper-ids eval/silver/claims_v1/baseline_flashlite/papers_processed.jsonl --run-id p2-03a-teacher-s20261114-n100 --silver-dir eval/silver/claims_v1/p2_03a_teacher --out docs/reports/P2-03a-dryrun --audit-out eval/audit/p2-03a-teacher.csv` (45 new papers brings the non-gold total to 100).
  - **Checkpoint 2026-11-16 (increment 1 of the 300 ceiling):** run `p2-03a-teacher-s20261114-n100` labelled **43 of 45 new papers** (2 lost to provider failures), **303 accepted silver claims**, 31 rejects, verbatim **92.7%**, **59 requests**, list price **$0.234809**, real spend **$0**. With the baseline's 55 non-gold papers this is **98 non-gold labelled papers** of the 300 ceiling. Sample plan: `docs/reports/P2-03a-sample.md` (draw verified gold-free: 0 gold, 0 already-labelled). Daily usage after this run: **342 of 450** requests.
  - **Why not closed:** the acceptance requires the sample size to be justified by the learning curve (P2-03c), which needs the student (P2-03b). Labelling continues in nested increments until the curve flattens or 300 is reached.
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
- 2026-11-16 — Buffy — P2-01 committed and verified; P2-02 section targeting measured (−56.4% $/paper, retention 34.5% → negative result standalone) — next: P2-03a teacher silver labelling (needs owner sign-off on sample size/dry-run)

## Phase exit checklist
- [ ] All tasks `[x]` or `[-]` with ADR
- [ ] Gate criteria evaluated honestly (see PRD)
- [ ] `docs/PROGRESS.md` phase table and headline numbers updated
- [ ] Report committed in `docs/reports/`
