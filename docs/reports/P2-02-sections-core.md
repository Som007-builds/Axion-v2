# P1 baseline extraction — dry-run plan (ESTIMATE)

**No extractor was run and no LLM call was made.** This plan parses real
corpus text and estimates prompt tokens; the claims/paper rate is a scenario,
not a measurement. Prices are verified for the paid run, but this file is
not a cost measurement.

## Sample

- Requested papers: 100
- Usable papers with baseline text: 96
- Missing full text: 0
- Parse failures: 0
- Empty baseline documents: 4
- Seed: 20261114; prompt version: `claim-extraction-v1`

## Prompt tokens (estimate)

| Mean | Median | p95 |
| --: | --: | --: |
| 2,015 | 1,495 | 5,218 |

Total for 96 calls: **193,430** prompt tokens (chars/4 heuristic).

## Expected claims and output tokens

| Claims/paper (assumed) | Expected claims | Output tokens |
| --: | --: | --: |
| 2 | 192 | 23,040 |
| 5 | 480 | 57,600 |
| 10 | 960 | 115,200 |

## Size recommendation

- Clears 200 claims at 5 claims/paper: **True**
- Recommended sample: **96 papers** (seeded, paper-level, uniform over corpus papers with full text).
- The recommendation is based on the conservative 5-claims/paper scenario;
  the paid run must record the observed rate and may stop early only with
  owner approval.

## Method

Token counts are ceil(characters/4) over the rendered prompt (baseline sections plus instructions). Output assumes 120 tokens per claim. Claims/paper is a scenario, not a measurement; no extractor has run.

## Cost

not computed here: this is a dry-run estimate; the paid run records actual list-price cost in the ledger
Formula used by the paid run: `input_tokens * input_price_per_Mtok / 1e6 + output_tokens * output_price_per_Mtok / 1e6`.

## Owner inputs status

1. Provider hosting: Google Gemini free tier via AI Studio.
2. Baseline model: `gemini-3.5-flash-lite` (ADR-0019); `gemini-3.8-flash` is a reference-only model, not the baseline.
3. Prices: official Google list prices, checked 2026-11-15; free-tier calls record list price with `billing=free_tier` and real spend $0.
4. Free-tier limits: 3.5 Flash-Lite 15 RPM / 250K TPM / 500 RPD (runner cap 450/day); 3.8 Flash 5 RPM / 250K TPM / 20 RPD. RPD resets at midnight Pacific.
5. SDK: the official `google-genai==2.8.0` package is pinned and installed behind `src/axion/llm/gemini.py`.
