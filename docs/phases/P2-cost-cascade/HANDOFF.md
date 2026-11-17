# HANDOFF — P2 Cost cascade

**Status:** P2 COMPLETE — gate review needed. All tasks `[x]` or `[-]`; no task is `[~]` or `[!]`.
**Branch:** `p2` (pushed). **Real spend:** $0 (free tier, billing off; list price ledgered).
**Gate report:** `docs/reports/P2-cascade.md`. **Frontier:** `docs/reports/P2-frontier.md`.

## What exists and is usable in P3

- **Ablation harness** (`scripts/ablate.py`) scoring any config against the frozen 200-claim gold
  audit: aligned precision, retention (all + core, ADR-0021 proposed), unverifiable rate, ledger cost.
- **Six measured rows** in `eval/ablation/results/results.json`; `scripts/frontier.py` regenerates the
  cost-vs-quality frontier and the gate verdict per row.
- **Escalation policy** `p2-05-length30-v1` (`src/axion/eval/escalation.py`): frozen MiniLM student on
  every paper, teacher replay on the longest 30%, large model only when an escalated paper yields no
  accepted claim. **`e` = 31.1%**, **`s` = 0.29%** of baseline cost.
- **Locked-but-proposed config** `src/axion/config/p2_operating_point.yaml` (status `proposed`),
  guarded by `tests/test_p2_operating_point.py` so it cannot silently drift from the code constants.
- **Cost projection** `scripts/cost_model.py` → `docs/reports/P2-projection.md`, MEASURED/PROJECTED
  separated, no typed-in ledger numbers.
- **Silver labels**: 98 non-gold papers, 687 teacher claims across the P1 baseline (55 papers) and the
  P2-03a increments; all 45 gold papers excluded by construction.
- **Student**: `eval/student/student_v1.model.json` (frozen MiniLM + logistic head, k=8), metadata and
  hash only — no model artifacts committed.

## Decisions made

- ADR-0008 scale approach (carried from P1); ADR-0019 baseline model/config frozen.
- **ADR-0020** (Proposed): P2 quality = precision + retention + cost, unverifiable reported separately.
- **ADR-0021** (Proposed): two retention numbers (all claims, core-section claims) and
  `$/core-section claim`; the gate keeps precision **and** agreement-with-baseline.
- **ADR-0022** (Proposed): operating point = `p2-05-length30-v1`; chosen by "most retention among
  gate-passers, then cheapest" rather than cheapest-only.

## Gotchas

- No GNU `make` on this host: use `.venv/Scripts/python.exe scripts/...`.
- `AXION_DRY_RUN=true` in `.env`; live runs need the command-local `AXION_DRY_RUN=false`.
- `eval/silver/**/*.jsonl`, `data/`, and the ledger are **gitignored**; the run reports and manifests
  are committed. Re-running analysis needs the local artifacts.
- Gemini 503 storms dominated the phase (43.2% of requests in one window). Every runner stops after
  three consecutive provider failures and resumes cleanly; **do not trust a pipeline's exit status for
  a `| tail` command** — check the artifact counts.
- Free-tier daily cap 450 requests, Pacific midnight reset; the pacer counts retries.

## Open risks and owner blockers

- **ADR-0021 and ADR-0022 are Proposed.** Until the owner rules, the operating point is not adopted,
  and the gate reading depends on whether agreement-with-baseline is binding. If ~90% retention were
  required, **no measured row passes** and the phase result is the published negative.
- Retention ~57% is the weakest number in the phase. P3's dependency work may justify it (if
  relied-upon claims concentrate in the sections the cascade reads) or may kill it.
- Stage 2 (large model) is projected, never measured at scale.
- `s` uses an assumed CPU rate; a real deployment cost would change it (though `s` is negligible).

## Exact next step

Owner decision on ADR-0021 and ADR-0022. If accepted, P3 starts from
`docs/phases/P3-blast-radius/TODO.md`; if the owner requires higher retention, P2's gate must be
recorded as a negative result and the best frontier point labelled as such **before** P3 begins.

## Session log

- 2026-11-17 — Buffy — P2-07 frontier + ADR-0022 proposed; P2-09 projection; P2-08 lock/report/handoff.
- 2026-11-17 — Buffy — P2-06 batching measured (negative).
- 2026-11-17 — opencode — P2-03a/b/c, P2-04, P2-05, P2-05b.
- 2026-11-16 — Buffy — P2-01 harness; P2-02 section targeting (negative standalone).
