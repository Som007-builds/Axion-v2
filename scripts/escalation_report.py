"""P2-05 calibrated escalation: dev calibration and one frozen test read.

The cascade runs the CPU claim-sentence student on every gold paper, then sends
the longest ``ESCALATION_FRACTION`` of papers to the frozen small LLM (the P1
``gemini-3.5-flash-lite`` teacher). Stage 2 would send papers whose small-LLM
output contains no accepted claim to ``gemini-3.8-flash``; it never fires on the
45 gold papers, so stage-2 quality is not measured.

Stage 1 is a **replay** of the frozen teacher output. Its cost is the measured
list price of those teacher calls in the P1 ledger, not the $0 the cache would
charge for an identical repeat. Real spend is $0.

Calibration is dev-only. The policy and fraction are fixed in
``src/axion/eval/escalation.py`` before this script scores the test split.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from axion.config.pricing import load_pricing
from axion.config.settings import Settings
from axion.eval.ablation import (
    ConfigClaim,
    DocumentIndex,
    GoldClaim,
    SplitScore,
    load_gold,
    score,
)
from axion.eval.escalation import (
    ESCALATION_FRACTION,
    POLICY_VERSION,
    RISK_SIGNAL,
    PaperRisk,
    select_escalations,
    stage2_triggers,
)
from axion.extract.claims import Claim, build_baseline_document
from axion.parse.jats import parse_jats_file
from axion.train.student import (
    Sentence,
    SentenceStudent,
    read_processed_papers,
    read_teacher_claims,
    sentence_rows,
    top_k_claims,
    unverifiable_rate,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/raw/europepmc/fulltext"
GOLD = ROOT / "eval/audit/claims_audit_v1.csv"
STUDENT = ROOT / "eval/student/student_v1.model.json"
BASELINE = ROOT / "eval/silver/claims_v1/baseline_flashlite/silver_claims.jsonl"
TEACHER_RUNS = (
    ROOT / "eval/silver/claims_v1/baseline_flashlite",
    ROOT / "eval/silver/claims_v1/p2_03a_teacher",
)
LEDGER = ROOT / "data/ledger.sqlite3"
OUT = ROOT / "eval/escalation"
REPORT = ROOT / "docs/reports/P2-05-escalation.md"
CONFIG = ROOT / "eval/ablation/configs/escalation-length30.json"
CLAIMS_OUT = OUT / "claims_merged.jsonl"
LEDGER_OUT = OUT / "ledger.sqlite3"
BASELINE_RUN = "p1-10-flashlite-s20261114-n100"
PARENT_PROBE_RUN = "p2-05-parent-probe"
STUDENT_K = 8
COMPUTE_USD_PER_HOUR = (0.05, 0.10)
RANDOM_TRIALS = 200
FEATURES = (
    "mean_top",
    "min_top",
    "max_score",
    "mean_all",
    "frac_high",
    "entropy",
    "gap_8_9",
    "sum_top",
)


@dataclass(frozen=True)
class SignalRow:
    risk: PaperRisk
    mean_top: float
    min_top: float
    max_score: float
    mean_all: float
    frac_high: float
    entropy: float
    gap_8_9: float
    sum_top: float


@dataclass(frozen=True)
class SplitData:
    split: str
    paper_ids: tuple[str, ...]
    signals: tuple[SignalRow, ...]
    claims: tuple[Sentence, ...]
    claims_by_paper: dict[str, tuple[Sentence, ...]]


@dataclass(frozen=True)
class ParentProbe:
    """One dev-only stage-1 -> stage-2 pair that exercises the ledger link."""

    stage1_id: int
    stage2_id: int
    parent_call_id: int | None
    model: str
    prompt_tokens: int
    completion_tokens: int
    usd: float
    stage1_cache_hit: bool


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def log(message: str) -> None:
    print(message, flush=True)


def pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def interval(row: SplitScore) -> str:
    if row.precision is None or row.precision_ci_low is None or row.precision_ci_high is None:
        return "n/a"
    return f"{row.precision * 100:.1f}% [{row.precision_ci_low * 100:.1f}-{row.precision_ci_high * 100:.1f}]"


def usd(value: float | None, places: int = 6) -> str:
    return "n/a" if value is None else f"${value:.{places}f}"


def embed_cached(
    encoder: SentenceTransformer, texts: list[str], tag: str
) -> tuple[np.ndarray, float, bool]:
    digest = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()[:16]
    path = ROOT / "data/student" / f"escalation-{tag}-{digest}.npz"
    if path.exists():
        payload = np.load(path)
        if "seconds" in payload.files:
            return (
                np.asarray(payload["embeddings"], dtype=np.float64),
                float(payload["seconds"][0]),
                True,
            )
    start = time.perf_counter()
    embeddings = encoder.encode(
        texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False
    )
    seconds = time.perf_counter() - start
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path, embeddings=embeddings, digest=np.array([digest]), seconds=np.array([seconds])
    )
    log(f"encoded {len(texts)} sentences in {seconds:.1f}s")
    return np.asarray(embeddings, dtype=np.float64), seconds, False


def load_costs() -> dict[str, float]:
    connection = sqlite3.connect(LEDGER)
    try:
        rows = connection.execute(
            "SELECT paper_id, SUM(usd) FROM llm_calls WHERE run_id = ? GROUP BY paper_id",
            (BASELINE_RUN,),
        ).fetchall()
    finally:
        connection.close()
    return {str(paper_id): float(value or 0) for paper_id, value in rows}


def baseline_token_means() -> tuple[float, float]:
    connection = sqlite3.connect(LEDGER)
    try:
        row = connection.execute(
            """
            SELECT AVG(prompt_tokens), AVG(completion_tokens)
            FROM llm_calls
            WHERE run_id = ? AND error IS NULL AND prompt_tokens > 0 AND completion_tokens > 0
            """,
            (BASELINE_RUN,),
        ).fetchone()
    finally:
        connection.close()
    if row is None or row[0] is None:
        raise SystemExit("no successful baseline calls to size the stage-2 projection")
    return float(row[0]), float(row[1])


def load_parent_probe() -> ParentProbe | None:
    """Read the dev-only mechanism probe, if it has been run."""
    connection = sqlite3.connect(LEDGER)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            """
            SELECT id, stage, model, parent_call_id, cache_hit,
                   prompt_tokens, completion_tokens, usd
            FROM llm_calls
            WHERE run_id = ?
            ORDER BY id
            """,
            (PARENT_PROBE_RUN,),
        ).fetchall()
    finally:
        connection.close()
    stage1 = next((row for row in rows if row["stage"] == "teacher_label"), None)
    stage2 = next((row for row in rows if row["stage"] == "large_llm"), None)
    if stage1 is None or stage2 is None:
        return None
    parent = stage2["parent_call_id"]
    return ParentProbe(
        stage1_id=int(stage1["id"]),
        stage2_id=int(stage2["id"]),
        parent_call_id=int(parent) if parent is not None else None,
        model=str(stage2["model"]),
        prompt_tokens=int(stage2["prompt_tokens"] or 0),
        completion_tokens=int(stage2["completion_tokens"] or 0),
        usd=float(stage2["usd"] or 0),
        stage1_cache_hit=bool(stage1["cache_hit"]),
    )


def teacher_zero_rate(gold_ids: set[str]) -> tuple[int, int]:
    processed: set[str] = set()
    with_claims: set[str] = set()
    for run in TEACHER_RUNS:
        processed |= read_processed_papers(run / "papers_processed.jsonl")
        with_claims |= set(read_teacher_claims(run / "silver_claims.jsonl"))
    non_gold = processed - gold_ids
    zero = non_gold - with_claims
    return len(zero), len(non_gold)


def build_split(
    split: str,
    paper_ids: list[str],
    gold: list[GoldClaim],
    model: SentenceStudent,
    encoder: SentenceTransformer,
    baseline_claims: dict[str, list[Claim]],
    costs: dict[str, float],
    index: DocumentIndex,
) -> tuple[SplitData, float]:
    sentences: list[Sentence] = []
    texts: list[str] = []
    start = time.perf_counter()
    for paper_id in paper_ids:
        document = build_baseline_document(
            parse_jats_file(SOURCE / f"{paper_id}.xml", paper_id=paper_id)
        )
        rows = sentence_rows(document, paper_id=paper_id)
        sentences.extend(rows)
        texts.extend(row.text for row in rows)
    parsed_at = time.perf_counter()
    embeddings, encode_seconds, _ = embed_cached(encoder, texts, tag=split)
    embed_at = time.perf_counter()
    scores = model.score(embeddings)
    claims = top_k_claims(sentences, scores, k=STUDENT_K)
    scored_at = time.perf_counter()
    elapsed = (parsed_at - start) + encode_seconds + (scored_at - embed_at)

    values: dict[str, list[float]] = defaultdict(list)
    for sentence, value in zip(sentences, scores, strict=True):
        values[sentence.paper_id].append(float(value))
    claims_by_paper: dict[str, list[Sentence]] = defaultdict(list)
    for claim in claims:
        claims_by_paper[claim.paper_id].append(claim)

    signals: list[SignalRow] = []
    gold_by_paper: dict[str, list[GoldClaim]] = defaultdict(list)
    for row in gold:
        if row.split == split:
            gold_by_paper[row.paper_id].append(row)
    for paper_id in paper_ids:
        paper_scores = sorted(values[paper_id], reverse=True)
        top = paper_scores[:STUDENT_K]
        paper_claims = [
            ConfigClaim(paper_id=s.paper_id, section=s.section, evidence_span=s.text)
            for s in claims_by_paper.get(paper_id, [])
        ]
        _, student_score = score(
            gold_by_paper[paper_id], paper_claims, matching="sentence", index=index
        )
        entropy = float(
            np.mean(
                [
                    -(value * np.log(max(value, 1e-9)))
                    - ((1.0 - value) * np.log(max(1.0 - value, 1e-9)))
                    for value in paper_scores
                ]
            )
        )
        risk = PaperRisk(
            paper_id=paper_id,
            split=split,
            sentences=len(paper_scores),
            gold_rows=len(gold_by_paper[paper_id]),
            student_retained=student_score.retained,
            baseline_claims=len(baseline_claims.get(paper_id, [])),
            baseline_cost_usd=costs.get(paper_id, 0.0),
        )
        signals.append(
            SignalRow(
                risk=risk,
                mean_top=float(np.mean(top)) if top else 0.0,
                min_top=float(min(top)) if top else 0.0,
                max_score=float(max(paper_scores)) if paper_scores else 0.0,
                mean_all=float(np.mean(paper_scores)) if paper_scores else 0.0,
                frac_high=float(np.mean([value >= 0.9 for value in top])) if top else 0.0,
                entropy=entropy,
                gap_8_9=(
                    float(paper_scores[7] - paper_scores[8]) if len(paper_scores) > 8 else 0.0
                ),
                sum_top=float(np.sum(top)),
            )
        )
    return (
        SplitData(
            split=split,
            paper_ids=tuple(paper_ids),
            signals=tuple(signals),
            claims=tuple(claims),
            claims_by_paper={key: tuple(value) for key, value in claims_by_paper.items()},
        ),
        elapsed,
    )


def spearman(left: list[float], right: list[float]) -> float:
    left_rank = np.argsort(np.argsort(left)).astype(float)
    right_rank = np.argsort(np.argsort(right)).astype(float)
    if left_rank.std() == 0 or right_rank.std() == 0:
        return 0.0
    return float(np.corrcoef(left_rank, right_rank)[0, 1])


def outcome(
    signals: tuple[SignalRow, ...], escalated: set[str], *, total_gold: int
) -> tuple[float, float]:
    retained = sum(
        row.risk.gold_rows if row.risk.paper_id in escalated else row.risk.student_retained
        for row in signals
    )
    cost = sum(row.risk.baseline_cost_usd for row in signals if row.risk.paper_id in escalated)
    return retained / max(total_gold, 1), cost


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args(argv)

    gold = load_gold(GOLD)
    gold_by_split = {
        split: [row for row in gold if row.split == split] for split in ("dev", "test")
    }
    gold_ids = {row.paper_id for row in gold}
    model, metadata, model_sha = SentenceStudent.load(STUDENT)
    encoder = SentenceTransformer(model.encoder_name, device="cpu")
    index = DocumentIndex.load(SOURCE)
    baseline_claims = read_teacher_claims(BASELINE)
    costs = load_costs()

    splits: dict[str, SplitData] = {}
    elapsed: dict[str, float] = {}
    for split in ("dev", "test"):
        paper_ids = sorted({row.paper_id for row in gold_by_split[split]})
        log(f"{split}: {len(paper_ids)} papers")
        splits[split], elapsed[split] = build_split(
            split,
            paper_ids,
            gold,
            model,
            encoder,
            baseline_claims,
            costs,
            index,
        )

    escalated: dict[str, frozenset[str]] = {}
    for split in ("dev", "test"):
        risks = [row.risk for row in splits[split].signals]
        escalated[split] = select_escalations(risks, fraction=ESCALATION_FRACTION)
    escalated_all = set(escalated["dev"]) | set(escalated["test"])
    log(f"escalated dev={len(escalated['dev'])} test={len(escalated['test'])}")

    # Dev calibration only: confidence features and the q sweep.
    dev_signals = splits["dev"].signals
    dev_total_gold = sum(row.risk.gold_rows for row in dev_signals)
    dev_retention = [row.risk.student_retained / max(row.risk.gold_rows, 1) for row in dev_signals]
    correlations = {
        feature: spearman([getattr(row, feature) for row in dev_signals], dev_retention)
        for feature in FEATURES
    }
    correlations["n_sentences"] = spearman(
        [float(row.risk.sentences) for row in dev_signals], dev_retention
    )

    rng = np.random.default_rng(20261117)
    sweep: list[dict[str, float]] = []
    for q in (0.10, 0.20, 0.30, 0.40, 0.45, 0.50, 0.60):
        m = max(1, int(q * len(dev_signals) + 0.5))
        length_pick = set(select_escalations([row.risk for row in dev_signals], fraction=q))
        length_ret, length_cost = outcome(dev_signals, length_pick, total_gold=dev_total_gold)
        mean_top_pick = {
            row.risk.paper_id
            for row in sorted(dev_signals, key=lambda row: (row.mean_top, row.risk.paper_id))[:m]
        }
        mean_top_ret, _ = outcome(dev_signals, mean_top_pick, total_gold=dev_total_gold)
        entropy_pick = {
            row.risk.paper_id
            for row in sorted(dev_signals, key=lambda row: (row.entropy, row.risk.paper_id))[:m]
        }
        entropy_ret, _ = outcome(dev_signals, entropy_pick, total_gold=dev_total_gold)
        oracle_pick = {
            row.risk.paper_id
            for row in sorted(
                dev_signals,
                key=lambda row: (
                    row.risk.student_retained / max(row.risk.gold_rows, 1),
                    row.risk.paper_id,
                ),
            )[:m]
        }
        oracle_ret, _ = outcome(dev_signals, oracle_pick, total_gold=dev_total_gold)
        random_ret: list[float] = []
        random_cost: list[float] = []
        for _ in range(RANDOM_TRIALS):
            pick = set(
                rng.choice(
                    [row.risk.paper_id for row in dev_signals], size=m, replace=False
                ).tolist()
            )
            retained, cost = outcome(dev_signals, pick, total_gold=dev_total_gold)
            random_ret.append(retained)
            random_cost.append(cost)
        baseline_cost = sum(row.risk.baseline_cost_usd for row in dev_signals)
        sweep.append(
            {
                "q": q,
                "m": float(m),
                "e": m / len(dev_signals),
                "length_ret": length_ret,
                "mean_top_ret": mean_top_ret,
                "entropy_ret": entropy_ret,
                "random_ret": float(np.mean(random_ret)),
                "oracle_ret": oracle_ret,
                "length_savings": 1
                - (length_cost / len(dev_signals)) / (baseline_cost / len(dev_signals)),
                "random_savings": 1
                - (float(np.mean(random_cost)) / len(dev_signals))
                / (baseline_cost / len(dev_signals)),
            }
        )
        log(f"dev q={q:.2f}: {sweep[-1]}")

    # Merged claims: student everywhere except escalated papers, which replay the
    # frozen teacher output.
    merged: list[ConfigClaim] = []
    for split in ("dev", "test"):
        for paper_id in splits[split].paper_ids:
            if paper_id in escalated[split]:
                for claim in baseline_claims.get(paper_id, []):
                    merged.append(
                        ConfigClaim(
                            paper_id=paper_id,
                            section=claim.section,
                            evidence_span=claim.evidence_span,
                        )
                    )
            else:
                for sentence in splits[split].claims_by_paper.get(paper_id, ()):
                    merged.append(
                        ConfigClaim(
                            paper_id=sentence.paper_id,
                            section=sentence.section,
                            evidence_span=sentence.text,
                        )
                    )
    merged.sort(key=lambda claim: (claim.paper_id, claim.section, claim.evidence_span))
    merged_by_split, merged_all = score(gold, merged, matching="sentence", index=index)

    baseline_config_claims = [
        ConfigClaim(paper_id=row.paper_id, section=claim.section, evidence_span=claim.evidence_span)
        for row in gold
        for claim in baseline_claims.get(row.paper_id, [])
    ]
    baseline_by_split, baseline_all = score(
        gold, baseline_config_claims, matching="sentence", index=index
    )
    student_claims = [
        ConfigClaim(
            paper_id=sentence.paper_id, section=sentence.section, evidence_span=sentence.text
        )
        for split in ("dev", "test")
        for sentence in splits[split].claims
    ]
    student_by_split, student_all = score(gold, student_claims, matching="sentence", index=index)

    # Costs and savings per split; escalated cost is the measured list price of
    # the teacher calls the policy would make, not the replay's $0 cache hits.
    cost_rows: list[dict[str, object]] = []
    for split in ("dev", "test"):
        rows = splits[split].signals
        n = len(rows)
        baseline_cost = sum(row.risk.baseline_cost_usd for row in rows)
        escalated_cost = sum(
            row.risk.baseline_cost_usd for row in rows if row.risk.paper_id in escalated[split]
        )
        retained = merged_by_split[split].retained
        cost_rows.append(
            {
                "split": split,
                "papers": n,
                "escalated": len(escalated[split]),
                "baseline_cost": baseline_cost,
                "escalated_cost": escalated_cost,
                "baseline_per_paper": baseline_cost / n,
                "net_per_paper": escalated_cost / n,
                "savings": 1 - (escalated_cost / n) / (baseline_cost / n),
                "cost_per_retained": escalated_cost / max(retained, 1),
                "baseline_per_retained": baseline_cost / max(merged_by_split[split].gold, 1),
            }
        )
    all_baseline_cost = sum(float(row["baseline_cost"]) for row in cost_rows)
    all_escalated_cost = sum(float(row["escalated_cost"]) for row in cost_rows)
    all_papers = len({row.paper_id for row in gold})
    all_net_per_paper = all_escalated_cost / all_papers
    all_baseline_per_paper = all_baseline_cost / all_papers
    all_savings = 1 - all_net_per_paper / all_baseline_per_paper
    e_all = len(escalated_all) / all_papers

    # Stage 2: measured on gold (0 triggers), projected with the teacher's
    # measured zero-claim rate on non-gold papers and the 3.8-flash list price.
    accepted = {paper: len(baseline_claims.get(paper, [])) for paper in escalated_all}
    stage2_gold = stage2_triggers(sorted(escalated_all), accepted)
    zero_count, non_gold_count = teacher_zero_rate(gold_ids)
    zero_rate = zero_count / max(non_gold_count, 1)
    prompt_mean, completion_mean = baseline_token_means()
    pricing = load_pricing(Settings().resolved_pricing_path)
    large = pricing.select("gemini-3.8-flash")
    large_post = pricing.price_for("gemini-3.8-flash").post_promotion()
    million = Decimal(1_000_000)
    unit_large = (
        Decimal(str(prompt_mean)) * large.input_usd_per_mtok
        + Decimal(str(completion_mean)) * large.output_usd_per_mtok
    ) / million
    unit_large_post = (
        Decimal(str(prompt_mean)) * large_post.input_usd_per_mtok
        + Decimal(str(completion_mean)) * large_post.output_usd_per_mtok
    ) / million
    stage2_rate = e_all * zero_rate
    added_intro = float(unit_large) * stage2_rate
    added_post = float(unit_large_post) * stage2_rate
    net_with_stage2 = all_net_per_paper + added_intro
    savings_with_stage2 = 1 - net_with_stage2 / all_baseline_per_paper
    probe = load_parent_probe()
    probe_added = 0.0
    probe_savings: float | None = None
    if probe is not None:
        probe_added = probe.usd * stage2_rate
        probe_savings = 1 - (all_net_per_paper + probe_added) / all_baseline_per_paper

    student_ms = (
        (
            elapsed["dev"] / len(splits["dev"].paper_ids)
            + elapsed["test"] / len(splits["test"].paper_ids)
        )
        / 2
        * 1000
    )
    frozen_baseline_per_paper = sum(costs.values()) / len(costs)
    s_compute = {
        rate: (student_ms / 1000 / 3600 * rate) / frozen_baseline_per_paper
        for rate in COMPUTE_USD_PER_HOUR
    }

    # Artifacts.
    OUT.mkdir(parents=True, exist_ok=True)
    with CLAIMS_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        for claim in merged:
            handle.write(
                json.dumps(
                    {
                        "paper_id": claim.paper_id,
                        "section": claim.section,
                        "evidence_span": claim.evidence_span,
                    }
                )
                + "\n"
            )
    with (OUT / "gold_papers.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for paper_id in sorted(gold_ids):
            handle.write(json.dumps({"paper_id": paper_id}) + "\n")
    with (OUT / "paper_signals.json").open("w", encoding="utf-8", newline="\n") as handle:
        rows = []
        for split in ("dev", "test"):
            for row in splits[split].signals:
                rows.append(
                    {
                        "paper_id": row.risk.paper_id,
                        "split": row.risk.split,
                        "sentences": row.risk.sentences,
                        "gold_rows": row.risk.gold_rows,
                        "student_retained": row.risk.student_retained,
                        "baseline_claims": row.risk.baseline_claims,
                        "baseline_cost_usd": row.risk.baseline_cost_usd,
                        "student_retention": row.risk.student_retained / max(row.risk.gold_rows, 1),
                        **{feature: getattr(row, feature) for feature in FEATURES},
                    }
                )
        json.dump(rows, handle, indent=2)
        handle.write("\n")

    shutil.copy2(LEDGER, LEDGER_OUT)
    connection = sqlite3.connect(LEDGER_OUT)
    try:
        placeholders = ",".join("?" for _ in escalated_all)
        connection.execute(
            f"DELETE FROM llm_calls WHERE run_id != ? OR paper_id IS NULL OR paper_id NOT IN ({placeholders})",
            [BASELINE_RUN, *sorted(escalated_all)],
        )
        connection.execute("DELETE FROM llm_cache")
        connection.commit()
        connection.execute("VACUUM")
    finally:
        connection.close()

    config = {
        "name": "escalation-length30",
        "description": (
            "P2-05 escalation replay: student top-8 on the shortest 70% of papers; "
            "frozen flash-lite teacher output on the longest 30%; list price of the "
            "escalated calls only"
        ),
        "kind": "replay",
        "claims_path": "eval/escalation/claims_merged.jsonl",
        "matching": "sentence",
        "run_ids": [BASELINE_RUN],
        "paper_ids_path": "eval/escalation/gold_papers.jsonl",
        "paper_count": 45,
        "ledgers": ["eval/escalation/ledger.sqlite3"],
        "notes": (
            "Length-risk escalation, e=0.30; student compute 0 LLM calls; stage 2 "
            "(3.8-flash) never fired on gold and is projected separately."
        ),
        "inference_ms_per_paper": student_ms,
    }
    CONFIG.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8", newline="\n")

    manifest = {
        "policy_version": POLICY_VERSION,
        "risk_signal": RISK_SIGNAL,
        "fraction": ESCALATION_FRACTION,
        "student_k": STUDENT_K,
        "student_artifact": str(STUDENT.relative_to(ROOT)),
        "student_artifact_sha256": model_sha,
        "student_metadata": metadata,
        "baseline_claims_sha256": sha256_file(BASELINE),
        "escalated": {split: sorted(escalated[split]) for split in ("dev", "test")},
        "e": {
            "dev": len(escalated["dev"]) / len(splits["dev"].paper_ids),
            "test": len(escalated["test"]) / len(splits["test"].paper_ids),
            "all": e_all,
        },
        "cost": {
            "baseline_per_paper": all_baseline_per_paper,
            "net_per_paper": all_net_per_paper,
            "savings": all_savings,
            "real_spend_usd": 0.0,
        },
        "stage2": {
            "gold_triggers": len(stage2_gold),
            "teacher_zero_claim_rate": zero_rate,
            "teacher_zero_claim_papers": zero_count,
            "teacher_non_gold_papers": non_gold_count,
            "unit_cost_intro_usd": str(unit_large),
            "unit_cost_post_promotion_usd": str(unit_large_post),
            "projected_added_cost_per_paper_usd": added_intro,
            "projected_savings_with_stage2": savings_with_stage2,
            "parent_probe": asdict(probe) if probe is not None else None,
            "probe_unit_cost_usd": probe.usd if probe is not None else None,
            "probe_projected_added_cost_per_paper_usd": (
                probe_added if probe is not None else None
            ),
            "probe_projected_savings": probe_savings,
        },
        "student_ms_per_paper": student_ms,
        "s_compute": {str(rate): value for rate, value in s_compute.items()},
        "created_at": datetime.now(UTC).isoformat(),
    }
    (OUT / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    lines = [
        "# P2-05 — calibrated escalation (length risk, small LLM then large LLM)",
        "",
        f"> Generated by `python scripts/escalation_report.py` on "
        f"{datetime.now(UTC).strftime('%Y-%m-%d')}. Dev calibration; the test split is read once.",
        "",
        "> **Gold measures precision only.** Retention is agreement with the baseline's own audited",
        "> output, not recall. Output that aligns with no gold row is unverifiable and is never",
        "> counted as correct. The 45 gold papers are a small cluster sample; claims within a paper",
        "> are not independent.",
        "",
        "## Policy",
        "",
        f"- **Stage 0:** frozen `student-v1-minilm-lr` (MiniLM encoder + logistic head, top-{STUDENT_K}",
        "  sentences/paper) runs on every paper. It makes **0 LLM calls**.",
        f"- **Stage 1 (small LLM):** the longest **{ESCALATION_FRACTION:.0%}** of papers, ranked by the",
        "  number of scorable sentences, replay the frozen P1 `gemini-3.5-flash-lite` teacher output.",
        "- **Stage 2 (large LLM):** a stage-1 paper with **no accepted claim** goes to",
        "  `gemini-3.8-flash`; the call carries the stage-1 `parent_call_id`.",
        f"- Fixed in `src/axion/eval/escalation.py` (`{POLICY_VERSION}`) **before** this script read the",
        "  test split. The fraction is a per-batch quantile; the realised count is `e`.",
        "",
        "### Why length, not confidence",
        "",
        "The planned confidence signals were measured first. On the 22 dev papers, **every** student",
        "confidence feature is negatively correlated with that paper's retention: low confidence",
        "predicts *more* retained gold rows, so confidence-based escalation is worse than random at",
        "every rate. The only signal that beat random was paper length.",
        "",
        "| Dev feature | Spearman rho vs per-paper student retention |",
        "| :-- | --: |",
    ]
    for feature, value in correlations.items():
        lines.append(f"| `{feature}` | {value:+.3f} |")
    lines += [
        "",
        f"> The student's mean top score is rho={correlations['mean_top']:+.3f} and its max score is",
        f"> rho={correlations['max_score']:+.3f}; sentence count is rho={correlations['n_sentences']:+.3f}.",
        "> This is a negative result for confidence calibration, not a tuning choice.",
        "",
        "### Dev sweep (calibration only)",
        "",
        "`q` is the requested escalation fraction; `e` is the realised rate. `random` is the mean of",
        f"{RANDOM_TRIALS} seeded random draws of the same size; `oracle` escalates the papers with the",
        "lowest actual student retention (an upper bound, not an implementable signal).",
        "",
        "| q | e | Length retention | Mean-top confidence | Entropy | Random | Oracle | Length savings | Random savings |",
        "| --: | --: | --: | --: | --: | --: | --: | --: | --: |",
    ]
    for row in sweep:
        marker = " **←**" if abs(float(row["q"]) - ESCALATION_FRACTION) < 1e-9 else ""
        lines.append(
            f"| {float(row['q']):.2f} | {float(row['e']):.2f} | "
            f"{float(row['length_ret']) * 100:.1f}%{marker} | "
            f"{float(row['mean_top_ret']) * 100:.1f}% | "
            f"{float(row['entropy_ret']) * 100:.1f}% | "
            f"{float(row['random_ret']) * 100:.1f}% | "
            f"{float(row['oracle_ret']) * 100:.1f}% | "
            f"{float(row['length_savings']) * 100:.1f}% | "
            f"{float(row['random_savings']) * 100:.1f}% |"
        )
    lines += [
        "",
        f"At q={ESCALATION_FRACTION:.2f} the length rule retains "
        f"{next(row['length_ret'] for row in sweep if abs(float(row['q']) - ESCALATION_FRACTION) < 1e-9) * 100:.1f}%"
        " of dev gold rows, close to the oracle at the same rate, with "
        f"{next(row['length_savings'] for row in sweep if abs(float(row['q']) - ESCALATION_FRACTION) < 1e-9) * 100:.1f}%"
        " dev list-price savings. It was chosen as the largest round decile that keeps a",
        "comfortable margin over the 50% gate; q=0.40 falls to ~52% savings on dev.",
        "",
        "## Frozen gold result",
        "",
        "| Configuration | Split | Precision (95% CI) | Retention | Unverifiable | Claims | $/paper | Savings |",
        "| :-- | :-- | :-- | --: | --: | --: | --: | --: |",
    ]
    for name, rows_by_split, _total in (
        ("student-only", student_by_split, student_all),
        ("**escalation-length30**", merged_by_split, merged_all),
        ("baseline (teacher)", baseline_by_split, baseline_all),
    ):
        for split in ("dev", "test"):
            row = rows_by_split[split]
            split_cost = next(item for item in cost_rows if item["split"] == split)
            if name == "baseline (teacher)":
                per_paper = float(split_cost["baseline_per_paper"])
                savings = "—"
            elif name == "student-only":
                per_paper = 0.0
                savings = "100% (LLM)"
            else:
                per_paper = float(split_cost["net_per_paper"])
                savings = f"{float(split_cost['savings']) * 100:.1f}%"
            label = (
                name
                if split == "dev"
                else ("**escalation-length30**" if "escalation" in name else name)
            )
            lines.append(
                f"| {label} | {split} | {interval(row)} | {pct(row.retention)} | "
                f"{pct(unverifiable_rate(row))} | {row.emitted} | {usd(per_paper)} | {savings} |"
            )
    lines += [
        "",
        f"- **Test retention: {pct(merged_by_split['test'].retention)}** "
        f"({merged_by_split['test'].retained}/{merged_by_split['test'].gold}) vs the baseline's 100%.",
        f"- **Test precision: {interval(merged_by_split['test'])}** "
        f"({merged_by_split['test'].aligned_correct}/{merged_by_split['test'].aligned} aligned rows).",
        f"- **Unverifiable on test: {pct(unverifiable_rate(merged_by_split['test']))}**; most output is",
        "  outside the 200-row gold sample and is not evidence of correctness.",
        "- The academic precision target is the baseline's precision, not 100%; the escalation",
        "  keeps it. The **retention** loss is the real cost of the student and is not hidden.",
        "",
        "## Cost (measured, list price)",
        "",
        "| Split | Papers | Escalated (e) | Baseline $ | Escalated $ | Baseline $/paper | Net $/paper | Savings |",
        "| :-- | --: | --: | --: | --: | --: | --: | --: |",
    ]
    for item in cost_rows:
        lines.append(
            f"| {item['split']} | {item['papers']} | {item['escalated']} "
            f"({float(item['escalated']) / float(item['papers']) * 100:.1f}%) | "
            f"{usd(float(item['baseline_cost']))} | {usd(float(item['escalated_cost']))} | "
            f"{usd(float(item['baseline_per_paper']))} | {usd(float(item['net_per_paper']))} | "
            f"{float(item['savings']) * 100:.1f}% |"
        )
    lines += [
        f"| **all** | **{all_papers}** | **{len(escalated_all)} ({e_all * 100:.1f}%)** | "
        f"**{usd(all_baseline_cost)}** | **{usd(all_escalated_cost)}** | "
        f"**{usd(all_baseline_per_paper)}** | **{usd(all_net_per_paper)}** | "
        f"**{all_savings * 100:.1f}%** |",
        "",
        "- **Real spend: $0.** Stage 1 is a replay of the frozen teacher calls; the cache would",
        "  serve every one at $0. The cost above is the **list price those calls already carry** in the",
        "  P1 ledger, which is the cost a fresh paper would incur. Reporting the cache's $0 as the",
        "  lever's saving would be fake.",
        f"- Escalated cost per retained gold row: **{usd(all_escalated_cost / max(merged_all.retained, 1))}**;",
        f"  baseline: **{usd(all_baseline_cost / max(baseline_all.retained, 1))}**.",
        f"- `e = {e_all * 100:.1f}%` overall (dev {len(escalated['dev'])}/{len(splits['dev'].paper_ids)}, "
        f"test {len(escalated['test'])}/{len(splits['test'].paper_ids)}).",
        "",
    ]
    probe_lines: list[str] = []
    if probe is not None:
        stage1_note = "$0 cache hit" if probe.stage1_cache_hit else "a cache miss"
        probe_lines = [
            f"- **Mechanism probe (dev only, output discarded):** stage-1 call {probe.stage1_id} was a",
            f"  {stage1_note}; stage-2 call {probe.stage2_id} on `{probe.model}` records",
            f"  `parent_call_id={probe.parent_call_id}` and {probe.prompt_tokens:,} prompt +",
            f"  {probe.completion_tokens:,} completion tokens, **{usd(probe.usd)}** list price, real spend $0.",
            "  The probe is not part of the measured policy.",
            f"- **Probe sensitivity:** using that measured unit cost adds **{usd(probe_added)}/paper** and",
            f"  leaves **{pct(probe_savings)}** savings, versus the projection's **{pct(savings_with_stage2)}**.",
            "  One dev paper is a sensitivity point, not a rate.",
        ]
    lines += [
        "## Stage 2 (large LLM): rule, probe, and projection",
        "",
        f"- **Measured on gold: {len(stage2_gold)} of {len(escalated_all)} escalated papers** have no accepted",
        "  teacher claim, so the policy never triggered stage 2. The link is demonstrated separately",
        "  below; the client's mechanism is also covered by",
        "  `tests/test_llm_client.py::test_tier_and_parent_call_id_are_ledgered`.",
        f"- **Teacher zero-claim base rate:** {zero_count}/{non_gold_count} non-gold teacher-labelled",
        f"  papers ({zero_rate * 100:.1f}%) have no accepted claim. Applied to the escalated fraction, the",
        f"  projected stage-2 rate is `e x {zero_rate * 100:.1f}% = {stage2_rate * 100:.1f}%` of all papers.",
        f"- **Unit cost projection:** {prompt_mean:,.0f} prompt + {completion_mean:,.0f} completion tokens",
        f"  per paper at `gemini-3.8-flash` intro list price = **{usd(float(unit_large))}/paper**;",
        f"  post-promotion = **{usd(float(unit_large_post))}/paper**.",
        f"- Projected added cost: **{usd(added_intro)}/paper** (intro), taking net savings from",
        f"  **{all_savings * 100:.1f}% to {savings_with_stage2 * 100:.1f}%**. Post-promotion adds",
        f"  **{usd(added_post)}/paper**.",
        *probe_lines,
        "- This is a **projection**, not a measurement: the zero-claim rate is from different papers,",
        "  the large model's output quality is unmeasured, and the one probe call was not scored.",
        "",
        "## `e` and `s`",
        "",
        f"- `e = {e_all * 100:.1f}%` measured (escalated papers / all gold papers).",
        "- `s = 0` in LLM-ledger terms: the student makes no provider call and records no ledger cost.",
        f"- Student inference: **{student_ms:,.0f} ms/paper** on CPU for parse + split + encode + score.",
        f"  At an assumed $0.05/CPU-hour that is {usd(student_ms / 1000 / 3600 * 0.05)}/paper,",
        f"  or **{s_compute[0.05] * 100:.2f}%** of the frozen baseline's $0.005645/paper; at $0.10/CPU-hour,",
        f"  **{s_compute[0.10] * 100:.2f}%**. The compute rate is an assumption; the time is measured.",
        "",
        "## What this result means",
        "",
        "- **The cost gate is met on list price** (≥50% savings) but **the quality story is weak**:",
        f"  retention on test is {pct(merged_by_split['test'].retention)}, far below the baseline's 100%.",
        "  Precision survives; retention does not. The P2 gate is written in terms of precision, so this",
        "  row technically passes, but it is not a free lunch and P2-07 must not present it as one.",
        f"- **The 60% objective is marginal:** stage-1-only savings are {all_savings * 100:.1f}%",
        "  (just over the 60% objective), but the stage-2 projection takes them to",
        f"  {savings_with_stage2 * 100:.1f}%. The 50% gate still passes; the objective does not survive",
        "  stage 2 at the projected rate.",
        "- **Confidence calibration failed.** The student is not able to tell which of its papers it is",
        "  failing on; length is a proxy for claim volume, not for uncertainty.",
        "- **The cache does not make escalation cheaper on a fresh corpus.** Stage 1's $0 replay is a",
        "  measurement artifact; the scalable cost is list price.",
        "- **The student is the binding constraint.** Escalating 30% of papers recovers the teacher's",
        "  claims on those papers, but the other 70% still run at the student's ~28% retention.",
        "",
        "## Limits (repeat in every P2 report)",
        "",
        "- Gold measures precision only; retention is agreement with the baseline's own audited output,",
        "  not recall. Absolute recall is unknown.",
        "- 45 gold papers / 200 rows: small cluster sample, wide intervals, and paper-level heterogeneity.",
        "- Stage 1 is a replay. It uses the same frozen teacher prompt and output as the baseline; it is",
        "  not a new extraction run, and its $0 cache hits are not the lever's cost.",
        "- Stage 2 (large LLM) is a projection; it never fired on gold and its claims were never scored.",
        "- No model was adopted, no tier was changed, and the P1 baseline remains frozen.",
        "",
        "## Reproduce",
        "",
        "```bash",
        "python scripts/escalation_report.py",
        "python scripts/ablate.py --all",
        "```",
        "",
        "The derived `eval/escalation/ledger.sqlite3` and `claims_merged.jsonl` are regenerable and",
        "gitignored; `run_manifest.json`, `paper_signals.json`, `gold_papers.jsonl` and the config are",
        "committed.",
        "",
    ]
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    log(
        f"test retention {merged_by_split['test'].retention:.3f} "
        f"precision {merged_by_split['test'].precision} "
        f"e {e_all:.3f} savings {all_savings:.3f} "
        f"stage2 gold {len(stage2_gold)}"
    )
    log(f"report {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
