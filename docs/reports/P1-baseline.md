# P1 baseline — measured claim extraction

**Status: extraction measured; audited precision pending owner labels.** The PRD
P1 gate ("baseline report exists with audited precision") is not yet passed:
every extraction number below is measured, but precision needs the P1-11 audit
in `eval/audit/claims_audit_v1.csv`, which has no labels yet.

Everything here is generated from the run artifacts and the ledger; no number
was hand-tuned. Source of record: `eval/silver/claims_v1/baseline_flashlite/run_report.json`
(regenerate with the run command in §7).

## 1. Run and provenance

| Item | Value |
| :-- | :-- |
| Run id | `p1-10-flashlite-s20261114-n100` |
| Date | 2026-11-15 |
| Provider / model | `gemini` / `gemini-3.5-flash-lite` (ADR-0019) |
| Tier | `small` |
| Prompt | `claim-extraction-v1` |
| Generation config | thinking `default` (no `thinking_config`), temperature `0.0`, max output `16,384` |
| Retry policy | network/5xx at most once, every attempt paced |
| Billing | `free_tier` — list price recorded, **real spend $0.00** |
| Sampling | seeded paper sample, `seed=20261114`, `--sample 100`, seeded order |
| Corpus manifest SHA-256 | `a8f745022d4ade9db6b50f2866e1b14d01116649c3ba45701d754beaca0c88aa` |
| Papers file SHA-256 | `7adf8572c623cd70407a49ad93e4e8741fd8972f0d21ea2dfe01e50d64cef6ff` |

Silver-label provenance (teacher model, prompt version, run id, generation
config, billing) is in `silver_manifest.json`; every claim row carries the same
fields. Silver labels are **training-only** and never gold.

## 2. Extraction metrics

| Metric | Measured | Note |
| :-- | --: | :-- |
| Papers processed | **100 / 100** | 2.03% of the 4,928-paper corpus |
| Accepted silver claims | **765** | 7.65 claims/paper (5-claim audit cap is separate) |
| Extracted claims (accepted + span rejects) | 862 | |
| Evidence-span verbatim rate | **88.7%** | 97 spans rejected as not verbatim |
| Strict pre-normalization rate | 88.7% | 0 claims rescued by normalization |
| Parse / structured-output failures | **0** | Pydantic-validated JSON schema |
| Other rejected claims | 11 | named a section the baseline document does not contain |
| Prompt-token estimate vs real | **−8.7%** | 764,084 estimated (chars/4) vs 697,734 real |

## 3. Tokens and cost (list price; $0 real spend)

| Metric | Value |
| :-- | --: |
| Prompt tokens | 697,734 |
| Completion tokens | 142,057 |
| Thinking tokens | **0** (SDK default thinking emitted none) |
| Total tokens | 839,791 (8,398/paper) |
| Cost per paper | **$0.005645** |
| Cost per accepted claim | **$0.000738** |
| Total list price | **$0.564459** |
| Output (incl. thinking) share of cost | **62.9%** |
| Requests used | **120** of the 450/day cap (500 RPD, 15 RPM, 250K TPM) |

Prices (checked 2026-11-15, <https://ai.google.dev/gemini-api/docs/pricing>):
`gemini-3.5-flash-lite` $0.30 input / $2.50 output / $0.03 cached input per 1M
tokens. Google prints no post-2026-12-31 change for this model, so call-date and
post-promotion costs are identical.

## 4. Latency

| Metric | Value |
| :-- | --: |
| Mean | 6,448 ms |
| p50 | ≈4,879 ms (ledger) |
| p95 | **15,490 ms** |

## 5. Corpus and retraction coverage

From `docs/reports/P1-corpus.md` and `P1-corpus-coverage.md` (no LLM calls):

| Measure | Value |
| :-- | --: |
| Papers (sources + citers) | 4,928 |
| Retracted OA source papers | 792 |
| Citer papers | 4,168 |
| Citation contexts | 6,117 |
| Parse coverage | 100.00% (4,928/4,928, 0 failures) |
| Retraction Watch rows in snapshot | 68,369 (1,586 in this subject; 1,565 linkable) |
| Sources with ≥1 incoming citer edge | 285 of 792 (507 have none) |
| Citer papers with no outgoing edge | 34 of 4,168 |
| Papers with no edge at all | 533 |

Blast-radius counts are conditional on this included citer set (ADR-0015
Proposed); the coverage caveat is recorded in `P1-corpus-coverage.md`.

## 6. Audited precision (P1-11) — pending

Export (ADR-0018 rule): `eval/audit/claims_audit_v1.csv` — **200 claims from 45
papers**, max 5 per paper, seed `20261114`, paper-level split 22 dev / 23 test,
corpus snapshot `fdaf972b397a32183d2ccf93f55298f1c76fe02037f07fb5a1cb7e4d5d2927be`,
all label fields blank. `claims_audit_v1_overlap.csv` holds the seeded 20% (40
claims) second-labeler subset. Labels are the owner's; the agent creates none.

Precision, Wilson 95% CI, the paper-level cluster bootstrap CI, the failure
breakdown, and κ are produced by:

```bash
.venv/Scripts/python.exe scripts/audit_validate.py \
    --audit eval/audit/claims_audit_v1.csv --out docs/reports/P1-audit.md
```

Until that runs, precision is **not reported anywhere** and the gate stays open.
The gate rule: if audited precision < 90%, fix extraction before P2.

## 7. Reproduce

```bash
# extraction (measured numbers above; free tier, no billing)
AXION_DRY_RUN=false .venv/Scripts/python.exe scripts/run_baseline_extraction.py \
    --sample 100 --execute --model gemini-3.5-flash-lite \
    --out eval/silver/claims_v1/baseline_flashlite/estimate \
    --silver-dir eval/silver/claims_v1/baseline_flashlite \
    --run-id p1-10-flashlite-s20261114-n100

# audit export from the candidate claims
.venv/Scripts/python.exe scripts/audit_sample.py \
    --claims eval/silver/claims_v1/baseline_flashlite/candidates.jsonl \
    --out eval/audit/claims_audit_v1.csv --seed 20261114
```

## 8. Limitations

- **Single labeler, pending.** No human labels exist yet, so no precision claim
  is made; the audit needs ~3–6 h and a ≥7-day blind relabel or a second
  labeler.
- **Sample scope.** 100 of 4,928 papers (2.03%), infectious-disease sub-topic
  only; no generalisation beyond the sample without stating the fraction.
- **Span rejects are semantic, not cosmetic.** The 97 rejects are partial or
  merged spans (for example Greek-letter variants such as `TNF-α`); normalization
  rescued none on this model. The 11 unknown-section rejects are a prompt
  wording issue, not a schema issue.
- **Config is fixed, not tuned** (ADR-0019): the baseline must stay comparable.
- **Reference comparison, not quality.** 5 papers on `gemini-3.8-flash` gave 74
  claims, 100% verbatim, 9,177 thinking tokens, $0.001403/claim and ~30× the
  latency (`eval/reference/claims_v1/flash38/`); it is not baseline and never
  silver.
