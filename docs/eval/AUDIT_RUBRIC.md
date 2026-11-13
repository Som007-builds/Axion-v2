# Claim Audit Rubric (Phase 1)

**Goal:** measure **claim extraction precision** with an honest, repeatable human audit.

## 1. What counts as a claim
A **claim** is a self-contained, falsifiable assertion about findings, methods' effects, or relationships reported by the paper (e.g., "Drug X reduced Y by 20% vs. placebo (n=120)").

Not claims: background facts attributed to others without the paper's own support, definitions, procedural descriptions ("We collected samples from…"), rhetorical statements, future work, hedged speculation without a stated finding, headings, or citations alone.

## 2. Labels (one per extracted claim)
| Label | Meaning |
| :-- | :-- |
| `CORRECT` | A real claim; text faithfully represents the source; evidence span supports it. |
| `NOT_A_CLAIM` | Fails the definition above. |
| `DISTORTED` | Based on a real statement but wording changes meaning (stronger/weaker, wrong direction, missing key condition). |
| `UNSUPPORTED_SPAN` | The evidence span does not contain or support the claim (or is not found verbatim). |
| `DUPLICATE` | Substantively duplicates another extracted claim from the same paper. |

**Precision** = `CORRECT / total audited`. Report secondary breakdown by failure label.
Edge case: a claim that is correct but with an imprecise span → `UNSUPPORTED_SPAN` only if the span fails to support the claim; otherwise `CORRECT` with a note.

## 3. Sampling
- Sample **≥200** extracted claims uniformly at random with a fixed seed (record seed and corpus snapshot id).
- Stratify reporting (not sampling) by section and paper to expose weaknesses.
- Freeze dev/test split of the audited set (e.g., 50/50) **before** any cascade tuning in P2.

## 4. Procedure
1. Export sample with: `claim_id`, claim text, section, evidence span, paper title/PMCID, ±1 surrounding paragraph.
2. Label in a spreadsheet/CSV; do not look at model confidence while labeling.
3. Write a one-line note for every non-`CORRECT` label.
4. After **≥7 days**, re-label a random 10% blind; compute agreement (raw % and Cohen's κ).
5. Commit labels with: labeler id, date, rubric version.

## 5. Reporting
- Report `n`, precision, **Wilson 95% CI**, failure breakdown, and self-agreement.
- State the limitations: single labeler, domain/sub-topic coverage, sample size.
- Label provenance: **gold** (human-audited). Anything not human-audited is **silver** and must be marked so.

## 6. Silver vs. gold
- **Gold** labels are human-audited and are used for **evaluation**: gold DEV for tuning thresholds, frozen gold TEST for the only reported student/classifier quality.
- **Silver** labels are teacher/student/heuristic outputs and are used for **training only**.
- **Never evaluate a student on teacher-labeled data.** A teacher-score is not a student metric.
- Splits are by **paper**, not by claim or citation context. Student training must exclude every paper that appears in the gold DEV or TEST sets.
- The gold TEST set is frozen before tuning and never used for threshold selection or retraining.
- Record the student version/hash with every result. Do not commit large model artifacts; commit metadata and hashes.

**File locations:**
- Gold: `eval/audit/` (committed; see §7).
- Silver: `eval/silver/` for manifests, label schemas, and hashes. Large silver label files are **not** committed if they exceed repo limits; commit a manifest with row counts, provenance, and SHA-256 hashes, and document the regeneration command.

## 7. File format
`eval/audit/claims_audit_v1.csv` columns:
`claim_id, paper_id, section, claim_text, evidence_span, label, note, labeler, date, rubric_version, split, relabel_label`

## Changelog
- v1 (2026-11-09): initial rubric.
- v2 (2026-11-14): added silver-vs-gold rules, paper-level splits, and silver file locations (ADR-0008).
