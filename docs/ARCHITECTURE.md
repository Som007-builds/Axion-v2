# Architecture (planned)

See `CONTEXT.md §7` for stack and data model; this file is the design overview and will be updated as components land.

```mermaid
flowchart LR
    EPMC[Europe PMC API<br/>JATS full text] --> ING[Ingest + raw cache]
    CR[Retraction Watch data<br/>via Crossref] --> FLAG[Flag loader + linker]
    ING --> PARSE[JATS parser<br/>sections, refs, citation contexts]
    PARSE --> STORE[(Neo4j graph<br/>Chroma vectors)]
    FLAG --> STORE
    STORE --> EXP[Expand from flagged papers<br/>find citing contexts]
    EXP --> CAS[Cascade<br/>rules → classifier → small LLM → large LLM]
    CAS --> LINK[Link contexts to source claims]
    LINK --> PROP[Trust propagation]
    PROP --> STORE
    CAS -. every call .-> LEDGER[(SQLite cost ledger)]
    STORE --> API[FastAPI]
    LEDGER --> API
    API --> WEB[Dashboard<br/>blast radius + cost panel]
```

## Design principles
- Deterministic stages first; cost attributed per stage via `stage` and `run_id` on every derived edge and ledger row.
- Idempotent loaders; content/ID keys; cache before models.
- Evaluation is a first-class component (`eval/`), with frozen splits and regenerable reports.

## Component responsibilities (target)
| Component | Responsibility | LLM |
| :-- | :-- | :-: |
| `ingest/` | Europe PMC and retraction-data clients, raw cache | no |
| `parse/` | JATS → structured document + citation contexts | no |
| `extract/` | cascade stages, claim extraction | yes (late stages) |
| `link/` | dependency detection and context→claim linking | yes (ambiguous only) |
| `propagate/` | trust propagation rule v2 | no |
| `llm/` | `LLMClient`, providers, cache, ledger | — |
| `store/` | Neo4j, Chroma, SQLite access | no |
| `api/` | read endpoints, cost summaries | no |

## Open design questions (resolve via ADR)
- Granularity of claim linking (sentence vs. claim object).
- Transitive propagation depth and decay.
- Handling of retracted papers with missing/partial full text.
