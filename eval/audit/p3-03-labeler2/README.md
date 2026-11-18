# labeler-2 handoff (wave 2)

ADR-0023 Amendment C requires that this directory contains **only** what the second labeler may
receive. Send these two files and nothing else:

- `p3-03-wave2-overlap2-labeler.html` — the blind packet (31 rows, one at a time, autosaves).
- `p3-03-wave2-overlap2-blind.csv` — the same rows as CSV, with the `label`/`note`/`labeler`/`date`
  columns blank.

**Do not** copy labeler 1's export (`dependency_audit_v1_wave2_labelled.csv`), any `*-selection.json`
(it carries per-class counts), any manifest (weights, strata, split), or any wave-1 packet into this
directory. Those stay in `eval/audit/p3-03/`, which is **not** shared with labeler 2.

The returned export is checked against the blinded subset before comparison, and the overlap must
carry at least 15 negative rows or the report declares negative-side kappa not estimable.
