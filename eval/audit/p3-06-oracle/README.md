# P3-06 oracle packet (dev only)

**Question this answers:** if the source sentence in the prompt were *right*, would the detector
find more dependencies? The detector reads one abstract sentence per source; the P3-06 diagnosis
found a better body sentence for 68.8% of rows (`docs/reports/P3-06-linking-diagnosis.md`), but
"better by word overlap" is not "the sentence the citation depends on". This packet asks a human.

- **Rows: 30** = **all 14** text-bearing dev positives + **16**
  negatives, seed `20261120`, stratified by section (other 4, discussion 5, introduction 3,
  results 3, methods 1).
- Packet hash (row ids): `511b788c48d6c502`.
- **2 positives** (`P3W2-018`, `P3W2-023`) have no source body text — retracted or withdrawn before
  the body could be parsed. They stay in the packet, marked, and are excluded from the comparison.
- Candidates: up to **40 body sentences** per row, Results/Methods first, truncated in 19 rows.

## What to do

1. Open `p3-06-oracle-labeler.html` in a browser. It is self-contained; nothing is uploaded.
2. Type your labeler id in the top bar (the export refuses without one).
3. For each row: read the citing sentence and its paragraph, then the source paper's body
   sentences. Tick the sentence(s) the citing text actually depends on, or **none of these**.
   Background, a passing mention, or a shared topic is **none**. Keys: `1`–`9` toggle a candidate,
   `0` marks none, `n`/`p` move between rows.
4. Progress autosaves in the browser. When done, **Export CSV** and save the file as
   `p3-06-oracle-labelled.csv` **in this folder**.

**Expected time — estimate, not a measurement.** Your pace on the P3-05 contexts was **38 s/row**
when each row showed a short citing sentence and one abstract sentence. Here each row shows the same
context plus up to 40 source sentences to read through, but the judgement is a scan for one
supporting sentence rather than weighing a whole relation. Estimate **75–120 s/row**, i.e.
**35–60 minutes** for 30 rows, plus pauses. Flagged as an estimate: the packet does not measure
reading time, and the source paper's sentence count drives the spread.

## What the labels are used for

`scripts/p3_06_oracle.py` re-runs the frozen v3 detector on the rows where you picked a sentence,
with your sentence replacing the abstract proxy. Everything else stays identical: same prompt, same
schema, same model, same threshold. The comparison is positives caught before vs after as raw
counts out of 14, plus the direction of false alarms on the negatives. Thirty rows show a direction,
not an effect size — pre-registered in ADR-0027 Amendment A.

Nothing runs until the labels exist, and the live run is yours to start:

```powershell
.venv\Scripts\python.exe -m scripts.p3_06_oracle --mode dry-run
.venv\Scripts\python.exe -m scripts.p3_06_oracle --mode live --max-calls 28
```

## Files

| File | Whose |
|---|---|
| `p3-06-oracle-labeler.html` | yours — the blind labeler |
| `p3-06-oracle-blind.csv` | yours — the same 30 rows as data, no labels in it |
| `p3-06-oracle-labelled.csv` | yours — the export, once you have labelled |
| `p3-06-oracle-manifest.csv` | **not yours** — gold labels, id mapping, overlap flags |
| `../p3-06-oracle-labeler2/` | second labeler's blind-only handoff (10 rows) |

The manifest is what makes the packet auditable and what keeps it blind. Rebuilding the packet with
`python -m scripts.p3_06_link_oracle_packet` reproduces byte-identical files except this README,
which is copied from `docs/eval/p3_06_oracle_readme_template.md`.
