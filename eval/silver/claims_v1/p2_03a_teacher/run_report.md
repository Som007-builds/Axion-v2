# P1-10 baseline extraction — measured run

- Run id: `p2-03a-teacher-s20261114-n100`
- Provider/model: `gemini` / `gemini-3.5-flash-lite`
- Config: thinking `default`, temperature `0.0`, max output `16384`, billing `free_tier`
- Prompt version: `claim-extraction-v1`
- Papers processed: **43**
- Accepted silver candidate claims: **303**
- Failures: **31** (structured output: 0; span not verbatim: 24)
- Evidence-span verbatim rate (accepted / extracted): **92.7%**
- Strict pre-normalization rate: **92.7%** (0 fixed by normalization)
- Calls: **42 succeeded**, **16 failed** (cache hits: 1)
- Tokens: prompt **329,274**, completion **54,411** (reasoning **0**), total **383,685**
- List-price cost at call-date price: **$0.234809**; post-promotion: **$0.234809**; real spend: **$0.000000**
- Cost per accepted claim (includes rejected-claim tokens): **$0.000775** (post-promotion **$0.000775**)
- Output-token share of list price (incl. thinking): **57.9%**
- Prompt-token gap vs chars/4 estimate: **-7.2%** (354,831 estimated)
- Free-tier requests today: **342/450** (RPD 500, margin 50); resume after **2026-11-17T00:00:00-08:00** if stopped.

## Per paper

| Metric | Mean | Median | p95 |
| :-- | --: | --: | --: |
| Prompt tokens | 7,840 | — | — |
| Completion tokens | 1,296 | — | — |
| Reasoning tokens | 0 | — | — |
| Total tokens | 9,135 | — | — |
| USD (call-date) | 0.005591 | 0.005857 | 0.010723 |

## Per-paper records

| Paper | Calls | Prompt | Completion | Reasoning | Total | USD | Post-promo USD | Latency ms |
| :-- | --: | --: | --: | --: | --: | --: | --: | --: |
| `PMC10496059` | 1 | 502 | 9 | 0 | 511 | 0.000173 | 0.000173 | 1158 |
| `PMC12230139` | 1 | 7,785 | 3,556 | 0 | 11,341 | 0.011226 | 0.011226 | 8750 |
| `PMC2829052` | 1 | 13,425 | 1,658 | 0 | 15,083 | 0.008172 | 0.008172 | 14415 |
| `PMC5922582` | 1 | 7,805 | 1,761 | 0 | 9,566 | 0.006744 | 0.006744 | 4601 |
| `PMC6515764` | 1 | 6,306 | 654 | 0 | 6,960 | 0.003527 | 0.003527 | 2753 |
| `PMC6687105` | 1 | 9,121 | 473 | 0 | 9,594 | 0.003919 | 0.003919 | 2817 |
| `PMC7190200` | 1 | 6,344 | 270 | 0 | 6,614 | 0.002578 | 0.002578 | 1932 |
| `PMC7253235` | 1 | 8,771 | 1,441 | 0 | 10,212 | 0.006234 | 0.006234 | 11922 |
| `PMC7271637` | 1 | 5,078 | 955 | 0 | 6,033 | 0.003911 | 0.003911 | 6533 |
| `PMC7361108` | 1 | 11,583 | 2,180 | 0 | 13,763 | 0.008925 | 0.008925 | 18118 |
| `PMC7385074` | 1 | 13,319 | 799 | 0 | 14,118 | 0.005993 | 0.005993 | 2889 |
| `PMC7387962` | 1 | 6,236 | 2,132 | 0 | 8,368 | 0.007201 | 0.007201 | 12919 |
| `PMC7426715` | 1 | 2,894 | 388 | 0 | 3,282 | 0.001838 | 0.001838 | 3044 |
| `PMC7492153` | 1 | 6,404 | 1,008 | 0 | 7,412 | 0.004441 | 0.004441 | 10336 |
| `PMC7527165` | 1 | 8,698 | 1,658 | 0 | 10,356 | 0.006754 | 0.006754 | 5160 |
| `PMC7577345` | 1 | 3,965 | 1,019 | 0 | 4,984 | 0.003737 | 0.003737 | 3692 |
| `PMC7589163` | 1 | 14,475 | 1,738 | 0 | 16,213 | 0.008688 | 0.008688 | 7142 |
| `PMC7598432` | 1 | 4,830 | 382 | 0 | 5,212 | 0.002404 | 0.002404 | 2293 |
| `PMC7757982` | 1 | 11,852 | 917 | 0 | 12,769 | 0.005848 | 0.005848 | 3695 |
| `PMC7835451` | 1 | 15,401 | 1,265 | 0 | 16,666 | 0.007783 | 0.007783 | 5397 |
| `PMC8146492` | 1 | 4,605 | 546 | 0 | 5,151 | 0.002746 | 0.002746 | 2873 |
| `PMC8185501` | 1 | 7,789 | 1,413 | 0 | 9,202 | 0.005869 | 0.005869 | 4041 |
| `PMC8210659` | 1 | 6,003 | 1,498 | 0 | 7,501 | 0.005546 | 0.005546 | 4147 |
| `PMC8276232` | 1 | 16,579 | 1,048 | 0 | 17,627 | 0.007594 | 0.007594 | 3894 |
| `PMC8368209` | 1 | 10,585 | 2,604 | 0 | 13,189 | 0.009686 | 0.009686 | 11148 |
| `PMC8382023` | 1 | 2,944 | 408 | 0 | 3,352 | 0.001903 | 0.001903 | 2196 |
| `PMC8510587` | 1 | 1,895 | 608 | 0 | 2,503 | 0.002088 | 0.002088 | 10289 |
| `PMC8515140` | 1 | 8,192 | 1,721 | 0 | 9,913 | 0.006760 | 0.006760 | 5048 |
| `PMC8616654` | 1 | 5,805 | 1,650 | 0 | 7,455 | 0.005866 | 0.005866 | 4768 |
| `PMC8733512` | 1 | 814 | 138 | 0 | 952 | 0.000589 | 0.000589 | 1373 |
| `PMC8748708` | 1 | 6,657 | 2,281 | 0 | 8,938 | 0.007700 | 0.007700 | 5783 |
| `PMC8916227` | 1 | 14,305 | 1,722 | 0 | 16,027 | 0.008596 | 0.008596 | 4820 |
| `PMC8948605` | 1 | 13,309 | 3,358 | 0 | 16,667 | 0.012388 | 0.012388 | 12544 |
| `PMC9040802` | 1 | 12,836 | 2,749 | 0 | 15,585 | 0.010723 | 0.010723 | 7155 |
| `PMC9120986` | 1 | 1,618 | 139 | 0 | 1,757 | 0.000833 | 0.000833 | 8053 |
| `PMC9281210` | 1 | 9,675 | 490 | 0 | 10,165 | 0.004128 | 0.004128 | 7120 |
| `PMC9310377` | 1 | 1,801 | 1,774 | 0 | 3,575 | 0.004975 | 0.004975 | 4873 |
| `PMC9452130` | 1 | 5,023 | 1,097 | 0 | 6,120 | 0.004249 | 0.004249 | 5664 |
| `PMC9556962` | 1 | 8,483 | 2,392 | 0 | 10,875 | 0.008525 | 0.008525 | 9259 |
| `PMC9690223` | 1 | 5,106 | 302 | 0 | 5,408 | 0.002287 | 0.002287 | 9611 |
| `PMC9702704` | 1 | 16,194 | 915 | 0 | 17,109 | 0.007146 | 0.007146 | 3712 |
| `PMC9968613` | 1 | 4,262 | 1,295 | 0 | 5,557 | 0.004516 | 0.004516 | 3878 |

Latency: mean **6234 ms**, p95 **12919 ms**.

Stopped reason: **completed**.

## Provider failure root cause

- Error class: `TransientProviderError`
- HTTP status: `503`; provider status: `UNAVAILABLE`
- Finish reason: `None`
- Attempts made: 2
- Tokens: prompt None, completion None (thinking None)
- Message: `Gemini server error (503): {"error": {"code": 503, "message": "This model is currently experiencing high demand. Spikes in demand are usually temporary. Please try again later.", "status": "UNAVAILABLE"}}`

Audit export: `-` (status `not_ready`; - claims, - papers; available 303 claims / 40 papers).

Silver candidates are training-only and are not gold labels.
