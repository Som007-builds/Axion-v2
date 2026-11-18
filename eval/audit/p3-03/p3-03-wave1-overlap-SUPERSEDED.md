# SUPERSEDED — wave-1 pre-built overlap

`p3-03-wave1-overlap-blind.csv` and `p3-03-wave1-overlap-labeler.html` are kept for the record
and are **not** to be labelled.

ADR-0023 Amendment A replaced the pre-built overlap with one built from the first labeler's
wave-1 labels. Build it after the wave returns:

```
python scripts/dependency_sample.py --build-overlap dependency_audit_v1_wave1_labelled.csv
```

That writes `p3-03-wave1-overlap2-blind.csv`, `p3-03-wave1-overlap2-labeler.html` and
`p3-03-wave1-overlap2-selection.json` (row ids and counts only, no labels).

Rule: all/nearly all `RELIES_ON` rows plus a round-robin spread over `MENTIONS`, `UNRELATED`
and `insufficient_context`; at least 30 rows and at least 20% of the wave and at least 6
negatives; blank labeler id; hash-ordered rows.

kappa from overlap 2 is conditioned on labeler 1 — report raw agreement next to it.
