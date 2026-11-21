# P3-06 oracle — does the right source sentence help the detector?

**Written by `scripts/p3_06_oracle.py` from the owner's labels and the ledger. The
dev-only oracle test pre-registered in ADR-0027, not a gate result.**

## What was swapped

- Packet: **30** rows: 14 positives,  16 negatives.
- Treatment arm (a sentence the owner picked): **22** rows.
- Answered `none`: **6** rows, no supporting sentence.
- Untestable (source has no body text): **2** rows.
- Labels from: soham.

Only the claim block changed. Same prompt, same schema, same model, same threshold.

## At threshold 30

| | positives caught | negatives fired |
|---|---|---|
| before (abstract proxy) | 6 of 11 | 2 of 11 |
| after (owner's sentence) | 6 of 11 | 2 of 11 |

**2 rows crossed the threshold** in either direction; 18 of 22 rows scored exactly the same. The counts above are net, so a gain and a loss cancel: the crossings are named under *What moved* instead of being netted away.

Thirty rows can show a direction and not an effect size; no interval is quoted,
because none would be informative at this n.

## What moved: 4 of 22 rows

| row | gold | before | after | delta | crossed |
|---|---|---|---|---|---|
| P3W1-007 | RELIES_ON | 50 | 92 | +42 | no |
| P3W2-068 | MENTIONS | 33 | 58 | +25 | no |
| P3W1-058 | RELIES_ON | 25 | 33 | +8 | yes |
| P3W2-052 | RELIES_ON | 33 | 25 | -8 | yes |

## A gold positive with no supporting sentence

`P3W1-063` was answered `none`: reading the whole body, the
owner found no sentence that citing text depends on. That is a statement about the
gold label, not about the model, and it is left standing rather than re-scored.

## The pre-committed gate

**Not built.** Positives caught moved by +0 and negatives fired by +0; the rule says no movement means link quality is not the ceiling, so the linker is not built.

The P3-05 dev-negative (ADR-0026 Amendment C) therefore stands unchanged, and the
frozen test set is untouched.

## Cost, from the ledger

- 22 attempts, 22 succeeded, 0 errors, 0 cache hits.
- 15368 prompt + 1808 completion tokens.
- **$0.009129** at list price, free tier, no charge.
- Estimate before the run: $0.010718 for 22 requests.

## Per row

| row | gold | before | after | delta | heuristic |
|---|---|---|---|---|---|
| P3W2-068 | MENTIONS | 33 | 58 | 25 | 1.0 |
| P3W1-009 | MENTIONS | 25 | 25 | 0 | 0.0 |
| P3W2-042 | MENTIONS | 25 | 25 | 0 | 0.8 |
| P3W2-031 | MENTIONS | 50 | 50 | 0 | -1.0 |
| P3W2-066 | MENTIONS | 25 | 25 | 0 | -1.2 |
| P3W1-034 | RELIES_ON | 25 | 25 | 0 | -1.2 |
| P3W1-069 | RELIES_ON | 25 | 25 | 0 | 0.2 |
| P3W1-058 | RELIES_ON | 25 | 33 | 8 | 0.2 |
| P3W1-025 | RELIES_ON | 25 | 25 | 0 | 0.2 |
| P3W2-003 | MENTIONS | 25 | 25 | 0 | -0.2 |
| P3W1-014 | RELIES_ON | 25 | 25 | 0 | -0.2 |
| P3W2-052 | RELIES_ON | 33 | 25 | -8 | 0.0 |
| P3W1-070 | RELIES_ON | 75 | 75 | 0 | 0.0 |
| P3W1-066 | MENTIONS | 25 | 25 | 0 | 0.0 |
| P3W1-026 | RELIES_ON | 33 | 33 | 0 | 0.2 |
| P3W2-045 | MENTIONS | 25 | 25 | 0 | -0.2 |
| P3W2-047 | MENTIONS | 25 | 25 | 0 | -0.2 |
| P3W1-007 | RELIES_ON | 50 | 92 | 42 | 1.0 |
| P3W2-008 | MENTIONS | 25 | 25 | 0 | -0.2 |
| P3W1-065 | RELIES_ON | 50 | 50 | 0 | 0.0 |
| P3W1-033 | RELIES_ON | 33 | 33 | 0 | 0.8 |
| P3W2-006 | MENTIONS | 25 | 25 | 0 | 0.8 |
