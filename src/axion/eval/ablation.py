"""P2 ablation harness: score configurations against the frozen gold audit.

The gold audit labels 200 claims produced by the P1 baseline over 45 papers
(22 dev / 23 test). It measures **precision** of that output and cannot measure
absolute recall. A P2 configuration is therefore scored on three separate
numbers, always reported together:

* **aligned precision** — among the configuration's claims that align with a
  gold-labelled baseline claim, the share whose gold label is ``CORRECT``;
* **retention** — the share of the 200 gold claims the configuration still
  emits (agreement relative to the baseline's own output, *not* recall);
* **cost** — list-price USD from the ledger, per paper and per retained claim.

Output that aligns with no gold row is **unverifiable**: its precision is
unknown and it is never counted as correct. This module computes those numbers;
it does not create labels and it never tunes on the test split.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from axion.eval.audit import LABELS, read_audit, wilson_interval
from axion.extract.claims import (
    BaselineDocument,
    find_evidence_span,
    normalize_for_match,
)
from axion.parse.jats import sentence_bounds

Matching = Literal["span", "sentence"]
SPLITS = ("dev", "test")
BASELINE_PRECISION = 0.965
BASELINE_RUN_ID = "p1-10-flashlite-s20261114-n100"


class AblationError(Exception):
    """Raised when a configuration or its inputs cannot be evaluated."""


class AblationConfig(BaseModel):
    """One versioned pipeline configuration, replayable from its artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    description: str
    kind: Literal["replay", "teacher_run", "student_run"]
    claims_path: str
    matching: Matching = "sentence"
    run_ids: tuple[str, ...] = ()
    paper_ids_path: str | None = None
    paper_count: int | None = Field(default=None, ge=1)
    ledgers: tuple[str, ...] = ()
    notes: str = ""

    def canonical(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


class GoldClaim(BaseModel):
    """One audited claim row, reduced to the fields the harness needs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str
    paper_id: str
    split: Literal["dev", "test"]
    label: str
    section: str
    evidence_span: str


class ConfigClaim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    paper_id: str
    section: str
    evidence_span: str


class SplitScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    split: str
    gold: int
    retained: int
    retention: float
    aligned: int
    aligned_correct: int
    precision: float | None
    precision_ci_low: float | None
    precision_ci_high: float | None
    emitted: int
    claim_aligned: int
    claim_correct: int


class ConfigScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config: str
    description: str
    kind: str
    matching: str
    config_sha256: str
    claims_sha256: str | None
    gold_sha256: str
    papers: int
    claims: int
    claims_per_paper: float
    evaluation_papers: int
    evaluation_claims: int
    cost_usd: str | None
    cost_per_paper_usd: str | None
    cost_per_retained_claim_usd: str | None
    cache_hits: int
    calls: int
    by_split: dict[str, SplitScore]
    overall: SplitScore

    def to_row(self) -> dict[str, object]:
        return {
            "config": self.config,
            "papers": self.papers,
            "claims": self.claims,
            "claims_per_paper": round(self.claims_per_paper, 3),
            "cost_per_paper_usd": self.cost_per_paper_usd,
            "dev_precision": _fmt_pct(self.by_split["dev"].precision),
            "dev_retention": _fmt_pct(self.by_split["dev"].retention),
            "test_precision": _fmt_pct(self.by_split["test"].precision),
            "test_retention": _fmt_pct(self.by_split["test"].retention),
            "unverifiable_rate": _fmt_pct(_unverifiable_rate(self.overall)),
            "description": self.description,
        }


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def _unverifiable_rate(score: SplitScore) -> float | None:
    if score.emitted == 0:
        return None
    return (score.emitted - score.claim_aligned) / score.emitted


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_gold(path: Path, *, require_labels: bool = True) -> list[GoldClaim]:
    """Load the frozen audit CSV; every row must be labelled and split."""
    rows = read_audit(path)
    claims: list[GoldClaim] = []
    for row in rows:
        label = (row.get("label") or "").strip()
        split = (row.get("split") or "").strip()
        if require_labels and (not label or label not in LABELS):
            raise AblationError(f"{path}: gold row {row.get('claim_id')} is not labelled correctly")
        if split not in SPLITS:
            raise AblationError(f"{path}: gold row {row.get('claim_id')} has no dev/test split")
        claims.append(
            GoldClaim(
                claim_id=row["claim_id"],
                paper_id=row["paper_id"],
                split=split,
                label=label or "UNLABELLED",
                section=row.get("section") or "",
                evidence_span=row.get("evidence_span") or "",
            )
        )
    if not claims:
        raise AblationError(f"{path}: no gold claims")
    paper_splits: dict[str, set[str]] = defaultdict(set)
    for claim in claims:
        paper_splits[claim.paper_id].add(claim.split)
    leaking = sorted(paper for paper, splits in paper_splits.items() if len(splits) > 1)
    if leaking:
        raise AblationError(f"a paper appears in both splits: {', '.join(leaking[:5])}")
    return claims


def load_config_claims(path: Path) -> list[ConfigClaim]:
    """Read a silver-claims JSONL (teacher run) or a harness claims JSONL."""
    claims: list[ConfigClaim] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AblationError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(raw, dict):
                raise AblationError(f"{path}:{line_number}: row is not an object")
            # Teacher silver rows nest the claim under "claim".
            nested = raw.get("claim")
            source = nested if isinstance(nested, dict) else raw
            paper_id = raw.get("paper_id") or raw.get("pmcid")
            evidence = source.get("evidence_span")
            section = source.get("section")
            if not isinstance(paper_id, str) or not isinstance(evidence, str):
                raise AblationError(f"{path}:{line_number}: missing paper_id or evidence_span")
            claims.append(
                ConfigClaim(
                    paper_id=paper_id,
                    section=str(section or ""),
                    evidence_span=evidence,
                )
            )
    if not claims:
        raise AblationError(f"{path}: no claims")
    return claims


def _paper_ids_from(path: Path) -> set[str]:
    ids: set[str] = set()
    if not path.exists():
        return ids
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and isinstance(row.get("paper_id"), str):
            ids.add(str(row["paper_id"]))
    return ids


@dataclass
class DocumentIndex:
    """Cached source documents, for mapping a span to its sentence."""

    source_dir: Path
    _documents: dict[str, BaselineDocument | None]

    @classmethod
    def load(cls, source_dir: Path) -> DocumentIndex:
        return cls(source_dir=source_dir, _documents={})

    def document(self, paper_id: str) -> BaselineDocument | None:
        if paper_id not in self._documents:
            path = self.source_dir / f"{paper_id}.xml"
            if not path.exists():
                self._documents[paper_id] = None
            else:
                from axion.parse.jats import JatsParseError, parse_jats_file

                try:
                    from axion.extract.claims import build_baseline_document

                    self._documents[paper_id] = build_baseline_document(
                        parse_jats_file(path, paper_id=paper_id)
                    )
                except JatsParseError:
                    self._documents[paper_id] = None
        return self._documents[paper_id]

    def sentence_key(self, paper_id: str, section: str, span: str) -> str | None:
        """Normalized sentence containing ``span``, or ``None`` if unavailable."""
        document = self.document(paper_id)
        if document is None:
            return None
        return sentence_key(document, section_label=section, evidence_span=span)


def sentence_key(
    document: BaselineDocument, *, section_label: str, evidence_span: str
) -> str | None:
    """Return the normalized sentence that contains the claim's span.

    This is the shared unit for claim-level (teacher) and sentence-level
    (student) output: both are scored on the sentence they select or fall in.
    """
    by_label = {section.label.casefold(): section for section in document.sections}
    section = by_label.get(section_label.casefold())
    candidates = [section] if section is not None else list(document.sections)
    for candidate in candidates:
        match = find_evidence_span(candidate.text, evidence_span)
        if match is None:
            continue
        for start, end in sentence_bounds(candidate.text):
            if start <= match.start < end or start < match.end <= end:
                return normalize_for_match(candidate.text[start:end]).casefold()
    return None


def span_key(section: str, evidence_span: str) -> str:
    return normalize_for_match(evidence_span).casefold()


def _keys_for(
    claims: Sequence[ConfigClaim],
    *,
    matching: Matching,
    index: DocumentIndex,
) -> list[str | None]:
    keys: list[str | None] = []
    for claim in claims:
        if matching == "span":
            keys.append(span_key(claim.section, claim.evidence_span))
        else:
            keys.append(index.sentence_key(claim.paper_id, claim.section, claim.evidence_span))
    return keys


def score(
    gold: Sequence[GoldClaim],
    claims: Sequence[ConfigClaim],
    *,
    matching: Matching,
    index: DocumentIndex,
) -> tuple[dict[str, SplitScore], SplitScore]:
    """Compute aligned precision and retention per split and overall.

    The unit for precision is the **gold row**: a configuration "covers" a gold
    claim when it emits a claim in the same sentence (or with the same span).
    That keeps a replay reproducible at exactly the audit's 193/200. Per-emitted
    claim counts are reported as secondary columns so duplicates and
    unverifiable output stay visible.
    """
    gold_keys: dict[str, str | None] = {}
    for row in gold:
        gold_keys[row.claim_id] = (
            span_key(row.section, row.evidence_span)
            if matching == "span"
            else index.sentence_key(row.paper_id, row.section, row.evidence_span)
        )
    keys = _keys_for(claims, matching=matching, index=index)
    claims_by_key: dict[str, list[ConfigClaim]] = defaultdict(list)
    for claim, key in zip(claims, keys, strict=True):
        if key is None:
            continue
        claims_by_key[key].append(claim)

    gold_papers = {row.paper_id for row in gold}
    evaluated = [
        (claim, key)
        for claim, key in zip(claims, keys, strict=True)
        if claim.paper_id in gold_papers
    ]
    labels_by_key: dict[str, list[str]] = defaultdict(list)
    for row in gold:
        key = gold_keys[row.claim_id]
        if key is not None:
            labels_by_key[key].append(row.label)

    def score_subset(gold_rows: Sequence[GoldClaim], name: str) -> SplitScore:
        paper_set = {row.paper_id for row in gold_rows}
        subset = [(claim, key) for claim, key in evaluated if claim.paper_id in paper_set]
        emitted = len(subset)
        claim_aligned = 0
        claim_correct = 0
        for _, key in subset:
            if key is None:
                continue
            labels = labels_by_key.get(key)
            if not labels:
                continue
            claim_aligned += 1
            if all(label == "CORRECT" for label in labels):
                claim_correct += 1
        retained = 0
        correct = 0
        for row in gold_rows:
            key = gold_keys[row.claim_id]
            if key is None or key not in claims_by_key:
                continue
            retained += 1
            if row.label == "CORRECT":
                correct += 1
        precision = correct / retained if retained else None
        low, high = wilson_interval(correct, retained) if retained else (None, None)
        return SplitScore(
            split=name,
            gold=len(gold_rows),
            retained=retained,
            retention=retained / len(gold_rows) if gold_rows else 0.0,
            aligned=retained,
            aligned_correct=correct,
            precision=precision,
            precision_ci_low=low,
            precision_ci_high=high,
            emitted=emitted,
            claim_aligned=claim_aligned,
            claim_correct=claim_correct,
        )

    by_split = {
        split: score_subset([row for row in gold if row.split == split], split) for split in SPLITS
    }
    overall = score_subset(gold, "all")
    return by_split, overall


@dataclass(frozen=True)
class CostSummary:
    usd: Decimal
    calls: int
    cache_hits: int
    measured: bool


def ledger_cost(ledger_paths: Sequence[Path], run_ids: Sequence[str]) -> CostSummary:
    """Sum list-price cost and cache hits for the given runs."""
    if not run_ids:
        return CostSummary(usd=Decimal("0"), calls=0, cache_hits=0, measured=False)
    from axion.llm.ledger import SQLiteLedger

    total = Decimal("0")
    calls = 0
    hits = 0
    found = False
    for ledger_path in ledger_paths:
        if not ledger_path.exists():
            continue
        ledger = SQLiteLedger(ledger_path)
        for run_id in run_ids:
            rows = ledger.calls_for_run(run_id)
            if not rows:
                continue
            found = True
            for row in rows:
                if row.cache_hit:
                    hits += 1
                    continue
                if row.error is not None:
                    continue
                calls += 1
                total += row.usd or Decimal("0")
    return CostSummary(usd=total, calls=calls, cache_hits=hits, measured=found)


def _config_paths(config: AblationConfig) -> tuple[Path, list[Path]]:
    claims = Path(config.claims_path)
    ledgers = [Path(path) for path in config.ledgers]
    return claims, ledgers


def evaluate_config(
    config: AblationConfig,
    *,
    gold_path: Path,
    source_dir: Path,
) -> ConfigScore:
    gold = load_gold(gold_path)
    claims_path, ledgers = _config_paths(config)
    claims = load_config_claims(claims_path)
    index = DocumentIndex.load(source_dir)
    by_split, overall = score(gold, claims, matching=config.matching, index=index)

    papers: set[str] = set()
    if config.paper_ids_path:
        papers |= _paper_ids_from(Path(config.paper_ids_path))
    papers |= {claim.paper_id for claim in claims}
    paper_count = config.paper_count or len(papers)
    gold_papers = {row.paper_id for row in gold}
    cost = ledger_cost(ledgers, config.run_ids)
    cost_usd = cost.usd if cost.measured else None
    per_paper = (cost.usd / paper_count) if cost.measured and paper_count else None
    per_retained = None
    if per_paper is not None and overall.retained:
        per_retained = cost.usd / overall.retained
    return ConfigScore(
        config=config.name,
        description=config.description,
        kind=config.kind,
        matching=config.matching,
        config_sha256=hashlib.sha256(config.canonical().encode("utf-8")).hexdigest(),
        claims_sha256=sha256_file(claims_path) if claims_path.exists() else None,
        gold_sha256=sha256_file(gold_path),
        papers=paper_count,
        claims=len(claims),
        claims_per_paper=len(claims) / paper_count if paper_count else 0.0,
        evaluation_papers=len(gold_papers),
        evaluation_claims=overall.emitted,
        cost_usd=None if cost_usd is None else format(cost_usd, "f"),
        cost_per_paper_usd=None if per_paper is None else f"{per_paper:.9f}",
        cost_per_retained_claim_usd=None if per_retained is None else f"{per_retained:.9f}",
        cache_hits=cost.cache_hits,
        calls=cost.calls,
        by_split=by_split,
        overall=overall,
    )


def load_configs(directory: Path) -> dict[str, AblationConfig]:
    configs: dict[str, AblationConfig] = {}
    for path in sorted(directory.glob("*.json")):
        config = AblationConfig.model_validate_json(path.read_text(encoding="utf-8"))
        if config.name in configs:
            raise AblationError(f"duplicate config name {config.name!r}")
        configs[config.name] = config
    if not configs:
        raise AblationError(f"no ablation configs in {directory}")
    return configs


def _ci(score_row: SplitScore) -> str:
    precision = score_row.precision
    low = score_row.precision_ci_low
    high = score_row.precision_ci_high
    if precision is None or low is None or high is None:
        return "n/a"
    return f"{precision * 100:.1f}% [{low * 100:.1f}-{high * 100:.1f}]"


def render_report(scores: Sequence[ConfigScore], *, baseline_name: str = "baseline") -> str:
    lines = [
        "# P2 ablation results",
        "",
        "> Generated by `python scripts/ablate.py --all` from the frozen gold audit and the",
        "> ledger. **Gold measures precision only.** It labels 200 baseline claims from 45 papers.",
        "> Retention is agreement with the baseline's own output, **not recall**; absolute recall",
        "> is unmeasured. Claims that align with no gold row are **unverifiable** and are never",
        "> counted as correct.",
        "",
        "## Quality definition",
        "",
        "- **Aligned precision**: `CORRECT / aligned` over output that matches a gold-labelled",
        "  baseline claim (same sentence; see the `matching` column). Wilson 95% CI.",
        "- **Retention**: share of the 200 gold claims the configuration still emits.",
        "- **Unverifiable rate**: share of evaluated output that matches no gold row.",
        "- **Cost**: list-price USD from the ledger. Free tier: real spend is $0.",
        "",
        "## Configurations",
        "",
        "| Config | Papers | Claims | Claims/paper | $/paper | Dev precision | Dev retention | "
        "Test precision | Test retention | Unverifiable | Matching | Notes |",
        "| :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | :-- | :-- |",
    ]
    for score_row in scores:
        unverifiable = _unverifiable_rate(score_row.overall)
        cost = "-" if score_row.cost_per_paper_usd is None else "$" + score_row.cost_per_paper_usd
        lines.append(
            f"| `{score_row.config}` | {score_row.papers} | {score_row.claims} | "
            f"{score_row.claims_per_paper:.2f} | {cost} | "
            f"{_ci(score_row.by_split['dev'])} | "
            f"{_fmt_pct(score_row.by_split['dev'].retention)} | "
            f"{_ci(score_row.by_split['test'])} | "
            f"{_fmt_pct(score_row.by_split['test'].retention)} | "
            f"{_fmt_pct(unverifiable)} | {score_row.matching} | {score_row.description} |"
        )
    lines += [
        "",
        "## Detail",
        "",
        "| Config | Split | n gold | Retained | Retention | Aligned rows | Correct rows | "
        "Emitted claims | Aligned claims | Cost USD | Calls | Cache hits |",
        "| :-- | :-- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |",
    ]
    for score_row in scores:
        for split in (*SPLITS, "all"):
            row = score_row.by_split.get(split, score_row.overall)
            lines.append(
                f"| `{score_row.config}` | {split} | {row.gold} | {row.retained} | "
                f"{_fmt_pct(row.retention)} | {row.aligned} | {row.aligned_correct} | "
                f"{row.emitted} | {row.claim_aligned} | {score_row.cost_usd or '-'} | "
                f"{score_row.calls} | {score_row.cache_hits} |"
            )
    lines += [
        "",
        "## Baseline tolerance",
        "",
        f"- Baseline config: `{baseline_name}`; expected aligned precision "
        f"**{BASELINE_PRECISION:.1%}**, retention **100.0%**.",
        "",
        "## Limits (repeat in every P2 report)",
        "",
        "- Gold has one primary labeler; agreement covers a 20% independent overlap with no",
        "  `NOT_A_CLAIM` rows, so error-class agreement is unmeasured.",
        "- Gold samples baseline output: **absolute recall is unknown** and not reported.",
        "- 45 papers is a small cluster count; claims within a paper are not independent.",
        "- Aligned precision is conditional on alignment; unverifiable output is counted,",
        "  not scored.",
        "- Structured claim fields (`claim_type`, population, direction) are outside this",
        "  measurement.",
        "",
    ]
    return "\n".join(lines)


def baseline_check(score_row: ConfigScore) -> dict[str, object]:
    """Compare a replay against the frozen P1 values; no tolerance games."""
    test = score_row.by_split["test"]
    dev = score_row.by_split["dev"]
    overall = score_row.overall
    # Exact ratio comparison: a replay must reproduce 193/200, not a rounded number.
    precision_exact = overall.aligned > 0 and overall.aligned_correct * 200 == 193 * overall.aligned
    return {
        "precision": overall.precision,
        "expected_precision": BASELINE_PRECISION,
        "precision_matches": precision_exact,
        "retention": overall.retention,
        "retention_complete": overall.retention == 1.0,
        "unverifiable": _unverifiable_rate(overall),
        "dev_precision": dev.precision,
        "test_precision": test.precision,
        "cost_per_paper_usd": score_row.cost_per_paper_usd,
        "cost_measured": score_row.cost_per_paper_usd is not None,
    }


__all__ = [
    "BASELINE_PRECISION",
    "BASELINE_RUN_ID",
    "AblationConfig",
    "AblationError",
    "ConfigClaim",
    "ConfigScore",
    "DocumentIndex",
    "GoldClaim",
    "SplitScore",
    "baseline_check",
    "evaluate_config",
    "ledger_cost",
    "load_config_claims",
    "load_configs",
    "load_gold",
    "render_report",
    "score",
    "sentence_key",
    "sha256_file",
    "span_key",
]
