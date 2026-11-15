# P1-10 baseline extraction — measured run

> **PARTIAL RUN:** stopped before the planned sample; this is not a baseline.

- Run id: `p1-10-ref-flash38-s20261114-n5`
- Provider/model: `gemini` / `gemini-3.8-flash`
- Config: thinking `default`, temperature `0.0`, max output `16384`, billing `free_tier`
- Prompt version: `claim-extraction-v1`
- Papers processed: **5**
- Accepted silver candidate claims: **74**
- Failures: **0** (structured output: 0; span not verbatim: 0)
- Evidence-span verbatim rate (accepted / extracted): **100.0%**
- Strict pre-normalization rate: **100.0%** (0 fixed by normalization)
- Calls: **5 succeeded**, **0 failed** (cache hits: 0)
- Tokens: prompt **28,087**, completion **22,073** (reasoning **9,177**), total **50,160**
- List-price cost at call-date price: **$0.103838**; post-promotion: **$0.207678**; real spend: **$0.000000**
- Cost per accepted claim (includes rejected-claim tokens): **$0.001403** (post-promotion **$0.002806**)
- Output-token share of list price (incl. thinking): **79.7%**
- Prompt-token gap vs chars/4 estimate: **-6.7%** (30,114 estimated)
- Free-tier requests today: **17/18** (RPD 20, margin 2); resume after **2026-11-16T00:00:00-08:00** if stopped.

## Per paper

| Metric | Mean | Median | p95 |
| :-- | --: | --: | --: |
| Prompt tokens | 5,617 | — | — |
| Completion tokens | 4,415 | — | — |
| Reasoning tokens | 1,835 | — | — |
| Total tokens | 10,032 | — | — |
| USD (call-date) | 0.020768 | 0.016531 | 0.032255 |

## Per-paper records

| Paper | Calls | Prompt | Completion | Reasoning | Total | USD | Post-promo USD | Latency ms |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| `PMC12178481` | 1 | 7,072 | 7,187 | 4,280 | 14,259 | 0.032255 | 0.064510 | 190215 |
| `PMC7577699` | 1 | 5,003 | 5,455 | 1,842 | 10,458 | 0.024208 | 0.048417 | 204967 |
| `PMC8866727` | 1 | 6,826 | 2,686 | 756 | 9,512 | 0.015192 | 0.030384 | 141218 |
| `PMC9463000` | 1 | 4,776 | 3,453 | 1,117 | 8,229 | 0.016531 | 0.033062 | 290982 |
| `PMC9806414` | 1 | 4,410 | 3,292 | 1,182 | 7,702 | 0.015652 | 0.031305 | 155560 |

Latency: mean **196588 ms**, p95 **290982 ms**.

Stopped reason: **max_calls_reached**.
Audit export: `-` (status `not_ready`; - claims, - papers; available 74 claims / 5 papers).

Silver candidates are training-only and are not gold labels.
