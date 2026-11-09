# AGENTS.md — read this first

You are an AI coding agent working on **Axion V2**. Work is handed between agents, and any agent can be cut off at any moment by a usage limit. The repository itself is the memory.

## Mandatory read order (every session)

1. `CONTEXT.md` — the project bible. Source of truth for purpose, scope, standards, rules.
2. `docs/AGENT_PROTOCOL.md` — how to start, work, checkpoint, and hand off.
3. `docs/PROGRESS.md` — current phase, last session, **next action**.
4. The active phase's `docs/phases/<phase>/TODO.md` — pick the first unclaimed task.
5. `docs/PRD.md` — only the section for the active phase.
6. `_private/` — if the folder exists locally, read `_private/README.md` and `_private/budget.md`. It is untracked; never commit or quote it in tracked files.

## Non-negotiables

- Update the phase TODO **at every task boundary** (claim before starting, mark done with evidence after). Do not batch updates to the end.
- Every LLM call goes through the project's `LLMClient` so it lands in the cost ledger. No exceptions.
- Never commit secrets or anything under `_private/`.
- Do not expand scope. Anything not in the active phase's TODO needs an entry in `docs/DECISIONS.md` approved by the owner.
- Stop and ask the owner when the protocol says to (see `docs/AGENT_PROTOCOL.md` §6).
