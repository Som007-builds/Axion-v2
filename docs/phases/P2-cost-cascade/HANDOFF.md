# HANDOFF — P2 Cost cascade

**Status:** P2 COMPLETE — gate accepted 2026-11-18. All tasks `[x]` or `[-]`; no task is `[~]` or `[!]`.
**Branch:** `main` (`p2` merged at `cd8f5aa`; phase branch deleted). **Real spend:** $0 (free tier, billing off; list price ledgered).
**Gate report:** `docs/reports/P2-cascade.md`. **Frontier:** `docs/reports/P2-frontier.md`.

## What exists and is usable in P3

- **Ablation harness** (`scripts/ablate.py`) scoring any config against the frozen 200-claim gold
  audit: aligned precision, retention (all + core, ADR-0021 accepted), unverifiable rate, ledger cost.
- **Six measured rows** in `eval/ablation/results/results.json`; `scripts/frontier.py` regenerates the
  cost-vs-quality frontier and the gate verdict per row.
- **Escalation policy** `p2-05-length30-v1` (`src/axion/eval/escalation.py`): frozen MiniLM student on
  every paper, teacher replay on the longest 30%, large model only when an escalated paper yields no
  accepted claim. **`e` = 31.1%**, **`s` = 0.29%** of baseline cost.
- **Accepted config** `src/axion/config/p2_operating_point.yaml` (status `accepted`, decided
  2026-11-18), guarded by `tests/test_p2_operating_point.py` so it cannot silently drift from the
  code constants.
- **Cost projection** `scripts/cost_model.py` → `docs/reports/P2-projection.md`, MEASURED/PROJECTED
  separated, no typed-in ledger numbers.
- **Silver labels**: 98 non-gold papers, 687 teacher claims across the P1 baseline (55 papers) and the
  P2-03a increments; all 45 gold papers excluded by construction.
- **Student**: `eval/student/student_v1.model.json` (frozen MiniLM + logistic head, k=8), metadata and
  hash only — no model artifacts committed.

## Decisions made

- ADR-0008 scale approach (carried from P1); ADR-0019 baseline model/config frozen.
- **ADR-0020** (Proposed): P2 quality = precision + retention + cost, unverifiable reported separately.
- **ADR-0021** (Accepted 2026-11-18): two retention numbers (all claims, core-section claims) and
  `$/core-section claim`; the gate keeps precision **and** agreement-with-baseline.
- **ADR-0022** (Accepted 2026-11-18): operating point = `p2-05-length30-v1`; chosen by "most
  retention among gate-passers, then cheapest" rather than cheapest-only. The 56.7% test retention
  is accepted as a stated limitation.

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

- **ADR-0021 and ADR-0022 are Accepted (2026-11-18).** The operating point is adopted, with the
  gate reading explicitly including agreement-with-baseline; the 56.7% test retention is a stated
  limitation. If a later phase requires ~90% retention, **no measured row passes** and P2 must be
  revisited as the published negative.
- Retention ~57% remains the weakest number in the phase. P3's dependency work may justify it (if
  relied-upon claims concentrate in the sections the cascade reads) or may kill it.
- Stage 2 (large model) is projected, never measured at scale.
- `s` uses an assumed CPU rate; a real deployment cost would change it (though `s` is negligible).

## Exact next step

P3 starts from `docs/phases/P3-blast-radius/TODO.md`; claim **P3-01** (dependency labeling guideline)
on branch `p3`. Do not re-open P2 without a new ADR. If P3 finds that relied-upon claims need the
sections the cascade drops, revisit ADR-0022 rather than silently changing the gate.

## Session log

- 2026-11-18 — opencode — owner accepted ADR-0021/ADR-0022; config promoted to `accepted`; `main`
  fast-forwarded to `cd8f5aa`, `p2` branch deleted; gate recorded.
- 2026-11-17 — Buffy — P2-07 frontier + ADR-0022 proposed; P2-09 projection; P2-08 lock/report/handoff.
- 2026-11-17 — Buffy — P2-06 batching measured (negative).
- 2026-11-17 — opencode — P2-03a/b/c, P2-04, P2-05, P2-05b.
- 2026-11-16 — Buffy — P2-01 harness; P2-02 section targeting (negative standalone).
