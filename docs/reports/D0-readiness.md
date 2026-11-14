# Day-0 build-ready gate report

**Date:** 2026-11-14
**Scope:** the owner-requested Day-0 close-out that makes the repository safe and complete enough for fresh per-phase agent threads. No P1 feature work was started.
**Branch:** `d0/build-ready`, merged into local `main` after this report; nothing was pushed.
**Decision:** **Agent close-out complete; Day 0 is not fully complete.** P1 can start locally at the P1-03 checkpoint, but normal push/CI and several later P1 tasks remain owner-blocked.

## Checks

| Area | Check | Result | Evidence / notes | Owner or agent |
| :-- | :-- | :-- | :-- | :-- |
| Git state | Local `main` contains P1-01, P1-02, DOC-01, and the P1-03 checkpoint | PASS | Merge `6986af3`; task branches `p1/P1-01-bootstrap`, `p1/P1-02-settings`, `p1/P1-03-llmclient`, and `docs/scale-approach` retained. | Agent |
| Git state | Only `.env.example` is tracked among env/private paths | PASS | `git ls-files` filtered for `_private`/`.env` → `.env.example` only. `_private/` is ignored. | Agent |
| Git state | Working tree clean after final checks | PASS | No uncommitted source/config changes after the final commit; this report/status update is the last commit. | Agent |
| Secret scan | Custom working-tree scan | PASS | `python scripts/check_secrets.py` → `secret scan passed`. | Agent |
| Secret scan | `detect-secrets` full history (all refs + reflog) | PASS | Installed `detect-secrets==1.5.0`; 98 unique text blobs scanned preserving paths. 9 findings, all unverified false positives: historical P1-01 evidence lines containing the literal phrase "secret scan" (Secret Keyword) and a fake test env value in `tests/test_settings.py` (Base64 High Entropy String). **0 verified secrets.** | Agent |
| Secret scan | Current-tree `detect-secrets` | PASS (with known false positives) | 3 unverified false positives: the same P1-01 phrase, the `super-secret-value` test sentinel, and the fake test env value. No credential or private key. | Agent |
| Provenance | Any V1-copied files? | PASS | Compared 59 V2 tracked blobs with 185 allowed V1 source/doc blobs at `b4b6a25`, excluding V1 `.env`, data, caches, and credentials. Only empty `docs/reports/.gitkeep` matched empty V1 `__init__.py` files; no substantive copy. Recorded in `docs/PROVENANCE.md`. | Agent |
| Tests | Offline test suite | PASS | `python -m pytest -q` → **89 passed, 1 skipped** (the network test is opt-in via `AXION_RUN_NETWORK=1`). | Agent |
| Lint/types | Ruff check and format | PASS | `ruff check .` → all checks passed; `ruff format --check .` → 35 files already formatted. | Agent |
| Lint/types | Strict mypy | PASS | `python -m mypy` → success, 22 source files. | Agent |
| Pre-commit | Hook install and full run | PASS | `pre-commit install` succeeded. The 3.11 venv cannot create hook envs on this host (Python base is `D:\`, a virtualenv path bug); running the same hooks under Python 3.12 passed all 8 hooks: check-yaml, large-files, end-of-file, trailing-whitespace, ruff, ruff-format, mypy, secret-scan. CI uses Ubuntu 3.11. | Agent/local tooling |
| CI | Workflow YAML lint | PASS (syntax only) | `pre-commit check-yaml` and PyYAML parse passed; one job (`quality`). `actionlint` is unavailable. The workflow cannot execute until the private remote has the pushes. | Agent |
| Compose | Neo4j 5.x only, healthcheck, loopback, env password, named volumes | PASS | `docker compose config --quiet` with a temporary dummy password → PASS. No Redis/worker/API. Not started because Docker is currently stopped; not exercised against a live container. | Agent |
| Day-0 check | Script + offline tests + target | PASS | `scripts/day0_check.py`, `tests/test_day0_check.py`, `make day0-check`; 89 tests pass. Prints PASS/FAIL/SKIP and never prints values. | Agent |
| Day-0 check | Current host readiness | FAIL | `python scripts/day0_check.py` → Python PASS; environment names FAIL (`LLM_SMALL_MODEL`, `LLM_LARGE_MODEL`, `NEO4J_PASSWORD`, `CROSSREF_CONTACT_EMAIL`, `EUROPEPMC_CONTACT_EMAIL` missing); dry-run PASS; Docker FAIL (daemon not reachable); Neo4j SKIP (configured but down). These are owner/local environment items, not script defects. | Owner |
| Docs | Data-source terms recorded; unknowns explicit | PASS (owner approval pending) | `docs/DATA_SOURCES.md` has URLs, verification date, access methods, Retraction Watch fields, per-article Europe PMC licence rule, polite-usage rules, and "Owner to confirm" on every row. Retraction Watch licence and Europe PMC numeric rate limit remain unresolved. | Agent + owner |
| Config | `.env.example` names match settings; pricing blank; no hard-coded model IDs/prices | PASS | Existing `test_env_example_lists_every_setting`; `test_packaged_template_loads_with_blank_prices`; `pricing.yaml` has `models: {}`; production search found no model IDs or numeric prices. | Agent |
| Fresh-thread docs | Protocol, D0 handoff, P1–P5 handoff templates | PASS | `docs/AGENT_PROTOCOL.md` §1 and §10; `docs/phases/D0-prerequisites/HANDOFF.md` filled; P1–P5 templates exist. | Agent |
| Fresh-thread prompts | P1–P5 kickoff + mid-phase resume | PASS | Six untracked files in `_private/phase-prompts/`; `git check-ignore` confirms `_private/`; `git ls-files _private` is empty. | Agent |
| Owner handoff | Action sheet ordered by soonest blocker | PASS | `_private/owner-action-sheet.md` (untracked): push, contact emails/Neo4j, provider/prices/budget, Retraction Watch terms, V1 files, labeling time, B1–B6, P5 release. | Agent |
| Docs | Local Markdown links resolve | PASS | 26 Markdown files checked; 0 missing local links. | Agent |
| ADR numbering | ADR-0008 scale approach; ADR-0009 Day-0 | PASS (owner confirmation pending) | `docs/DECISIONS.md` records the renumbering and the updated private/open-ended-hours facts; owner confirmation requested in D0-O1. | Agent + owner |
| Remote/CI | Private remote has local `main` and branches | FAIL | Repo is private (unauthenticated GitHub API 404 on 2026-11-14), but `origin/main` is still `f0eea8f`; local `main` is ahead. No task branches are on the remote; CI has not run. | Owner |
| P1-04/P1-05/P1-06 | Live fetch prerequisites | FAIL | Contact emails, Neo4j password/start, and network confirmation are missing. Offline implementation can proceed. | Owner |
| P1-06/P1-07 | Retraction Watch terms/data | FAIL | Dataset licence/redistribution is unresolved; raw CSV is currently treated as non-redistributable. | Owner |
| P1-10 | Provider, model IDs, verified prices, budget | FAIL | Tier model IDs and prices are blank; provider/key state must be reconciled; dry-run stays on; paid budget remains $0 until approved. | Owner |
| P1-09 | V1 files or rewrite decision | PENDING (can wait) | Exact V1 paths and V2 destinations are in the owner action sheet; P1-09 can rewrite from the migration-map description if the owner approves. | Owner |
| P1-11/P3-03 | Owner labeling time | FAIL (later) | Not scheduled. Assumption: ~3–6 owner hours each plus the P1-11 7-day relabel gap; P1-11 cannot be closed without it. | Owner |

## Hard blockers vs can-wait

**Hard blockers for normal phase operations or specific tasks**

1. **Push/CI:** local `main` and the task branches are not on the private remote; `origin/main` is `f0eea8f`. This blocks review, CI, and a normal phase handoff.
2. **Live P1 fetch:** contact emails, Neo4j password/start, and network confirmation are missing. This blocks P1-04/P1-05/P1-06 live acceptance, not offline implementation.
3. **Retraction Watch:** the dataset licence/redistribution terms are unresolved. This blocks P1-06/P1-07 data acquisition and later release.
4. **P1-10:** provider/model IDs, verified prices, and any paid budget are missing. This blocks live baseline extraction.
5. **P1-11/P3-03:** owner labeling time is not scheduled; P1-11 also needs a 7-day relabel gap. This blocks the P1 gate and P3 gold set.

**Can wait**

- V1 file port vs rewrite for P1-09 (P1-09 can be rewritten from the migration-map description).
- B5 weekly hours (open-ended/no fixed schedule) and B6 `_private/` backup risk (accepted).
- Final licence, data release, public visibility, and outreach for P5.

## Day-0 exit assessment

- **Agent work:** complete for this close-out.
- **Day 0 as a whole:** **not complete**, because owner-only blockers remain. However, none of them block the first P1-thread action (re-running and closing P1-03), which is offline.
- **Fresh P1 thread:** resume P1-03, then P1-03b, then P1-04. Read `docs/phases/D0-prerequisites/HANDOFF.md` first.
- **First owner action:** after the agent merges `d0/build-ready` into local `main`, push `main` to the private remote and confirm GitHub Actions is green.

## Commands used for this report

```text
python -m pytest -q                         # 89 passed, 1 skipped
python -m ruff check .                      # passed
python -m ruff format --check .             # 35 files formatted
python -m mypy                              # 22 source files
python scripts/check_secrets.py             # passed
pre-commit run --all-files (Python 3.12)    # 8/8 hooks passed
docker compose config --quiet               # passed with dummy env
python scripts/day0_check.py                # current host: 3 FAIL, 1 SKIP
```

## Limitations

- The full-history scan used `detect-secrets`, not `gitleaks`/`trufflehog` (unavailable). It scanned all refs plus reflog, but no tool can prove a negative.
- `actionlint` is unavailable; CI YAML is syntax-checked but not semantically executed locally.
- The Compose healthcheck was validated by config only; Docker was stopped at the final check.
- Data-source terms are recorded as observed on 2026-11-14; they are not legal advice and are not owner-approved yet.
- Labeling-hour estimates are planning assumptions, not measured times.
