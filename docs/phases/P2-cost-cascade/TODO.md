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

### [x] P2-03a — Silver-label generation by teacher
- depends: P2-01, P1-10
- what: Budget-capped, dry-run-first teacher labeling on a **seeded sample of corpus papers excluding all 45 gold papers**; persist provenance (teacher model/version, prompt version, run_id); paper-level split; write to the silver-label store. Sample size is justified by the learning curve (P2-03c).
- acceptance: Dry-run estimate produced; sample size and seed recorded and justified from the learning curve; silver manifest + hashes committed (large labels may be external with manifest); **zero gold papers in the sample**; ledger stage `teacher_label`; daily-quota stop is clean and resumable.
  - agent: Buffy | started: 2026-11-16 | branch: p2
  - notes:
    - **Owner decisions (2026-11-16):** sample ceiling **300 teacher-labelled papers total**, excluding all 45 gold papers; the ~55 non-gold papers already labelled by the P1 baseline count toward it; nested seeded increments 50/100/200/300 with the learning curve deciding when to stop (stop early if it flattens); teacher stays `gemini-3.5-flash-lite` with the frozen baseline config and prompt v1.
    - Sample draw is a **prefix of one seeded permutation** (`sample_papers_excluding`, seed 20261114) after removing gold and already-labelled papers, so increments never re-label a paper. Gold exclusion is enforced by `--exclude-paper-ids`, not by eyeballing.
    - Planned increment command: `AXION_DRY_RUN=false python scripts/run_baseline_extraction.py --execute --sample 45 --exclude-paper-ids eval/audit/claims_audit_v1.csv --exclude-paper-ids eval/silver/claims_v1/baseline_flashlite/papers_processed.jsonl --run-id p2-03a-teacher-s20261114-n100 --silver-dir eval/silver/claims_v1/p2_03a_teacher --out docs/reports/P2-03a-dryrun --audit-out eval/audit/p2-03a-teacher.csv` (45 new papers brings the non-gold total to 100).
  - **Checkpoint 2026-11-16 (increment 1 of the 300 ceiling):** run `p2-03a-teacher-s20261114-n100` labelled **43 of 45 new papers** (2 lost to provider failures), **303 accepted silver claims**, 31 rejects, verbatim **92.7%**, **59 requests**, list price **$0.234809**, real spend **$0**. With the baseline's 55 non-gold papers this is **98 non-gold labelled papers** of the 300 ceiling. Sample plan: `docs/reports/P2-03a-sample.md` (draw verified gold-free: 0 gold, 0 already-labelled). Daily usage after this run: **342 of 450** requests.
  - **Sample closed (2026-11-17):** the P2-03c curve is flat from 10 to 98 papers, so the acceptance condition "justified by the learning curve" is met at **98 non-gold papers**; labelling stopped below the 300 ceiling by design.
  - done: 2026-11-17 | evidence: dry run `docs/reports/P2-03a-dryrun.{md,json}`; plan `docs/reports/P2-03a-sample.md` (seed **20261114**, 0 gold and 0 already-labelled papers in the draw); run manifests/hashes committed in `eval/silver/claims_v1/p2_03a_teacher/` (labels themselves external, ignored); ledger stage `teacher_label`; quota stop/resume is the tested runner path and no 429 occurred. **Sample closed at 98 non-gold papers** (55 P1 + 43 P2-03a) because the P2-03c curve is flat from 10 to 98 papers — see `docs/reports/P2-student.md`. Two planned papers were lost to provider failures and are recorded; they were not replaced because the curve did not justify more labelling.

### [x] P2-03b — Train claim-sentence student + gold evaluation
- depends: P2-03a
- what: Train a small encoder on the silver TRAIN split; tune thresholds on gold DEV; report on frozen gold TEST; record student version/hash. Never evaluate on teacher-labeled data.
- acceptance: Gold-test aligned precision, **retention of gold baseline claims**, and unverifiable rate with CIs; absolute recall is reported as **unmeasured**; no paper overlap between train and gold dev/test; isolated ablation row; model metadata/hash recorded.
  - agent: opencode | started: 2026-11-17 | branch: p2
  - notes:
    - 2026-11-17: claimed. Train papers = the **98 non-gold** papers (88 with teacher claims; 55 P1 baseline non-gold + 43 P2-03a); all 45 gold papers excluded by ID and asserted in the split manifest.
    - Student = `all-MiniLM-L6-v2` sentence encoder + binary sentence head. Negatives are all other sentences in the same papers (teacher omissions are label noise, documented).
    - Operating point is chosen on **gold dev only** by a rule fixed before test scoring; the frozen test split is scored once.
    - **Design finding (negative):** frozen MiniLM embeddings + logistic head top out at **25–31% retention** of audited claims at the baseline claim budget. End-to-end listwise fine-tuning doubled held-out silver agreement (12.4% → 25.8% recall@8) but did not move the gold point enough to justify its 48-minute CPU run (29.1% vs 27.2% at k=8; two rows), so the simpler frozen-encoder student ships.
    - Functional context features (paper title, section, neighbours, abstract similarity) and section quotas were tested on dev and did not improve the point.
    - **Interpretation:** the teacher labels only ~4% of sentences and omits many claim-like sentences, so a sentence selector learns "claim-like" rather than the teacher's salience ranking. The student is a negative result on its own; it is carried into P2-05 escalation and P2-07, not adopted.
  - done: 2026-11-17 | evidence: `python scripts/train_student.py` → **98 non-gold papers, 16,452 sentences, 650 positives**; frozen gold **test retention 30.9% (30/97)**, aligned precision **100.0% [88.6–100]**, unverifiable **83.7%**, 184 claims; dev **25.2%**, precision 100.0% [87.1–100]. Inference **1,278 ms/paper CPU** (parse+split+encode+score), no LLM calls, no ledger cost. Harness row `student-minilm` (`scripts/ablate.py --config student-minilm`): 45 papers, 360 claims, retention **0.280**. Artifact `eval/student/student_v1.model.json` SHA-256 `e6ac79d6…`, manifest with all 98 train paper IDs and the excluded-gold hash. Report `docs/reports/P2-student.md`. 12 offline tests in `tests/test_student.py`; suite **342 passed / 2 skipped**; ruff/format/mypy clean.

### [x] P2-03c — Learning curve
- depends: P2-03b
- what: Measure student quality vs. number of silver labels at geometric steps up to the label budget; report marginal value.
- acceptance: Curve/table generated by script; budgets and assumptions recorded; negative result published if it plateaus.
  - agent: opencode | started: 2026-11-17 | branch: p2
  - notes:
    - Curve is a **nested prefix of one seeded paper order** (seed 20261117) at 10, 20, 35, 50, 70, 83, 98 papers, so each point adds labels to the previous point rather than resampling.
    - Quality is measured on gold **dev** only (test never enters the curve): retention@8, retention@20, precision@8. `scripts/train_student.py --skip-curve` disables it.
    - **Plateau:** retention@8 is 23.3% → 25.2% and retention@20 is 45.6% → 56.3% between 10 and 98 papers, with no monotone trend; precision stays 96–100%. More teacher labels at this design do not buy retention, so the owner's 300-paper ceiling was not spent.
    - This is a negative result and is published in `docs/reports/P2-student.md`; it is the justification for closing P2-03a at 98 papers.
  - done: 2026-11-17 | evidence: curve table in `docs/reports/P2-student.md` §Learning curve, generated by `python scripts/train_student.py`; budgets (98-paper cap, 8 claims/paper) and the seed recorded in the student manifest.

### [x] P2-04 — Lever: cache and dedup
- depends: P2-01
- what: Content-hash keys; near-duplicate sentence dedup; measure hit rates on re-runs and across papers.
- acceptance: Hit-rate report; ledger shows $0 cache hits.
  - agent: opencode | started: 2026-11-17 | branch: p2
  - notes:
    - 2026-11-17: claimed. The client already has a persistent content-hash cache (`src/axion/llm/cache.py`) keyed over prompt, system, model, decoding params, schema and thinking level; a hit is written to the ledger with `cache_hit=true` at `$0`.
    - Evidence is two-sided: (a) a **re-run probe** of already-cached papers under a new run id (0 provider calls, 0 new cache rows, 100% hits, `$0`); (b) a **cross-paper duplicate census** with exact and near-duplicate (shingle Jaccard) measures and the token share that dedup could remove.
    - **Cache is a real but narrow lever.** A timed re-run of the first 5 frozen baseline papers under `p2-04-cache-probe` produced **5 ledger rows, 5 cache hits, 0 provider calls, 0 tokens, $0.000000**; the cache table stayed at **238 rows**, so every probe call was a read hit. Across all runs, **9 of 486 ledger attempts** are cache hits and **0** of them carry a non-zero price.
    - **Dedup is not material on this sample.** 16,466 sentences → **190 duplicate copies (1.15%)**: 175 exact and 15 near at Jaccard 0.9, split **174 within-paper / 16 cross-paper**; ≈**5,963 prompt tokens** (upper bound, a projection). At 0.8 the count rises only to 199 / 6,507 tokens. Within-paper exact repeats (abstract/results duplication) dominate, so dedup cannot buy a large share of the prompt.
    - Dedup is therefore **measured, not applied**. Applying it would change the evidence a prompt sees and needs its own live run and quality row; the safer target is within-paper duplicates, which cannot remove a unique claim.
    - The probe's one recorded `failures.jsonl` row is a teacher **verification reject** (`evidence_span_not_verbatim`), not a provider failure, and does not affect the hit count.
  - done: 2026-11-17 | evidence: `docs/reports/P2-04-cache-dedup.md` (generated by `python scripts/cache_dedup_report.py`); probe provenance `docs/reports/P2-04-cache-probe.{md,json}` + `eval/silver/claims_v1/cache_probe/`; ledger query shows 5/5 hits, `usd=0`, 0 tokens, 0 priced hits; cache table unchanged at 238. New deterministic helper `src/axion/extract/dedup.py` (normalized exact key + MinHash/LSH/Jaccard) with **9 offline tests** in `tests/test_dedup.py`; suite **351 passed / 2 skipped**; ruff/format/mypy clean.

### [x] P2-05 — Lever: calibrated escalation
- depends: P2-01, P2-03b
- what: Define confidence/agreement signals and calibrated or conformal thresholds; escalate low-confidence items to a small LLM, then a large LLM. Measure escalation rate `e`, escalation cost, and net cost; log `parent_call_id`.
- acceptance: Isolated ablation row; escalation rule + calibration documented; `e` measured; net cost reported.
  - agent: opencode | started: 2026-11-17 | branch: p2
  - notes:
    - Stage 0 is the frozen `student-v1-minilm-lr` (top-8); stage 1 is the frozen P1 `gemini-3.5-flash-lite` teacher; stage 2 is `gemini-3.8-flash`, triggered only when stage 1 accepts no claim. No model or tier was changed.
    - The planned confidence signals were calibrated on dev first and **failed**: mean top score rho -0.386, max score -0.444, entropy -0.072 vs per-paper retention. Low confidence predicts *more* retention, so confidence escalation is worse than random at every rate. The shipped rule is the only signal that beat random: escalate the longest 30% of papers (sentence count, rho -0.682).
    - Rule frozen at `ESCALATION_FRACTION=0.30` before the test read (`p2-05-length30-v1`). Dev q=0.30: e=31.8%, retention 57.3%, savings 58.7%, vs random 49.2% retention. Test (read once): e=30.4%, retention 56.7% (55/97), precision 98.2% [90.4-99.7], savings 61.6%.
    - Overall: e=31.1% (14/45), $0.002505/paper vs $0.006282 baseline (-60.1%), $/retained $0.000989 vs $0.001413. Real spend $0: stage 1 replayed cached teacher output at list price, not cache $0.
    - Stage 2 never fired on gold (0/14); teacher zero-claim base rate 10/98 (10.2%) projects a 3.2% stage-2 rate, +$0.000335/paper, savings 54.8% (intro price). A dev mechanism probe (calls 487->488) proves `parent_call_id` is ledgered: stage 1 $0 cache hit, stage 2 6,703+2,624 tokens, $0.014867 list price, real spend $0; using that unit cost gives 52.6% savings. Probe output discarded and not scored.
    - `s=0` in LLM terms; student inference 1,180 ms/paper CPU (parse+split+encode+score); projected 0.29%/0.58% of baseline at $0.05/$0.10 per CPU-hour. Precision survives; retention does not. The owner should decide at P2-07 whether 56.7% test retention is acceptable.
  - done: 2026-11-17 | evidence: `python scripts/escalation_report.py` -> `docs/reports/P2-05-escalation.md`, `eval/escalation/run_manifest.json`, `eval/escalation/paper_signals.json`; harness row `escalation-length30` (`scripts/ablate.py --all`): 45 papers, 410 claims, dev precision 0.983, test 0.982, retention 0.570, $0.002505/paper; derived ledger 15 rows/14 papers/$0.112730 list price (baseline run); probe ledger rows 487->488; 7 offline tests `tests/test_escalation.py`.

### [x] P2-05b — Flywheel experiment
- depends: P2-05, P2-03c
- what: Retrain the student including escalated cases as new silver labels; measure whether `e` drops and whether gold-test quality holds.
- acceptance: Before/after `e` and gold-test quality reported; provenance of new labels recorded; negative result published if no improvement.
  - agent: opencode | started: 2026-11-17 | branch: p2
  - notes:
    - **Gold-free design:** base student = 55 P1 non-gold papers; flywheel pool = 40 P2-03a non-gold papers with at least one accepted claim. Pool split 28 candidate / 12 held-out (seed `20261118`); only candidate labels can be added. Gold is evaluation only; no LLM call was made (cached teacher labels).
    - **Agreement signal:** per-paper mean reciprocal rank (MRR) of teacher-positive sentences in the student's full ranking. A binary top-8 recall signal was tried first and was degenerate: 12/28 candidate papers tied at zero, so the realised threshold escalated 42.9% and held-out `e` rose 33.3% -> 41.7%. MRR was chosen on the non-gold candidate pool, before the reported run; the gold test was not used to choose the signal.
    - **Reported run:** threshold `0.0339` (30% low tail); selected **8/28** candidate papers (28.6%) -> **1,890 sentences / 77 positive sentences** added to the base. Held-out `e` **8.3% -> 8.3%** (1/12 both); mean held-out MRR 7.64% -> 7.14%. Gold dev retention 25.2% -> 26.2%; **gold test retention 27.8% -> 26.8% (-1.0 point)**, test precision 96.3% -> 96.2%, unverifiable 85.3% -> 85.9%. The frozen 98-paper `student_v1` reference is 30.9% / 100.0% on test. **Negative result:** targeted labels did not reduce `e` and did not hold test retention.
    - **Provenance:** selected IDs and label counts in `eval/flywheel/run_manifest.json`; label source `p2-03a-teacher-s20261114-n100`; base/flywheel artifacts SHA-256 recorded. The flywheel does not replace the frozen `student_v1`.
  - done: 2026-11-17 | evidence: `python scripts/flywheel_report.py` -> `docs/reports/P2-05b-flywheel.md`, `eval/flywheel/run_manifest.json`, `eval/flywheel/base.model.json`, `eval/flywheel/flywheel.model.json`; harness row `flywheel-student` (`scripts/ablate.py --all`): 45 papers, 360 claims, dev precision 1.000, test precision 0.9615, retention **0.265**; 5 offline tests in `tests/test_flywheel.py`; no new LLM calls, real spend **$0**.

### [x] P2-06 — Lever: prompt batching
- depends: P2-01
- what: Batch sentences/sections per call within token limits; measure parse-failure rate.
- acceptance: Isolated ablation row; failure rate reported.
  - agent: opencode | started: 2026-11-17 | branch: p2
  - notes:
    - **Design:** the frozen baseline is one paper per call, so the tested lever is a new batch prompt (`claim-extraction-batch-v1`) that packs several papers into one call with explicit `=== PAPER <id> ===` delimiters and asks for a per-claim `paper_id`. The baseline prompt stays frozen. Batches of 3 papers on the 45 gold papers (15 calls) keep output well under 16,384 tokens and stay inside the 15 RPM / 450 RPD free tier. Cost is token-based, so the expected saving is only the shared instruction overhead; the real question is whether attribution/parse failures stay low.
  - done: 2026-11-17 | evidence: run `p2-06-batch3-s20261114-n100`; `python scripts/batching_report.py` → `docs/reports/P2-06-batching.md`; harness row `batching` via `python scripts/ablate.py --all`; 6 offline tests in `tests/test_batching.py`.
  - **Measured (free tier, $0 real):** 100/100 papers, **389 claims (3.89/paper vs baseline 7.65)**, **127 requests incl. retries vs 120 baseline**, 84 failed requests, **0 parse failures, 0 `unknown_paper` attribution failures**, 50 verbatim-span rejects, list price **$0.351838** = **$0.003518380/paper vs $0.005644590 = −37.7%**. Quality: dev precision 97.0%, test 97.2%, **retention 34.5%** (test 37.1%), core retention **52.6%**, unverifiable 57.7%.
  - **Negative result.** The saving is not efficiency: output tokens dominate baseline cost (62.9%), so halving claim yield is what halves the bill. Two secondary findings: (a) batching introduced **no** attribution or parse failures, so the expected failure mode did not appear; (b) the operational win did not materialise either — 43 batches became 127 requests because retries cost more than the packing saved, slightly *worse* than the baseline's 120. Do not adopt batching on this evidence; keep the row for P2-07.
  - **Caveat:** the 3-paper batch reaches 43 batches rather than 34 because greedy packing splits on the 24K-token ceiling; the dry run predicted −2.6% prompt tokens (744,544 vs 764,084), and the realised drop is dominated by shorter output.

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
- 2026-11-17 — opencode — P2-05b flywheel negative: MRR threshold selected 8/28, held-out e 8.3→8.3%, test retention 27.8→26.8%, precision 96.3→96.2%, $0 — next: P2-06 batching
- 2026-11-17 — opencode — P2-03a closed at 98 gold-free papers (flat curve); P2-03b student trained and scored once on frozen test (retention 30.9%, precision 100%, unverifiable 83.7% → negative on its own); P2-03c curve flat, negative published — next: P2-04 cache/dedup
- 2026-11-16 — Buffy — P2-01 committed and verified; P2-02 section targeting measured (−56.4% $/paper, retention 34.5% → negative result standalone) — next: P2-03a teacher silver labelling (needs owner sign-off on sample size/dry-run)

## Phase exit checklist
- [ ] All tasks `[x]` or `[-]` with ADR
- [ ] Gate criteria evaluated honestly (see PRD)
- [ ] `docs/PROGRESS.md` phase table and headline numbers updated
- [ ] Report committed in `docs/reports/`
