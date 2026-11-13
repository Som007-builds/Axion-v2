# Agent Protocol — working agreement for AI agents

Agents are interchangeable and can be **cut off without warning** (usage limits, crashes). The repo must always contain enough state for the next agent to continue. Follow this protocol exactly.

## 1. Session start (always)
1. Read, in order: `AGENTS.md` → `CONTEXT.md` → this file → `docs/PROGRESS.md` → active phase `TODO.md` → relevant PRD section.
2. If `_private/` exists locally: read `_private/README.md` and `_private/budget.md`.
3. `git status` and `git log -5`; confirm a clean working tree or understand uncommitted work (a previous agent may have been cut off — see §5).
4. Find the active phase in `docs/PROGRESS.md`. Take the **first** task in that phase's TODO that is `[ ]` (todo) or `[~]` (stale in-progress, see §5).
5. Run the task's preconditions (tests, env checks). Do not start work on a red baseline without noting it.

## 2. Task states (in phase `TODO.md`)
| Marker | Meaning |
| :-- | :-- |
| `[ ]` | Not started |
| `[~]` | In progress — must include `agent`, `started` timestamp, and branch |
| `[x]` | Done — must include **evidence** (commit hash, files, test/command run) |
| `[!]` | Blocked — must include reason and what unblocks it |
| `[-]` | Dropped/superseded — must reference the ADR |

## 3. While working
- **Claim before you start:** change the task to `[~]` and fill `agent/started/branch`; commit the TODO change (or at minimum save it) *before* writing code.
- **Branch per task:** `p<phase>/<task-id>-<slug>`; small commits; Conventional Commits.
- **Checkpoint often:** after any meaningful step (tests passing, file created, long command finished), add a one-line note under the task. Before any long-running or expensive command, write the planned command in the task notes.
- **Tests and lint** must pass before marking `[x]`: `make lint typecheck test` (or the documented equivalents).
- **Cost discipline:** all LLM calls via `LLMClient`; check `_private/budget.md`; use `--dry-run` first; never exceed caps.
- **Docs in the same commit** as behavior changes.
- **Decisions:** anything that changes scope, schema, targets, data sources, or tech choices → new entry in `docs/DECISIONS.md` (status `Proposed` until the owner approves).

## 4. Task completion
1. Mark `[x]` with: `done: <date>`, `evidence: <commit hash(es)>, <paths>, <command and result>`.
2. If the task produced numbers, ensure they come from a script and note the command.
3. Append a **session log entry** in `docs/PROGRESS.md` (template §7).
4. Update "Next action" in `docs/PROGRESS.md` to the next unclaimed task.
5. Push/merge per repo rules; do not leave work only in the local tree.

## 5. Resuming after an interruption
Signs: a task is `[~]` and its `started` time is old; uncommitted changes exist; a branch exists with WIP commits.
1. Read the task's notes and the diff of the WIP branch.
2. Decide: **continue** (preferred) or **restart** (only if the WIP is unsafe). Record which, and why, in the task notes.
3. Re-run the tests before building on partial work.
4. Update the `agent/started` fields to yours; keep the history of prior notes.

**If you sense you are running out of budget/context:** stop starting new work. Write a **partial-state note** (§7) in the task: what's done, what's left, exact next command, and any gotchas. Commit WIP on the task branch with message `wip: <task-id> <short state>`. Update `docs/PROGRESS.md`.

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
- agent: <name/model> | started: <YYYY-MM-DD HH:MM> | branch: p1/P1-03-llmclient
- notes:
  - 2026-11-10 14:05 ledger schema done; tests pending
  - PARTIAL: implemented cache; TODO: provider cooldown + tests. Next: `pytest tests/llm -k cooldown`
- done: 2026-11-10 | evidence: commit abc1234; src/axion/llm/*; `make test` → 42 passed
```

### Session log entry (`docs/PROGRESS.md`, newest first)
```
### 2026-11-10 — <agent> — P1
- Did: P1-02 done, P1-03 in progress
- State: branch p1/P1-03-llmclient (WIP commit abc1234)
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
