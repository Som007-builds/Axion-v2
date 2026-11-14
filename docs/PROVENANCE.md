# Provenance — code and data carried over from Axion V1

V1 repository: https://github.com/Som007-builds/Axion (MIT) · V1 snapshot tag: `v1-final` (created and pushed 2026-11-09) · V1 commit: `b4b6a25338057bd05bc6b74bc75b26198fe546e8` (reference read 2026-11-09 from local `D:\AI-Projects\schimesh`)

| V1 path | V1 commit | V2 path | What changed | Notes |
| :-- | :-- | :-- | :-- | :-- |
| `llm.py`, `tests/test_llm_router.py`, `utils/llm_cache.py`, `utils/llm_parser.py` | `b4b6a25` | `src/axion/llm/*` (clean-room rewrite) | Typed `Provider` protocol and registry; injected clock/sleep; persistent SQLite content-hash cache; SQLite `llm_calls` ledger; tier model resolution; Pydantic structured-output validation; `axion-cost-report` CLI | Reference only; no code copied verbatim. Replaces V1's module-global router and in-process cache. |

## Fresh-vs-copied audit (2026-11-14)

**Result:** every substantive V2 tracked file was written fresh for V2. No V1 source, test, config, or documentation file was copied into the repository.

Method: compared the Git blob hashes of the 59 tracked V2 files with the 185 allowed source/documentation blobs in V1 at `b4b6a25338057bd05bc6b74bc75b26198fe546e8`. The comparison excluded V1 `.env` files, data, caches, credentials, and other non-source paths; no V1 secrets or data were read. The only identical blob was the empty `docs/reports/.gitkeep`, which matches empty `__init__.py` files in V1 and is not a copy of substantive content.

| V2 area | Status | Basis |
| :-- | :-- | :-- |
| Scaffold, packaging, CI, Makefile, pre-commit, settings, stage schema, tests, docs | Fresh | Written in V2 from the project brief and migration-map descriptions; no matching V1 blob. |
| `src/axion/llm/*` | Fresh clean-room implementation | V1 `llm.py` ideas were used as reference only (see row above); no matching V1 blob. |
| `LICENSE` | Fresh MIT template | Standard MIT text; not imported from V1. |
| `docs/reports/.gitkeep` | Empty placeholder | Coincidentally identical to empty V1 `__init__.py` files; not copied. |
| V1 files listed for a later P1-09 port | Not yet present | Owner must provide them or approve a rewrite; add a row here only when a file is actually ported. |

Rules: add one row per ported file; ported code keeps the MIT notice; no secrets, data, or caches are ever ported. If a later task imports a V1 file, update this audit and add the exact V1 path, commit, V2 destination, and changes.
