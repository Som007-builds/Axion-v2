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
