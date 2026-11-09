# Axion V2

**Claim-level trust propagation for the scientific literature — at a cost you can measure.**

When a paper is retracted or flagged, which claims in *other* papers actually depended on it? Citation-level alerts say "everything that cites it." Axion V2 aims to answer at the **claim level**, and to do so cheaply enough to run at scale by expanding the graph outward from retracted papers only, rather than processing an entire corpus.

> **Status:** Pre-Phase 1 (Day-0 setup). Nothing here is production-ready. See [`docs/PROGRESS.md`](docs/PROGRESS.md) for live status.

## Why this exists

- AI-generated and paper-mill content is entering the literature faster than review can absorb it; retractions arrive in large batches.
- LLM-based claim processing is too expensive to run over tens of millions of papers.
- Axion V2 treats **cost per trusted claim** as a first-class result, reported next to quality in every experiment.

## Principles

1. **Hypotheses, not verdicts.** Every machine judgment is a lead to inspect, with provenance back to the source sentence.
2. **Measured or it didn't happen.** Reported numbers come with sample sizes, intervals, and a command that regenerates them.
3. **Cost is a metric.** Every LLM call is logged; every experiment reports quality *and* dollars.
4. **Negative results are published.**

## Documentation

| Doc | Purpose |
| :-- | :-- |
| [`CONTEXT.md`](CONTEXT.md) | Project bible: purpose, scope, standards, glossary |
| [`docs/PRD.md`](docs/PRD.md) | Phase-by-phase product requirements |
| [`docs/DAY0_PREREQUISITES.md`](docs/DAY0_PREREQUISITES.md) | Setup and what is carried over from Axion V1 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Architecture decision records |
| [`docs/AGENT_PROTOCOL.md`](docs/AGENT_PROTOCOL.md) | Working agreement for AI agents |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Live status and session log |
| [`docs/eval/AUDIT_RUBRIC.md`](docs/eval/AUDIT_RUBRIC.md) | Human labeling rubric |

## Development

Requires Python 3.11. Dev tools are pinned in `pyproject.toml`.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
pre-commit install
make lint typecheck test
```

`make report` is a placeholder until the first regenerable report exists (P1-12).
All tests are offline by default; network and LLM tests must be marked and opt-in.

## Lineage

Successor to [Axion V1](https://github.com/Som007-builds/Axion) (MIT). V2 is a clean-room restart: selected components are ported with attribution (see `docs/PROVENANCE.md` once created), history is not carried over.

## License

MIT (to be confirmed in Day-0; see `docs/DAY0_PREREQUISITES.md`).
