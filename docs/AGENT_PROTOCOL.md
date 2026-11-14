# Agent Protocol — working agreement for AI agents

Agents are interchangeable and can be **cut off without warning** (usage limits, crashes). The repo must always contain enough state for the next agent to continue. Follow this protocol exactly.

## 1. Session start (always)
1. Read, in order: `AGENTS.md` → `CONTEXT.md` → this file → `docs/PROGRESS.md` → the previous phase's `docs/phases/<phase>/HANDOFF.md` (when one exists) → active phase `TODO.md` → relevant PRD section.
2. If `_private/` exists locally: read `_private/README.md` and `_private/budget.md`.
3. `git status` and `git log -5`; confirm a clean working tree or understand uncommitted work (a previous agent may have been cut off — see §5).
4. Find the active phase in `docs/PROGRESS.md`. Take the **first** task in that phase's TODO that is `[ ]` (todo) or `[~]` (stale in-progress, see §5).
5. Run the task's preconditions (tests, env checks). Do not start work on a red baseline without noting it.

## 2. Task states (in phase `TODO.md`)
| Marker | Meaning |
| :-- | :-- |
| `[ ]` | Not started |
| `[~]` | In progress — must include `agent`, `started` timestamp, and the phase branch |
| `[x]` | Done — must include **evidence** (commit hash, files, test/command run) |
| `[!]` | Blocked — must include reason and what unblocks it |
| `[-]` | Dropped/superseded — must reference the ADR |

## 3. While working
- **Claim before you start:** change the task to `[~]` and fill `agent/started/branch` (the phase branch); commit the TODO change (or at minimum save it) *before* writing code.
- **One branch per phase:** work on `p<phase>` (`p1`, `p2`, …) for every task in that phase; small commits; Conventional Commits.
- **Checkpoint often:** after any meaningful step (tests passing, file created, long command finished), add a one-line note under the task. Before any long-running or expensive command, write the planned command in the task notes.
- **Tests and lint** must pass before marking `[x]`: `make lint typecheck test` (or the documented equivalents).
- **Cost discipline:** all LLM calls via `LLMClient`; check `_private/budget.md`; use `--dry-run` first; never exceed caps.
- **Docs in the same commit** as behavior changes.
- **Decisions:** anything that changes scope, schema, targets, data sources, or tech choices → new entry in `docs/DECISIONS.md` (status `Proposed` until the owner approves).

### Branching rule for phase threads

- `main` is the integration branch. A phase thread starts the phase branch from the current local `main`: `git switch main`, then `git switch -c p1` (or `git switch p1` if it already exists). Use one working branch per phase: `p1`, `p2`, and so on. Day-0's `d0/build-ready` predates this rule and is history.
- Do the whole phase on that branch. Do not create per-task branches such as `p1/P1-03-llmclient`. Task branches created before ADR-0010 are retained as history; they are not a precedent.
- Commit early and often with Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`, `wip:`). Mark the task `[~]` before writing code. If you stop mid-task, commit `wip: <task-id> <short state>` on the phase branch.
- **Merge to `main` only at task boundaries and only when green.** Run `make lint typecheck test` (or the documented equivalents) first. If all pass, merge the phase branch into `main` (fast-forward preferred: `git switch main && git merge --ff-only p1 && git switch p1`), then mark the task `[x]` with the merge commit in evidence. Never merge red: fix the issue or leave the task `[~]` on the phase branch.
- Do not rebase or rewrite history on a shared branch. If `main` moved, merge it into the phase branch, resolve conflicts there, re-run the checks, and then fast-forward `main`.
- **Delete the phase branch after the gate.** Once the gate result and handoff are recorded on `main`, delete the merged phase branch (`git branch -d p1`). Historical task branches and `d0/build-ready` are retained; do not rewrite them.
- Do not push `main`, phase branches, or tags until the owner has completed the visibility/push gate in `_private/owner-action-sheet.md`. Local commits are allowed while that gate is open.

## 4. Task completion
1. Mark `[x]` with: `done: <date>`, `evidence: <commit hash(es)>, <paths>, <command and result>`.
2. If the task produced numbers, ensure they come from a script and note the command.
3. Append a **session log entry** in `docs/PROGRESS.md` (template §7).
4. Update "Next action" in `docs/PROGRESS.md` to the next unclaimed task.
5. Commit the TODO update; merge to `main` per §3 only when the task boundary is green. Push only if the owner's push gate is open.

## 5. Resuming after an interruption
Signs: a task is `[~]` and its `started` time is old; uncommitted changes exist; a phase branch exists with WIP commits.
1. Read the task's notes and the diff of the phase branch.
2. Decide: **continue** (preferred) or **restart** (only if the WIP is unsafe). Record which, and why, in the task notes.
3. Re-run the tests before building on partial work.
4. Update the `agent/started` fields to yours; keep the history of prior notes.

**If you sense you are running out of budget/context:** stop starting new work. Write a **partial-state note** (§7) in the task: what's done, what's left, exact next command, and any gotchas. Commit WIP on the phase branch with message `wip: <task-id> <short state>`. Update `docs/PROGRESS.md`.

## 6. Stop and ask the owner when
- Scope or target changes are needed (any edit to `CONTEXT.md §3/§6`).
- A paid batch would exceed the cap, or `_private/budget.md` is missing and the batch is >20 calls.
- A destructive/irreversible action is needed (delete data, rewrite history, drop DB).
- Schema-breaking changes affect stored data.
- Licensing/terms of a data source are unclear.
- You find evidence that a reported number is wrong.
Record the question in `docs/PROGRESS.md` under "Open questions for owner" and mark the affected task `[!]`.

## 7. Templates

### Task notes (inside TODO)
```
- agent: <name/model> | started: <YYYY-MM-DD HH:MM> | branch: p1
- notes:
  - 2026-11-10 14:05 ledger schema done; tests pending
  - PARTIAL: implemented cache; TODO: provider cooldown + tests. Next: `pytest tests/llm -k cooldown`
- done: 2026-11-10 | evidence: commit abc1234; src/axion/llm/*; `make test` → 42 passed
```

### Session log entry (`docs/PROGRESS.md`, newest first)
```
### 2026-11-10 — <agent> — P1
- Did: P1-02 done, P1-03 in progress
- State: branch p1 (WIP commit abc1234)
- Next: finish cooldown + tests, then P1-04
- Blockers/questions: none
```

## 8. Prohibited
- Committing secrets, `.env`, anything under `_private/`, raw data, or large binaries.
- Calling an LLM outside `LLMClient`.
- Changing evaluation sets after tuning on them; leaking test split into training.
- Reporting numbers that no script regenerates.
- Silently dropping parse failures or errors.
- Evaluating a student on teacher-labeled data.
- Splitting by claim/context instead of by paper.
- Presenting projections as measurements.
- Expanding scope without an ADR.
- Rewriting git history on shared branches.

## 9. Definition of done (every task)
Code + tests + docs updated; lint/types/tests green; ledger/cost rules respected; TODO updated with evidence; PROGRESS next-action updated.

## 10. Phase thread protocol

The owner may run each phase in a **fresh agent thread**. Fresh threads have no chat memory, so the repository is the only handoff surface.

### Start of a phase thread
1. Follow §1, including the previous phase's `HANDOFF.md`.
2. Read the active phase's `TODO.md` and the matching PRD section before claiming work.
3. Read `_private/README.md` and `_private/budget.md` if the local folder exists.
4. Check `git status`, `git log -5`, and the current local `main`. Start the phase branch from `main` per §3.
5. Resume the first `[ ]` or stale `[~]` task. If a `[~]` task has a partial-state note, continue it; do not restart safe WIP.

### End of a phase thread (required, even if work is incomplete)
1. Write `docs/phases/<phase>/HANDOFF.md` from the template. Include:
   - current state and what is actually done;
   - decisions made and their ADR/TODO references;
   - gotchas, defects, and environment quirks;
   - open risks and owner blockers;
   - the exact next step and command;
   - a link to the gate report.
2. Write the gate report under `docs/reports/` using measured results only. Separate measured values from projections.
3. Update `docs/PROGRESS.md`: phase status, headline numbers, session log, blocked tasks, open questions, and next action.
4. Record every decision that exists only in chat as an ADR (if it changes scope/design) or a TODO note **before** the thread ends. Never leave knowledge only in chat.
5. Commit the handoff, gate report, TODO, and PROGRESS changes. Push only if the owner's push gate is open.
6. Delete the phase branch after the gate result is recorded on `main` (`git branch -d p1`); do not rewrite history.
7. **Stop at the gate.** Do not start the next phase. Wait for the owner's explicit decision.

### If the thread is cut off
Follow §5 immediately: write the partial-state note in the task (done / left / exact next command / gotchas), commit WIP on the phase branch with `wip: <task-id> <short state>`, and update `PROGRESS.md`. If time remains, update `HANDOFF.md` too.

### Owner-only work inside a phase
- Labeling tasks (for example P1-11 and P3-03) are owner work. The agent prepares the export, sampling script, rubric links, and validation checks; it does not invent labels.
- Keys, budget caps, licence decisions, repository visibility, and paid-run approval remain owner decisions. Record them in `docs/DECISIONS.md` or `_private/` as appropriate.
- Do not start the next phase while a gate decision is pending, even if the next phase's files look ready.
