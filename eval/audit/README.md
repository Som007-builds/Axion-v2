# Claim audit (P1-11)

This folder holds the **gold** human-audited claim set. The rubric is
`docs/eval/AUDIT_RUBRIC.md`; this note covers only the mechanics.

**The owner labels. The agent prepares the export and computes the numbers.**

## 1. Input

The extractor (P1-10) produces a candidate-claim JSONL file, one object per
line:

```json
{"claim_id": "PMC123:12", "paper_id": "PMC123", "claim_text": "...",
 "evidence_span": "...", "section": "Results", "paper_title": "...",
 "context_before": "...", "context_after": "..."}
```

`claim_id` and `paper_id` are required and `claim_id` must be unique;
`evidence_span` should be a verbatim substring of the source sentence.

## 2. Draw the sample

```powershell
python scripts/audit_sample.py --claims data/claims.jsonl --out eval/audit/claims_audit_v1.csv
```

- Uniform random sample, fixed seed `20261114`, minimum 200 claims (the script
  refuses a smaller sample unless `--allow-small` is passed for a dry run).
- The command prints the seed, the **corpus snapshot id** (SHA-256 of the claim
  set), and the dev/test counts. Record the seed and snapshot id in the report.
- The dev/test split is assigned **by paper** using a seeded hash, so a paper
  never straddles the split. It is frozen at export time, before any tuning.

## 3. Label

1. Work in the exported CSV; do not look at model confidence.
2. Use one of `CORRECT`, `NOT_A_CLAIM`, `DISTORTED`, `UNSUPPORTED_SPAN`,
   `DUPLICATE` in `label`.
3. Write a one-line `note` for every non-`CORRECT` row.
4. Fill `labeler` and `date` (ISO `YYYY-MM-DD`).
5. After **at least 7 days**, relabel a random 10% blind in `relabel_label`
   without looking at `label`.

Blank-label rows are allowed in a work-in-progress file and are reported as
unlabelled; the metrics script never guesses them.

## 4. Compute the numbers

```powershell
python scripts/audit_metrics.py --audit eval/audit/claims_audit_v1.csv \
    --out docs/reports/P1-audit.md
```

The script refuses unknown label values and reports precision, a Wilson 95%
CI, the failure breakdown, precision by section, and self-agreement (raw % and
Cohen's κ) once relabels exist. `--json` prints the same numbers for tooling.

## 5. Provenance

Commit the labelled `claims_audit_v1.csv`, the seed, the corpus snapshot id,
the rubric version (`v2`), and the extractor provenance (teacher model, prompt
version, run id) in the P1 baseline report. A teacher/student output is
**silver** and must never be placed in this folder or used for evaluation.

## 5-line procedure

1. Draw the seeded export: `python scripts/audit_sample.py --claims <candidates.jsonl> --out eval/audit/claims_audit_v1.csv --overlap-out eval/audit/claims_audit_v1_overlap.csv`.
2. Open `eval/audit/claim_audit_tool.html` directly in a browser and load the CSV (no server or network).
3. Label blind with `1`-`5`; press `N` for a note on every non-`CORRECT` row; arrows navigate; `Z` undoes.
4. Download the labelled CSV, then validate it: `python scripts/audit_validate.py --audit <labelled.csv> --out docs/reports/P1-audit.md`.
5. Optional agreement: have a second labeler load the `*_overlap.csv`, label it blind, and pass `--overlap <second.csv>` to `audit_validate.py`.

## Audit tool (single local HTML file)

`claim_audit_tool.html` is self-contained: no network calls, no CDN, no
dependencies, and no model confidence is displayed. It shows one claim at a
time with the paper title, section, and the paragraph window around the
evidence span; the span is highlighted. If the span is absent from the
supplied context, a red warning is shown and the span is displayed separately.
It autosaves to `localStorage`, keeps an undo stack, and downloads a CSV with
the exact audit columns.

What was actually checked: the inline JavaScript parses with `node --check`,
and the generated pilot CSV has the exact `AUDIT_RUBRIC.md` columns and the
paragraph context contains the span. The agent did **not** complete an
interactive browser run of this file, so the owner should load the two-row
fixture `eval/audit/tool_smoke_test.csv` (or any pilot CSV) and confirm the
keyboard flow before starting the real audit.

## Second-labeler overlap

`scripts/audit_sample.py --overlap-out ...` writes a deterministic seeded 20%
subset with the same columns. The second labeler labels that file blind; no
column is added to the audit. `scripts/audit_validate.py --overlap ...` merges
the second labels into `relabel_label` and computes raw agreement plus Cohen's
kappa. The alternative is the owner's blind self-relabel of the seeded 10%
after at least 7 days. ADR-0016 is the Proposed decision; the owner approves.

## Current P1 status (2026-11-15)

The paid P1-10 pilot produced **21 candidate claims from one paper** before
Groq's free-tier tokens-per-minute limit stopped the run (`TPM 8000`,
request `12111`). That pilot export is **below the 200-claim minimum** and is
not the official audit set. The local, git-ignored `claims_audit_v1_pilot.csv`
exists only to exercise the tooling; the official `claims_audit_v1.csv` waits
for a run that can clear the limit. Do not label the pilot file as if it were
the official sample.
