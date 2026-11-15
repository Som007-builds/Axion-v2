# P1 baseline extraction — dry-run plan (ESTIMATE)

**No extractor was run and no LLM call was made.** This plan parses real
corpus text and estimates prompt tokens; the claims/paper rate is a scenario,
not a measurement. Prices are verified for the paid run, but this file is
not a cost measurement.

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

not computed here: this is a dry-run estimate; the paid run records actual list-price cost in the ledger
Formula used by the paid run: `input_tokens * input_price_per_Mtok / 1e6 + output_tokens * output_price_per_Mtok / 1e6`.

## Owner inputs status

1. Provider hosting: Groq `openai/gpt-oss-120b` (large tier).
2. Prices: filled in `src/axion/config/pricing.yaml` from the official Groq
   model pages, checked 2026-11-15.
3. Budget: a $3 total P1-10 cap is recorded in the untracked private budget file.
4. SDK: the official `groq==1.7.0` package is approved, pinned, and installed
   behind `src/axion/llm/groq.py`.
5. Remaining blocker: the Groq free tier allows 8,000 tokens per minute and
   200,000 per day; this plan's mean prompt is 7,641 tokens and its p95 is
   15,867, so the paid run cannot complete without an owner decision on the
   limit, provider, or sampling rule.
