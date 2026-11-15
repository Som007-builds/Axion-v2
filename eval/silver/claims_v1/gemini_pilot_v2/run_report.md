# P1-10 baseline extraction — measured run

> **PARTIAL RUN:** stopped before the planned sample; this is not a baseline.

- Run id: `p1-10-gemini-validation-s20261114-n1`
- Provider/model: `gemini` / `gemini-3.8-flash`
- Config: thinking `medium`, temperature `0.0`, max output `16384`, billing `free_tier`
- Prompt version: `claim-extraction-v1`
- Papers processed: **0**
- Accepted silver candidate claims: **0**
- Failures: **1** (structured output: 0; span not verbatim: 0)
- Evidence-span verbatim rate (accepted / extracted): **100.0%**
- Strict pre-normalization rate: **100.0%** (0 fixed by normalization)
- Calls: **0 succeeded**, **2 failed** (cache hits: 0)
- Tokens: prompt **0**, completion **0** (reasoning **0**), total **0**
- List-price cost at call-date price: **$0.000000**; post-promotion: **$0.000000**; real spend: **$0.000000**
- Cost per accepted claim (includes rejected-claim tokens): **$0.000000** (post-promotion **$0.000000**)
- Output-token share of list price (incl. thinking): **0.0%**
- Prompt-token gap vs chars/4 estimate: **-100.0%** (7,589 estimated)
- Free-tier requests today: **12/18** (RPD 20, margin 2); resume after **2026-11-16T00:00:00-08:00** if stopped.

## Per paper

| Metric | Mean | Median | p95 |
| :-- | --: | --: | --: |
| Prompt tokens | 0 | — | — |
| Completion tokens | 0 | — | — |
| Reasoning tokens | 0 | — | — |
| Total tokens | 0 | — | — |
| USD (call-date) | 0.000000 | 0.000000 | 0.000000 |

## Per-paper records

| Paper | Calls | Prompt | Completion | Reasoning | Total | USD | Post-promo USD | Latency ms |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |

Latency: mean **0 ms**, p95 **0 ms**.

Stopped reason: **provider_failed**.

## Provider failure root cause

- Error class: `TransientProviderError`
- HTTP status: `504`; provider status: `DEADLINE_EXCEEDED`
- Finish reason: `None`
- Attempts made: 2
- Tokens: prompt None, completion None (thinking None)
- Message: `Gemini server error (504): {"error": {"code": 504, "message": "Deadline expired before operation could complete.", "status": "DEADLINE_EXCEEDED"}}`
Silver candidates are training-only and are not gold labels.
