# P1 baseline extraction — dry-run plan (ESTIMATE)

**No extractor was run and no LLM call was made.** This plan parses real
corpus text and estimates prompt tokens; the claims/paper rate is a scenario,
not a measurement. Prices are blank, so no dollar cost is stated.

## Sample

- Requested papers: 100
- Usable papers with baseline text: 100
- Missing full text: 0
- Parse failures: 0
- Empty baseline documents: 0
- Seed: 20261114; prompt version: `claim-extraction-v1`

## Prompt tokens (estimate)

| Mean | Median | p95 |
| --: | --: | --: |
| 7,641 | 6,971 | 15,867 |

Total for 100 calls: **764,084** prompt tokens (chars/4 heuristic).

## Expected claims and output tokens

| Claims/paper (assumed) | Expected claims | Output tokens |
| --: | --: | --: |
| 2 | 200 | 24,000 |
| 5 | 500 | 60,000 |
| 10 | 1,000 | 120,000 |

## Size recommendation

- Clears 200 claims at 5 claims/paper: **True**
- Recommended sample: **100 papers** (seeded, paper-level, uniform over corpus papers with full text).
- The recommendation is based on the conservative 5-claims/paper scenario;
  the paid run must record the observed rate and may stop early only with
  owner approval.

## Method

Token counts are ceil(characters/4) over the rendered prompt (baseline sections plus instructions). Output assumes 120 tokens per claim. Claims/paper is a scenario, not a measurement; no extractor has run.

## Cost

not computed: pricing.yaml is blank; no paid call is authorized
Formula once prices exist: `input_tokens * input_price_per_Mtok / 1e6 + output_tokens * output_price_per_Mtok / 1e6`.

## Owner inputs required before the paid run

1. Provider hosting for the chosen large tier (tier IDs are configured in `.env`).
2. Verified input/output prices in `src/axion/config/pricing.yaml`.
3. A paid budget cap in `_private/budget.md`.
4. Approval to install the chosen provider SDK (no adapter ships here).
