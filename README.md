# Axion V2

**When a paper is retracted, which claims in other papers actually depended on it?**

Citation-level alerts answer "everything that cites this." Axion V2 aims at the sentence the
citation sits in, decides whether that sentence *relies on* the retracted work, and does so at a
cost that is measured on every step rather than assumed.

This is a working research codebase, not a product. It publishes its own negative results, every
number below comes from a script in this repo, and the phase gate it currently faces is **not
passed**.

| | |
| :-- | :-- |
| **Phase** | P3 — blast radius (detector + baselines + gold audit) |
| **Gate status** | ⚠️ **open** — the detector has not yet beaten the section/lexical heuristic |
| **Real spend** | **$0** (free tier, billing off; every call still ledgered at list price) |
| **Test set** | frozen, hash-locked, **not evaluated once yet** |
| **Runtime** | Python 3.11 · pytest · ruff · mypy strict on `src/axion` |
| **Checks** | 474 tests passing, 2 skipped · lint, format and types clean (at this commit) |

---

## The problem, concretely

Retractions arrive in batches — paper-mill takedowns, proceedings purges — and they arrive faster
than review capacity grows. Downstream impact is currently computed by citation: paper B cites
retracted paper A, so B is flagged.

That signal is nearly useless at scale because a citation carries no information about load. Of
**300 human-labelled citation contexts** in this repo's corpus, only **37 (12.3%)** genuinely rely on
the retracted work. The other 263 are background, credit, a list of prior findings, a comparison, or
a mention of the retraction itself. An alert that fires on all 300 is right 12% of the time, and the
people receiving it learn to ignore it.

The interesting question is therefore not "does B cite A" but "would B's sentence have to change if
A's claim were false" — and the interesting engineering question is whether that can be answered
cheaply enough to matter.

## How it is built

Four layers, cheap to expensive, with the expensive layers reached only when the cheap ones cannot
decide:

```
JATS full text ──▶ Layer 0  deterministic   sections, paragraphs, xrefs, citation contexts,
   (Europe PMC)              no model calls  dedup, hash keys            ← citation contexts for free
                    │
                    ▼
                    Layer 1  student          small encoder models, trained on silver labels,
                             local CPU        run the bulk of triage at ~0.3% of LLM cost
                    │
                    ▼
                    Layer 2  escalation       small LLM, then a large one, only on low-confidence
                             LLM              items; results feed back as silver labels
                    │
                    ▼
                    Layer 3  lazy / hot-cold  process each paper once, risk-first; the cold corpus
                             scheduling       stays unprocessed until something makes it hot
```

The planning model is `relative_cost ≈ s + e`, where `s` is student cost as a fraction of
LLM-everywhere and `e` is the escalation rate. **`e` dominates**, which is why this project spends
its effort on measuring `e` and not on optimising `s`.

The cheapest lever turned out to be structural: JATS `<xref ref-type="bibr">` markers inside
paragraphs hand you the citation context with no model call at all.

## What has actually been measured

Every figure links to the committed report that regenerates it.

| Result | Number | Report |
| :-- | :-- | :-- |
| Corpus built from Retraction Watch → Europe PMC OA | **792** retracted source papers, **6,117** citation contexts, 3,976 citer→source edges | [`P1-corpus.md`](docs/reports/P1-corpus.md) |
| Claim extraction precision | **96.5%** [93.0, 98.3], n=200 claims, cluster-bootstrapped by paper | [`P1-audit.md`](docs/reports/P1-audit.md) |
| Deterministic candidate generation | 285 sources with a citer edge, 258 with ≥1 candidate context, **69.7%** of contexts linked to a source claim, idempotent re-load | [`P3-02-candidates.md`](docs/reports/P3-02-candidates.md) |
| Baseline cost, LLM on every section | **$0.005645**/paper, 100 papers, 765 claims | [`P2-ablation.md`](docs/reports/P2-ablation.md) |
| Cascade operating point (`escalation-length30`) | **−55.6% cost** ($0.002505/paper), test precision 98.2%, **retention 56.7%** | [`P2-cascade.md`](docs/reports/P2-cascade.md) |
| Escalation rate `e` | **31.1%** measured (14 of 45 gold papers) | [`P2-cascade.md`](docs/reports/P2-cascade.md) |
| Student cost ratio `s` | **0.29%** of baseline (1,192 ms/paper measured on CPU; the CPU price is an **assumption**) | [`P2-student.md`](docs/reports/P2-student.md) |
| Human-labelled gold set | **300** contexts, **37** `RELIES_ON`, split **by source paper** into 151 dev / 149 test | [`P3-03-wave1-metrics.md`](docs/reports/P3-03-wave1-metrics.md) |
| Two-labeler agreement | 61 overlap rows, **100%** raw agreement — and κ is **degenerate**, which is its own finding | [`P3-03-wave2-agreement.md`](docs/reports/P3-03-wave2-agreement.md) |
| Frozen test baselines | heuristic R **83.3%** [60.8, 94.2] at FAR **38.0%**; citation-level FAR 100%; LLM-only R 16.7% at FAR 1.1% | [`P3-04-baselines.md`](docs/reports/P3-04-baselines.md) |
| Staged detector, dev | cascade R **42.9%** [21.4, 67.4] at FAR **12.0%**, `e`=45% | [`P3-05-detector-dev.md`](docs/reports/P3-05-detector-dev.md) |

Those costs are **list price** recorded in a SQLite ledger on every call. Actual spend is $0 because
the project runs on a provider free tier with billing switched off — the discipline is that the
number would be real if billing were on.

### The gate this project is currently failing

P3's gate is: beat the citation-level baseline on false alarms at **recall ≥ 0.80**. The current best
cascade reaches **42.9% recall at 12.0% false alarms** on dev, against the heuristic's **85.7%
recall at 42.6%**. It is more precise and much less sensitive; it does not dominate. The phase gate
is therefore **open**, and it stays open until a detector clears the pre-registered rule
([ADR-0026](docs/DECISIONS.md)).

That sentence is in the README on purpose. A results table that only shows a project's good phase is
an advertisement, not a lab notebook.

## Negative results this repo publishes

1. **More teacher labels stopped helping.** Quality on the frozen gold test was flat from 10 to 98
   labelled papers, so labelling stopped 202 papers short of its ceiling — money not spent, written
   up as a negative result ([`P2-student.md`](docs/reports/P2-student.md)).
2. **The flywheel did not reduce escalation.** Retraining on escalated cases left held-out `e` at
   **8.3% → 8.3%** ([`P2-05b-flywheel.md`](docs/reports/P2-05b-flywheel.md)).
3. **Title-only rows are not free negatives.** The stub stratum was expected to be near-certain
   negatives; **3 of 34 were `RELIES_ON`** — a title plus the citing sentence is sometimes enough
   ([`P3-03-wave1-metrics.md`](docs/reports/P3-03-wave1-metrics.md)).
4. **An LLM asked for a class gives you a coin, not a probability.** Prompt v1 was near-silent
   (16.7% test recall); prompt v2 asked for a 0–100 score and returned **111 rows ≤ 30, zero rows
   between 31 and 70, 40 rows ≥ 70** — a decision wearing a number's clothes, which left the
   threshold nothing to tune ([`P3-05-llm-v2-calibration.md`](docs/reports/P3-05-llm-v2-calibration.md)).
5. **Perfect agreement can be uninformative.** Both labelers agreed on all 61 overlap rows, so
   Cohen's κ is 1.000 *by degeneracy* and says nothing about the rubric's borderline cases — which is
   the only place the rubric could be wrong.

## How the numbers stay honest

- **Every reported table is generated by a script** in [`scripts/`](scripts) and committed with the
  report. If it cannot be regenerated here, it is not claimed here.
- **Silver trains, gold evaluates.** Machine labels never appear in an evaluation. Human labels are
  the only basis for a reported number.
- **Splits are by paper**, not by row, so a paper cannot appear on both sides of a threshold.
- **The test set is frozen before the detector exists.** A spec hash is written to
  `eval/audit/p3-*/p3-*-test-frozen.json`; later runs recompute and *refuse to continue* if any
  frozen number moved. A baseline added after the freeze carries its own `added_at` stamp instead of
  quietly replacing the file.
- **Rates come with intervals.** Wilson for proportions, cluster bootstrap when rows share a paper.
  With 18 text-bearing test positives, "not distinguishable" is a legitimate and expected outcome.
- **Cost is reported with quality, always.** A result without a price is an incomplete result.
- **LLM calls go through one client.** No ad-hoc `requests` to a model anywhere: the client owns
  retries, pacing, caching and the ledger, so a call that is not in the ledger does not exist.

## Quickstart

Requires **Python 3.11** (pinned to `>=3.11,<3.12`); on Windows use `.venv\Scripts\activate`.

```bash
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
pre-commit install

make lint typecheck test            # ruff · mypy · pytest (all offline)
```

Everything in the default test suite is offline: no network, no paid calls. Network checks are
opt-in via `AXION_RUN_NETWORK=1`.

Cost accounting is a first-class CLI:

```bash
axion-cost-report --db data/ledger.sqlite3 --group-by stage
axion-cost-report --db data/ledger.sqlite3 --group-by model --json
```

Regenerate any report, for example:

```bash
python scripts/dependency_baselines.py      # P3-04 frozen test baselines
python scripts/p3_08_cost.py --section cost # $/context, $/retraction, PROJECTED corpus totals
python scripts/audit_validate.py --audit eval/audit/claims_audit_v1.csv
```

Optional extras exist for the parts that need more than a laptop's default: `.[store]` (Neo4j,
ChromaDB), `.[embeddings]`, `.[train]` (students). Nothing is required to run the tests. The Neo4j
stack used for graph checks is described in [`docs/LOCAL_SETUP.md`](docs/LOCAL_SETUP.md).

## Repository layout

```
src/axion/
  config/     settings, pricing table, corpus configs    llm/       LLMClient, providers, ledger, pacing
  ingest/     Europe PMC + retraction data               parse/     JATS → sections, xrefs, contexts
  extract/    claim extraction, cascade stages, prompts  link/      context→claim linking, dependency
  train/      silver labelling, students, evaluation     propagate/ trust propagation rules
  store/      Neo4j, Chroma, SQLite access               eval/      Wilson intervals, agreement stats
  api/        scaffold only — the FastAPI app is P4
scripts/      one script per committed report (each prints the numbers it claims)
eval/         gold + silver label manifests, frozen test specs, audit packets
docs/         PRD, architecture, ADRs, phase TODOs, generated reports
tests/        offline test suite (474 tests, no network)
```

## Documentation

| Doc | What it is |
| :-- | :-- |
| [`CONTEXT.md`](CONTEXT.md) | The project bible: purpose, scope, standards, cost rules, glossary |
| [`docs/PRD.md`](docs/PRD.md) | Phase-by-phase requirements and gates |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design and data model |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | 26 ADRs — including the ones that reverse earlier decisions |
| [`docs/reports/`](docs/reports) | Every generated report, MEASURED vs PROJECTED kept apart |
| [`docs/eval/DEPENDENCY_GUIDELINE.md`](docs/eval/DEPENDENCY_GUIDELINE.md) | The labelling rubric the gold set uses |
| [`docs/PROGRESS.md`](docs/PROGRESS.md) | Session-by-session log, including the failures |
| [`docs/AGENT_PROTOCOL.md`](docs/AGENT_PROTOCOL.md) | How work is claimed, checkpointed and handed off |

## Built by agents, on purpose

This repository is developed by AI coding agents working under a written protocol and an owner who
holds the decisions. The protocol is not decoration: agents claim a task before starting, record
evidence when finishing, checkpoint at every boundary because a session can be cut off without
warning, and **stop and ask** for anything irreversible. Decisions live in ADRs, and a later ADR
reversing an earlier one is normal and visible.

If you are an agent picking this up: read [`AGENTS.md`](AGENTS.md) first, then `CONTEXT.md`, then
`docs/AGENT_PROTOCOL.md`.

## Roadmap

| Phase | Scope | State |
| :-- | :-- | :-- |
| Day 0 | Prerequisites, tooling, pricing table | ✅ complete |
| P1 | Foundation: ledger, corpus, claim extraction baseline | ✅ complete |
| P2 | Cost cascade: students, escalation, frontier | ✅ gate accepted (with published caveats) |
| P3 | Blast radius: gold audit, baselines, staged detector, $/retraction | 🚧 **in progress — gate open** |
| P4 | Demo: API + dashboard with a live cost panel | ⬜ not started |
| P5 | Release: frozen evaluation, write-up, projection at scale | ⬜ not started |

What "done" will require, so it can be judged when claimed: dependency recall ≥ 0.80 with its
interval, false-alarm reduction against the citation-level floor, measured **$/retraction analysed**,
a frozen single test evaluation, and a corpus-scale figure labelled PROJECTED with its assumptions
attached.

## Lineage and license

Successor to [Axion V1](https://github.com/Som007-builds/Axion) (MIT). V2 is a clean-room restart:
selected components are ported with attribution in [`docs/PROVENANCE.md`](docs/PROVENANCE.md), and
V1's history is not carried over.

MIT — see [`LICENSE`](LICENSE) and ADR-0009. Data comes from Europe PMC (open access) and Retraction
Watch as distributed via Crossref; licence and field checks are recorded in
[`docs/DATA_SOURCES.md`](docs/DATA_SOURCES.md).
