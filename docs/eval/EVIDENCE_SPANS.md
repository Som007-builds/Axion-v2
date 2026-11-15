# Evidence-span normalization (P1-10)

The baseline accepts a claim only when its `evidence_span` can be located in the
named section. Matching is **verbatim after a fixed, documented normalization**;
there is no fuzzy matching, edit distance, stemming, or paraphrase matching.
Case is **not** folded. When a span is accepted after normalization, the stored
span is rewritten to the exact source substring, so the silver claim and the
audit CSV never contain the model's variant.

Implementation: `src/axion/extract/claims.py` (`normalize_for_match`,
`find_evidence_span`, `verify_claims`). Tests:
`tests/test_span_normalization.py`.

## Accepted normalization rules

1. **Unicode compatibility normalization** — NFKC, which expands ligatures
   (`ﬁ` → `fi`), full-width forms, and compatibility characters.
2. **Hyphen variants** — U+2010, U+2011, U+2012, U+2013, U+2014, U+2015,
   U+2212, U+FE58, U+FE63, and U+FF0D map to ASCII `-`.
3. **Quote variants** — curly single/double quotes, low/high quotes, prime
   marks, and guillemets map to ASCII `'` or `"`.
4. **Whitespace** — every whitespace run (including non-breaking and narrow
   spaces, tabs, and newlines) collapses to one ASCII space.
5. **Line-break hyphenation** — a hyphen between two letters followed by a
   line break is removed, joining the word (`remdesi-\nvir` → `remdesivir`).
6. **Invisible characters** — soft hyphen, zero-width space/joiner, and BOM are
   removed.

Not allowed: case folding, accent stripping, punctuation removal, stemming,
word reordering, fuzzy matches, or accepting a span from a different section.
A case-only difference is a reject, classified `case_only`.

## Reject categories

Failures from the normalized run are retained with `evidence_span` and a
`category` (also present in the `detail` text):

| Category | Meaning | Action |
| :-- | :-- | :-- |
| `unknown_section` | The named section is not in the baseline document. | Reject. |
| `partial_or_merged` | A prefix matches but the span joins non-contiguous text or a tail that is not in the source. | Reject; do not stitch. |
| `case_only` | The span matches only when case is folded. | Reject; case folding is not allowed. |
| `paraphrase_or_reordered` | At least 60% of the long words occur, but not the contiguous span. | Candidate for a future prompt change, not normalization. |
| `paraphrase_or_absent` | No contiguous prefix and fewer than 60% of long words occur. | Candidate for a future prompt change, not normalization. |

`normalization_only` is recorded for strict-run rejects that the normalized run
accepts; it is not a final failure category.

## Groq pilot categorization (2026-11-15, 1 paper)

The Groq pilot extracted 28 claims, of which 21 were accepted and 7 were
span rejects. The 7 rejects were:

| Claims | Difference | Category | Normalization fix? |
| :-- | :-- | :-- | :-- |
| 12, 13, 14, 21 | U+2011 non-breaking hyphen where the source has ASCII `-` | `normalization_only` | Yes — hyphen rule |
| 5, 6 | A prefix matches, but the model merged a non-contiguous tail into the span | `partial_or_merged` | No — reject |
| 15 | `Remdesivir` vs source `remdesivir` (case only) | `case_only` | No — case folding not allowed |

Before normalization: **7 / 28 = 25.0%** rejects. After the normalization-only
pass: **3 / 28 = 10.7%** rejects. Paraphrase was not the dominant cause
(1/7 rejects), so prompt v2 is **not** justified by this pilot; the prompt stays
`claim-extraction-v1`. The same 5-paper pilot is rerun on Gemini to measure the
reject rate on the new provider.
