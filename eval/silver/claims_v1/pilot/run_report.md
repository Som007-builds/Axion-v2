# P1-10 baseline extraction — measured run

> **PARTIAL RUN:** stopped before the planned sample; this is not a baseline.

- Run id: `p1-10-pilot-s20261114-n5`
- Papers processed: **1**
- Silver candidate claims: **21**
- Failures: **8** (structured output: 0; span not verbatim: 7)
- Evidence-span verbatim rate (accepted / extracted): **75.0%**
- Calls: **1 succeeded**, **1 failed** (cache hits: 0)
- Tokens: prompt **6,809**, completion **7,159** (reasoning **3,011**), total **13,968**
- List-price cost: **$0.005317**
- Prompt-token gap vs chars/4 estimate: **-10.3%** (7,589 estimated)

## Per paper

| Metric | Mean | Median | p95 |
| :-- | --: | --: | --: |
| Prompt tokens | 6,809 | — | — |
| Completion tokens | 7,159 | — | — |
| Reasoning tokens | 3,011 | — | — |
| Total tokens | 13,968 | — | — |
| USD | 0.005317 | 0.005317 | 0.005317 |

Latency: mean **16459 ms**, p95 **16459 ms**.

Stopped reason: **provider_failed**.
Provider detail: `Groq rate limit: request 12111 tokens exceeds TPM 8000`

Silver candidates are training-only and are not gold labels.
