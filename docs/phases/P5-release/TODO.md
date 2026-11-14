# TODO — P5 — Release and write-up

**PRD:** `docs/PRD.md` (PRD §P5) · **Gate:** see PRD · **Update this file as you work.**

## Status legend
`[ ]` todo · `[~]` in progress (needs agent/started/branch) · `[x]` done (needs evidence) · `[!]` blocked (needs reason) · `[-]` dropped (needs ADR ref)

## Rules (read `docs/AGENT_PROTOCOL.md` for full text)
- Claim a task (`[~]`) before starting; mark `[x]` with evidence when done; checkpoint notes at every step.
- If you may run out of budget: write a PARTIAL-state note (done / left / exact next command) and commit WIP.
- Take the **first** task that is `[ ]` or a stale `[~]`, respecting `depends:`.
- Update `docs/PROGRESS.md` at session end.

## Tasks

### [ ] P5-01 — Reproducibility pass
- depends: P4 complete
- what: Fresh-environment run of all scripts (`make report`); fix drift.
- acceptance: Clean checkout reproduces headline tables.
  - agent: — | started: — | branch: p5
  - notes:
  - done: — | evidence: —

### [ ] P5-02 — Data release check
- depends: P5-01
- what: Verify redistribution terms for any text/labels; release only what is allowed; document in DATA_SOURCES.md.
- acceptance: Release manifest + license notes. (Owner approves.)
  - agent: — | started: — | branch: p5
  - notes:
  - done: — | evidence: —

### [ ] P5-03 — Docs polish
- depends: P5-01
- what: README, docs/OPERATIONS.md, SECURITY.md, CONTRIBUTING.md, limitations section.
- acceptance: Docs lint/link check passes.
  - agent: — | started: — | branch: p5
  - notes:
  - done: — | evidence: —

### [ ] P5-04 — Write-up draft
- depends: P5-02
- what: Problem, method, cost-quality frontier, blast-radius results, limitations, negative results, and a section **"What we do and do not claim about scale"**; numbers pulled from generated reports only.
- acceptance: Every claim maps to an artifact; scale section distinguishes measured (~5k papers) from projected values and acknowledges prior art in citation-statement classification.
  - agent: — | started: — | branch: p5
  - notes:
  - done: — | evidence: —

### [ ] P5-05 — Release
- depends: P5-03, P5-04
- what: Tag v2.0.0, changelog, CITATION.cff.
- acceptance: Tag pushed; release notes published.
  - agent: — | started: — | branch: p5
  - notes:
  - done: — | evidence: —

### [ ] P5-06 — Outreach materials (agent drafts, owner sends)
- depends: P5-05
- what: Draft materials in `_private/` per `_private/outreach-plan.md`; agents never contact anyone.
- acceptance: Drafts exist; owner reviews.
  - agent: — | started: — | branch: p5
  - notes:
  - done: — | evidence: —

## Phase handoff log (append newest first)
<!-- Format: YYYY-MM-DD — agent — what changed — next step -->
- (empty)

## Phase exit checklist
- [ ] All tasks `[x]` or `[-]` with ADR
- [ ] Gate criteria evaluated honestly (see PRD)
- [ ] `docs/PROGRESS.md` phase table and headline numbers updated
- [ ] Report committed in `docs/reports/`
