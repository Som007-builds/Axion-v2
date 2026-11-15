# P1-10 baseline extraction — measured run

> **PARTIAL RUN:** stopped before the planned sample; this is not a baseline.

- Run id: `p1-10-gemini-pilot-s20261114-n5`
- Provider/model: `gemini` / `gemini-3.8-flash`
- Config: thinking `medium`, temperature `0.0`, max output `8192`, billing `free_tier`
- Prompt version: `claim-extraction-v1`
- Papers processed: **0**
- Accepted silver candidate claims: **0**
- Failures: **3** (structured output: 0; span not verbatim: 0)
- Evidence-span verbatim rate (accepted / extracted): **100.0%**
- Strict pre-normalization rate: **100.0%** (0 fixed by normalization)
- Calls: **0 succeeded**, **10 failed** (cache hits: 0)
- Tokens: prompt **0**, completion **0** (reasoning **0**), total **0**
- List-price cost at call-date price: **$0.000000**; post-promotion: **$0.000000**; real spend: **$0.000000**
- Cost per accepted claim (includes rejected-claim tokens): **$0.000000** (post-promotion **$0.000000**)
- Output-token share of list price (incl. thinking): **0.0%**
- Prompt-token gap vs chars/4 estimate: **-100.0%** (30,114 estimated)
- Free-tier requests today: **10/18** (RPD 20, margin 2); resume after **2026-11-16T00:00:00-08:00** if stopped.

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
Provider detail: `TransientProviderError: Gemini server error (503): {"error": {"code": 503, "message": "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.", "status": "UNAVAILABLE"}}`

Silver candidates are training-only and are not gold labels.
