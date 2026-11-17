# P2 — Cost cascade: phase report

**Status:** P2 COMPLETE — gate review needed.
**Branch:** `p2`. **Real spend for the whole phase: $0** (Gemini free tier, billing off; list price is
ledgered everywhere).

> **Gold measures precision only.** It labels 200 baseline claims from 45 papers (22 dev / 23 test,
> split by paper). Retention is agreement with the baseline's own output, **not recall**; absolute
> recall is unmeasured. Output aligning with no gold row is **unverifiable** and never counted as
> correct. Claims within a paper are not independent; 45 clusters is a small sample.

## Gate verdict (honest reading)

The PRD §P2 gate is ≥50% savings within 2 points of baseline precision, or a published negative
result plus the best frontier point.

- **Literal gate: PASS on two rows.** `escalation-length30` (−55.6% per paper, test precision 98.2%
  vs baseline 96.9%) and `sections-core` (−56.4%, test precision 96.3%).
- **The caveat that decides it:** both pass by emitting less. Test retention is **56.7%** for the
  escalation row and **27.8%** for section targeting. Under ADR-0021 (proposed, owner-pending) the
  gate also requires agreement with baseline, and no measured row reaches 90% retention.
- **Operating point proposed, not adopted:** ADR-0022 selects `p2-05-length30-v1`. Promotion is the
  owner's decision.

## Measured rows

From `docs/reports/P2-ablation.md` (all costs list price; real spend $0).

| Config | Papers | Claims | $/paper | Savings | Test precision | Test retention | Core retention |
| :-- | --: | --: | --: | --: | --: | --: | --: |
| `baseline` (P1 frozen) | 100 | 765 | $0.005644590 | — | 96.9% | 100.0% | 100.0% |
| `escalation-length30` | 45 | 410 | $0.002505111 | **55.6%** | **98.2%** | **56.7%** | 50.9% |
| `sections-core` | 93 | 428 | $0.002460613 | 56.4% | 96.3% | 27.8% | 59.6% |
| `batching` | 100 | 389 | $0.003518380 | 37.7% | 97.2% | 37.1% | 52.6% |
| `student-minilm` | 45 | 360 | local compute only | — | 100.0% | 30.9% | 28.1% |
| `flywheel-student` | 45 | 360 | local compute only | — | 96.2% | 26.8% | 29.8% |

## `e` and `s` (the two quantities the thesis turns on)

- **`e` (escalation rate) = 31.1%** measured (14 of 45 gold papers). Stage 2 never triggered on gold.
- **`s` (student cost ratio) = 0.29%** of baseline cost: 1,192 ms/paper measured on CPU, priced at an
  **ASSUMED** $0.05/CPU-hour (0.59% at $0.10/hour). The timing is a measurement; the CPU rate is not.

The planning model `relative_cost ≈ s + e` is borne out in structure but **`e` dominates**, exactly
as ADR-0008 predicted: `s` is negligible and the 55.6% saving is entirely "don't call the teacher on
70% of papers".

## Learning curve

Silver labels were added in nested seeded increments (50/100/200/300 ceiling, all 45 gold papers
excluded by construction). Quality was **flat from 10 to 98 labelled papers**, so labelling stopped at
**98 non-gold papers** rather than spending the 300-paper ceiling. This is a negative result for
"more teacher labels on this design buy retention" and is the reason P2-03a closed early
(`docs/reports/P2-student.md`).

## Flywheel

Retraining on escalated cases did **not** reduce `e`: held-out `e` stayed **8.3% → 8.3%** (1/12
both), mean held-out MRR fell 7.64% → 7.14%, and gold test retention moved 27.8% → 26.8%. Published
as a negative (`docs/reports/P2-05b-flywheel.md`).

## Negative results (kept deliberately)

1. **Confidence-based escalation fails.** Every student confidence feature is *negatively*
   correlated with per-paper retention (max-score rho −0.444, sentence count −0.682), so confidence
   escalation is worse than random at every rate. Length risk replaced it after this measurement.
2. **Section targeting buys cost by reading less.** −56.4% cost, 27.8% test retention; only 57 of 200
   gold claims live in abstract/results/conclusion.
3. **Batching fails the cost target** (−37.7%) and halves claim yield (389 vs 765). It introduced
   **zero** parse and zero attribution failures — the feared failure mode did not appear — and the
   request saving was erased by 503 retries (127 requests vs 120).
4. **Student-only is not a pipeline.** 30.9% test retention, 83.7% unverifiable; it needs escalation.
5. **Targeted flywheel labels do not lower `e`** (above).

## Projection (PROJECTED — never a measurement)

Full detail and assumptions: `docs/reports/P2-projection.md` (`python scripts/cost_model.py`, reading
the ledger, the escalation manifest and `pricing.yaml`; no typed-in numbers).

Headline projection at the measured `e = 31.1%`, including the stage-2 term: **$56,807 for 20M
papers** versus **$112,892** for the LLM-everywhere baseline (−49.7%). At `e = 5%` the projection is
**$9,408** (−91.7%); at `e = 50%`, **$91,096** (−19.3%). These are projections on a measured-cost
model, not measured costs at scale.

## Reproduction

```
python scripts/ablate.py --all --report docs/reports/P2-ablation.md
python scripts/frontier.py
python scripts/cost_model.py
python scripts/batching_report.py
python scripts/escalation_report.py
python scripts/flywheel_report.py
python scripts/audit_validate.py --audit eval/audit/claims_audit_v1.csv
```

## Limits

- One domain (infectious disease), one provider (Gemini free tier), one teacher model.
- `e` is measured on 45 gold papers; escalation on a different corpus is unknown.
- Stage 2 is projected from a zero-claim rate on other papers and a single dev probe call.
- Provider reliability during the phase was poor (43.2% HTTP 503 in one window,
  `docs/reports/P2-provider-reliability.md`); retries inflate request counts but not list price.
- Provider cost is list price; the free tier means real spend stayed $0, which flatters nothing but
  distorts nothing either — the ledger records what a paid tier would have charged.
