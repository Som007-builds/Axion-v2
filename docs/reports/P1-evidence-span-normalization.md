# P1 evidence-span reject analysis

**Date:** 2026-11-15 — **Scope:** P1-10 baseline normalization only. No labels
were created.

## Method

The baseline first checks the model's `evidence_span` byte-for-byte in the named
section, then re-checks it with the fixed normalization rules in
`docs/eval/EVIDENCE_SPANS.md`. Normalization repairs Unicode, hyphen, quote,
whitespace, line-break hyphenation, and invisible-character differences. It does
not fold case or use fuzzy/paraphrase matching. Accepted normalized spans are
rewritten to the exact source substring.

## Groq pilot (historical, 1 paper)

| Measure | Result |
| :-- | --: |
| Extracted claims | 28 |
| Accepted | 21 |
| Strict rejects | 7 (25.0%) |
| Rejects after normalization | 3 (10.7%) |
| Fixed by normalization | 4 |
| Parse failures | 0 |

Reject categorization:

| Claims | Observation | Category | Fixed? |
| :-- | :-- | :-- | :-- |
| 12, 13, 14, 21 | U+2011 non-breaking hyphen vs source ASCII `-` | `normalization_only` | Yes |
| 5, 6 | Prefix matches, but the span merges a non-contiguous tail | `partial_or_merged` | No |
| 15 | `Remdesivir` vs source `remdesivir` | `case_only` | No |

## Decision

Paraphrase was **1 of 7** rejects, not the dominant cause. Prompt v2 is therefore
not justified; `claim-extraction-v1` stays. The same 5-paper sample is rerun on
Gemini for a provider-level before/after comparison once `gemini-3.8-flash` is
available.
