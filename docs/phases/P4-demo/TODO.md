# TODO — P4 — Demo and dashboard

**PRD:** `docs/PRD.md` (PRD §P4) · **Gate:** see PRD · **Update this file as you work.**

## Status legend
`[ ]` todo · `[~]` in progress (needs agent/started/branch) · `[x]` done (needs evidence) · `[!]` blocked (needs reason) · `[-]` dropped (needs ADR ref)

## Rules (read `docs/AGENT_PROTOCOL.md` for full text)
- Claim a task (`[~]`) before starting; mark `[x]` with evidence when done; checkpoint notes at every step.
- If you may run out of budget: write a PARTIAL-state note (done / left / exact next command) and commit WIP.
- Take the **first** task that is `[ ]` or a stale `[~]`, respecting `depends:`.
- Update `docs/PROGRESS.md` at session end.

## Tasks

### [ ] P4-01 — API read endpoints
- depends: P3 gate passed
- what: List retractions, blast radius, claim provenance, health/readiness; fail-closed auth on any compute endpoint; tests.
- acceptance: OpenAPI renders; tests green.
  - agent: — | started: — | branch: p4
  - notes:
  - done: — | evidence: —

### [ ] P4-02 — Cost endpoints
- depends: P4-01
- what: Aggregations from ledger by stage and per retraction; tests.
- acceptance: Endpoint outputs match ledger report.
  - agent: — | started: — | branch: p4
  - notes:
  - done: — | evidence: —

### [ ] P4-03 — UI shell
- depends: P4-01
- what: Layout, API client, offline/empty states.
- acceptance: App builds; offline state visible without backend.
  - agent: — | started: — | branch: p4
  - notes:
  - done: — | evidence: —

### [ ] P4-04 — Blast radius view
- depends: P4-03
- what: Retraction picker -> graph + table (claim, citing paper, strength, evidence span) with provenance.
- acceptance: Manual walkthrough on 3 retractions.
  - agent: — | started: — | branch: p4
  - notes:
  - done: — | evidence: —

### [ ] P4-05 — Cost panel
- depends: P4-02, P4-03, P2-09
- what: Per-stage cost, calls, cache hits, savings vs baseline, escalation rate `e`, student cost ratio `s`, and a projection table labeled **PROJECTION** with assumptions; visually separate measured from projected.
- acceptance: Numbers trace to ledger; measured/projected separation is obvious; projection assumptions displayed.
  - agent: — | started: — | branch: p4
  - notes:
  - done: — | evidence: —

### [ ] P4-06 — Compose + seed
- depends: P4-04, P4-05
- what: Docker Compose (Neo4j + API + web), healthchecks, loopback ports; seeded demo dataset; one-command start.
- acceptance: Fresh clone -> demo works.
  - agent: — | started: — | branch: p4
  - notes:
  - done: — | evidence: —

### [ ] P4-07 — Screenshots + walkthrough
- depends: P4-06
- what: Capture screenshots; write walkthrough doc.
- acceptance: Committed under docs/ (no secrets in images).
  - agent: — | started: — | branch: p4
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
