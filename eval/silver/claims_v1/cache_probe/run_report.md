# P1-10 baseline extraction — measured run

- Run id: `p2-04-cache-probe`
- Provider/model: `gemini` / `gemini-3.5-flash-lite`
- Config: thinking `default`, temperature `0.0`, max output `16384`, billing `free_tier`
- Prompt version: `claim-extraction-v1`
- Papers processed: **5**
- Accepted silver candidate claims: **51**
- Failures: **1** (structured output: 0; span not verbatim: 1)
- Evidence-span verbatim rate (accepted / extracted): **98.1%**
- Strict pre-normalization rate: **98.1%** (0 fixed by normalization)
- Calls: **0 succeeded**, **0 failed** (cache hits: 5)
- Tokens: prompt **0**, completion **0** (reasoning **0**), total **0**
- List-price cost at call-date price: **$0.000000**; post-promotion: **$0.000000**; real spend: **$0.000000**
- Cost per accepted claim (includes rejected-claim tokens): **$0.000000** (post-promotion **$0.000000**)
- Output-token share of list price (incl. thinking): **0.0%**
- Prompt-token gap vs chars/4 estimate: **-100.0%** (30,114 estimated)
- Free-tier requests today: **5/450** (RPD 500, margin 50); resume after **2026-11-18T00:00:00-08:00** if stopped.

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

Stopped reason: **completed**.
Audit export: `-` (status `not_ready`; - claims, - papers; available 51 claims / 5 papers).

Silver candidates are training-only and are not gold labels.
