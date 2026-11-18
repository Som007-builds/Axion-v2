# Dependency Labeling Guideline — P3 v1.1

**Status:** v1.1 after the 20-row P3-01 pilot. This is a rubric, **not** a gold label set.
**Scope:** citation contexts in citing paper **B** that point at a retracted or flagged source paper **A**.
**Unit:** one resolved context-source edge. One sentence can produce several rows when it cites
several source papers; label each source separately.

Later stages (P3-06) link a relying context to the **specific claim** in A. This guideline stops at
the context-source edge so the pilot tests the definitions before claim linking is built.

## 1. Labels

Only three labels are allowed. Do not add an `UNSURE` label; if the text is genuinely insufficient,
skip the row and say why in `note`. A skipped row is not gold. In the packet and labeler, a skipped
row has a **blank `label`** and a `note` beginning `insufficient_context`; `insufficient_context` is a
UI action, not a fourth label.

### `RELIES_ON`

The citing context's claim, argument, method, or interpretation is **supported by, derived from, or
conditional on** a specific claim in A. Removing or invalidating that claim would weaken, qualify, or
falsify what B asserts in this context.

Use `RELIES_ON` when the citation does argumentative work, for example:

- B uses A's result as a premise for B's conclusion.
- B compares its own result with A's result and the comparison is load-bearing.
- B uses A's data, sample, parameter, or validated method as an input to its own claim.
- B includes A's finding in a meta-analysis, systematic review, or guideline recommendation.
- B's interpretation depends on A's claim even if B also cites other papers.

Counterfactual test: **if A's specific claim were retracted, would B's sentence need to change?**
If yes, `RELIES_ON`. If B would only need to remove a courtesy citation, it is not.

### `MENTIONS`

B cites A, and the citation is real, but B's claim does not depend on a specific claim in A. The
citation provides background, credit, a topic pointer, a standard method/tool reference, or a
contrast that B's own claim survives without.

Typical `MENTIONS` cases:

- "X has been studied extensively [A]."
- "A et al. reported Y" as background, where B's own claim does not use Y.
- A review, guideline, or textbook cited for general context.
- A standard assay, software package, database, or protocol cited in Methods.
- A list of examples ("several studies [A, B, C]") with no specific finding attributed.
- A citation to A's retraction notice or to A *as retracted*.
- B explicitly rejects A's claim: "A claimed X, but we show Y." B's claim stands without X; the
  citation is a contrast, not support.

**Corroboration is not dependency.** If B says "our result agrees with A" or "in agreement with
previous observations [A]", and B's result rests on B's own data, label `MENTIONS`. It becomes
`RELIES_ON` only when B's claim, method, parameter, or interpretation uses A's result as a premise,
input, or constraint. A single citation is not automatically `RELIES_ON`; count the load-bearing
use, not the number of citations.

`MENTIONS` is not a junk label. It says the citation exists but the retraction does not propagate
through this context.

### `UNRELATED`

The marker does not actually connect the context's asserted content to A. Examples:

- The marker is an artifact or a grouped reference dashboard, and the sentence is about something
  else.
- The context is only a reference-list fragment or a bare marker with no surrounding claim.
- A reference was misattributed to A by the parser or by the publisher, and the sentence does not
  discuss A at all.

Do **not** use `UNRELATED` merely because the citation is weak. A weak but real background citation
is `MENTIONS`. A method/tool citation is normally `MENTIONS`, not `UNRELATED`.

## 2. Decision procedure

Apply these steps in order:

1. **Resolve the target.** Identify which source paper A the marker points to. If a marker points to
   several sources, make one row per source. If the target cannot be resolved, do not label it; mark
   the row `unresolved` in `note` and exclude it from gold.
2. **Read enough context.** Read the marker's sentence and, when the sentence is incomplete or the
   antecedent is unclear, the adjacent sentence(s) and the section. Do not label from the reference
   title alone.
3. **State B's assertion.** Write down what B is claiming in this context. If there is no assertion
   (only a list, a definition, or a pointer), go to `MENTIONS` or `UNRELATED` as appropriate.
4. **Run the counterfactual.** If A's specific claim were removed or retracted, would B's assertion
   lose support, need qualification, or become false?
   - Yes → `RELIES_ON`.
   - No, but B is still referring to A → `MENTIONS`.
   - No, and the context is not really referring to A → `UNRELATED`.
5. **Record the reason.** Every non-trivial row gets a short `note` naming the decision cue. For
   `RELIES_ON`, name the supporting claim or result if it is visible. For a skipped row, say what
   is missing.

If the answer is genuinely undecidable from the available text, skip the row. Do not guess to fill a
quota.

## 3. Edge cases

| Case | Label | Reason |
| :-- | :-- | :-- |
| B uses A's effect size as an input to its meta-analysis | `RELIES_ON` | B's pooled estimate depends on A's result. |
| B cites A's standard PCR protocol in Methods | `MENTIONS` | The protocol is a tool citation; B's finding is not a claim from A. |
| B cites A for a definition it uses to classify cases | Usually `RELIES_ON` | B's classification depends on A's definition; note the definition if visible. |
| B cites A only as one of many examples of a topic | `MENTIONS` | No specific A claim is load-bearing. |
| B says "A was retracted [A]" | `MENTIONS` | B is reporting the retraction, not relying on A's claim. |
| B says "A claimed X; in contrast, we find Y" | `MENTIONS` | B's own result survives without X; the citation is adversarial. |
| B says "A claimed X; building on X, we find Y" | `RELIES_ON` | B's inference uses X as a premise. |
| B cites A for a database or software package | `MENTIONS` | A tool citation is not a claim dependency by default. |
| B says its own result agrees with A's prior result, but B's claim rests on B's own data | `MENTIONS` | Corroboration/consistency is not a premise; use `RELIES_ON` only if B's inference or parameter uses A. |
| B cites A as the sole support for a descriptive premise that drives B's recommendation | `RELIES_ON` | The premise is load-bearing even though only one citation supports it. |
| B cites A for a method but takes a parameter estimated from A | `RELIES_ON` | The parameter is load-bearing; note it. |
| B cites A in a limitations paragraph because A's method constrains B | `RELIES_ON` if the limitation changes B's claim; otherwise `MENTIONS` | Use the counterfactual, not the section. |
| B cites A only in a figure/table legend with no claim | `MENTIONS` | It is a citation, not a dependency. |
| B and A are the same paper (self-citation) | Use the same rule | Self-citation has no special exemption. |
| The retraction reason is misconduct, error, or a publisher action | Do not use the reason | Label the citation relation; the reason affects propagation policy, not this rubric. |
| The context cites several sources and attributes a specific finding only to A | `RELIES_ON` for A; `MENTIONS` for the others | One context can have different labels per source. |
| The context cites a review that itself cites A | `MENTIONS` for the review | Transitive citation is not the same edge; do not credit A through the review. |
| The marker is present but the paragraph is truncated before the claim | Skip; `note: insufficient_context` | Do not infer from the title or abstract. |

**Section is not a label.** Introduction citations can be `RELIES_ON` (a premise) and Results
citations can be `MENTIONS` (a comparison). Use the assertion and the counterfactual.

**Retraction status is not a label.** A retracted source can be `MENTIONS` in one context and
`RELIES_ON` in another. The detector's job is to find the second kind.

## 4. Constructed examples

These are **illustrations of the rubric**, not labels for any paper in the corpus. They are
deliberately constructed so the pilot labels remain independent.

| Context (B) | Why | Label |
| :-- | :-- | :-- |
| "Because A showed that the inhibitor reduced viral load by 2 log10, we tested the same inhibitor in our model." | B's experiment is motivated by A's result; the result is a premise. | `RELIES_ON` |
| "Inhibitor studies have been reviewed elsewhere [A]." | A is a topic pointer; B makes no claim from it. | `MENTIONS` |
| "We used the assay exactly as described by A." | A supplies a standard method, not a finding. | `MENTIONS` |
| "We used the inhibition constant reported by A to parameterize our model." | The parameter is an input; B's result depends on it. | `RELIES_ON` |
| "A reported an association, but our cohort shows no association." | B's result survives as a refutation; the citation is a contrast. | `MENTIONS` |
| "Building on A's finding that X predicts Y, we show that X also predicts Z." | B's inference uses A's finding as a premise. | `RELIES_ON` |
| "Several studies [A, B, C] have examined this question." | A is one example in a list; no specific finding is load-bearing. | `MENTIONS` |
| "A was retracted in 2024 [A]." | B reports the retraction; it does not rely on the claim. | `MENTIONS` |
| "See [A] for the full protocol." | A is a pointer, not a claim in B's argument. | `MENTIONS` |
| "[A]" alone, with no sentence around it. | No assertion to evaluate. | `UNRELATED` |

## 5. Pilot protocol (P3-01)

- **Packet:** `eval/audit/dependency_pilot_v1.csv`, generated by
  `python scripts/dependency_pilot.py` with seed `20261118`.
- **Sampling:** 20 resolved context-source edges, stratified by source paper (one context per source
  where possible), from the P1 corpus. The packet records the citer, source, section, marker,
  `context_text`, and `paragraph_text`. Labels are **blank**.
- **Source-claim proxy:** `source_claim_text` is the first substantive sentence of the source paper's
  abstract. It is context only, not a linked claim and not a model output. The label is still the
  context-source edge; P3-06 links the specific claim in A. Do not label from the proxy alone.
- **Blank-label labeler:** open `eval/audit/dependency_pilot_labeler.html` in a browser. It is a
  single self-contained HTML file with the 20 rows embedded, shows one row at a time, and stores
  progress in browser `localStorage`. It shows no model output. Keys `1`/`2`/`3` select
  `RELIES_ON`/`MENTIONS`/`UNRELATED`, key `4` marks `insufficient_context` (blank label), `0` clears
  the row, and `←`/`→` move between rows. The note box autosaves. **Export CSV** downloads
  `dependency_pilot_v1_labelled.csv` with the same columns plus `labeler` and `date`; the bundled
  copy defaults to `Soham` and `2026-11-18`. Send that file back; do not edit the source CSV by hand.
- **No agent labels:** the agent prepares the packet and does not fill `label`. The owner labels the
  20 rows. If a second labeler is available, label all 20 blind; the pilot is small enough that a
  full overlap is more informative than a 20% subset.
- **Pilot notes:** record disagreements, ambiguous rows, and any rule changes in the "Pilot log"
  below. Refine this document to v1.1 after the pilot.
- **Not gold:** pilot rows are rubric-calibration only. They are not part of the P3-03 gold audit,
  are not used for training, and are not reported as evaluation results. P3-03 draws a fresh
  stratified sample.

## 6. Reporting rules

For a real gold set, report:

- counts and per-class precision/recall/F1, with CIs where the sample supports them;
- **false-alarm reduction** against the citation-level baseline, where every citing paper is flagged:
  `RELIES_ON` is the positive class, and `MENTIONS`/`UNRELATED` are negatives;
- agreement on the double-labeled subset (raw agreement and Cohen's κ; if κ is degenerate, say so);
- the labeler, date, rubric version, and seed;
- the sampling frame, including unresolved or skipped rows.

Do not report the pilot as a gold result. Do not convert a teacher or student label into gold.

## 7. P3-01 pilot result

The measured summary is generated by `scripts/dependency_pilot_metrics.py`:
`docs/reports/P3-01-pilot.md` and `eval/audit/dependency_pilot_v1.summary.json`.

- **Returned file:** `eval/audit/dependency_pilot_v1_labelled.csv`; 20/20 rows, 20 source papers,
  20/20 notes, 0 blank labels.
- **Labels:** `MENTIONS` 16 (80.0%), `RELIES_ON` 2 (10.0%), `UNRELATED` 2 (10.0%).
- **Provenance:** `labeler=Soham`; `date=2026-11-18`; guideline version is `P3-v1`. The owner
  accepts responsibility for the pilot labels. The bundled labeler defaults to `Soham`.
- **Agreement:** no second-labeler file was supplied, so raw agreement and Cohen's κ are **not
  estimable**. This is a single-labeler calibration pilot, not a gold evaluation.
- **Review corrections:** `P3P-010` and `P3P-014` were corrected from `RELIES_ON` to `MENTIONS`
  during review. Both are grouped discussion corroboration; this is why v1.1 adds the
  "corroboration is not dependency" rule.
- **Edge cases exercised:** 3 retraction notices, 2 reference-list fragments, 4 grouped
  corroboration/consistency rows, 1 withdrawn source with no abstract-claim proxy (`P3P-014`).
- **Close calls:** a sole citation can still be `RELIES_ON` when its premise drives B's
  recommendation (`P3P-002`), while a sole citation that only corroborates B's own result is
  `MENTIONS` (`P3P-014`).

## Pilot log

- 2026-11-18 — opencode — v1 guideline drafted. `scripts/dependency_pilot.py` generated
  `eval/audit/dependency_pilot_v1.csv`: **20 blank-label rows across 20 source papers**, seed
  `20261118`. The packet intentionally contains real edge cases (retraction notices, reference-list
  fragments, grouped citations) so the pilot tests the rubric rather than only easy cases. Owner
  labeling and disagreement notes are pending; no labels were created by the agent.
- 2026-11-18 — opencode — added `paragraph_text` and a source-abstract `source_claim_text` proxy to
  the packet, and built the blank-label labeler
  `eval/audit/dependency_pilot_labeler.html`. The labeler is self-contained, blind to model output,
  autosaves locally, and exports the same CSV columns. No labels were created.
- 2026-11-18 — opencode — received the 20-row labelled packet (`labeler=Soham`, owner
  responsibility); ran `scripts/dependency_pilot_metrics.py`; recorded the single-labeler
  limitation, the two review corrections, and the corroboration rule. Refined this document to
  v1.1. The agent created no labels.
- **Pilot status:** complete. P3-01 is `[x]`; P3-03 still draws a fresh sample and this pilot is not
  gold or training data.

## Version history

- **v1.1 (2026-11-18):** after the 20-row pilot. Added the explicit corroboration/consistency rule,
  the sole-citation clarification, two edge-case rows, and the measured pilot summary. Rubric labels
  unchanged.
- **v1 (2026-11-18):** initial guideline, decision procedure, edge-case table, constructed examples,
  and the P3-01 pilot protocol. Labeler and source-claim-proxy note added the same day; rubric labels
  unchanged.
