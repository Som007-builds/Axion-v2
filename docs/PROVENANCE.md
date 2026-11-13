# Provenance — code and data carried over from Axion V1

V1 repository: https://github.com/Som007-builds/Axion (MIT) · V1 snapshot tag: `v1-final` (created and pushed 2026-11-09) · V1 commit: `b4b6a25338057bd05bc6b74bc75b26198fe546e8` (reference read 2026-11-09 from local `D:\AI-Projects\schimesh`)

| V1 path | V1 commit | V2 path | What changed | Notes |
| :-- | :-- | :-- | :-- | :-- |
| `llm.py`, `tests/test_llm_router.py`, `utils/llm_cache.py`, `utils/llm_parser.py` | `b4b6a25` | `src/axion/llm/*` (clean-room rewrite) | Typed `Provider` protocol and registry; injected clock/sleep; persistent SQLite content-hash cache; SQLite `llm_calls` ledger; tier model resolution; Pydantic structured-output validation; `axion-cost-report` CLI | Reference only; no code copied verbatim. Replaces V1's module-global router and in-process cache. |

Rules: add one row per ported file; ported code keeps the MIT notice; no secrets, data, or caches are ever ported.
