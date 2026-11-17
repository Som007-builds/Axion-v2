"""P2-05b: flywheel experiment on non-gold papers.

Base student: the 55 P1 baseline papers that are not in the gold audit.
Flywheel pool: the 43 P2-03a teacher-labelled papers that are not in gold
(40 have at least one accepted claim). The pool is split into a candidate set
and a disjoint held-out set. A frozen agreement threshold, calibrated on the
candidate set, selects low-agreement candidate papers; their cached teacher
labels are added to the base training set and the student is retrained.

Only non-gold labels are used for training. The gold audit is used for
evaluation only. No LLM call is made: the teacher labels are cached replays.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression

from axion.eval.ablation import AblationConfig, GoldClaim, SplitScore, load_gold
from axion.eval.flywheel import (
    ESCALATION_FRACTION,
    FLYWHEEL_SEED,
    PoolSplit,
    agreement_threshold,
    escalation_rate,
    select_low_agreement,
    split_pool,
)
from axion.extract.claims import Claim, build_baseline_document
from axion.parse.jats import parse_jats_file
from axion.train.student import (
    Example,
    Sentence,
    SentenceStudent,
    StudentError,
    build_examples,
    read_processed_papers,
    read_teacher_claims,
    score_student,
    sentence_rows,
    top_k_claims,
)

ROOT = Path(__file__).resolve().parents[1]
RUNS = {
    "p1": ROOT / "eval/silver/claims_v1/baseline_flashlite",
    "p2_03a": ROOT / "eval/silver/claims_v1/p2_03a_teacher",
}
GOLD = ROOT / "eval/audit/claims_audit_v1.csv"
SOURCE = ROOT / "data/raw/europepmc/fulltext"
CACHE = ROOT / "data/student"
OUT = ROOT / "eval/flywheel"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
SEED = FLYWHEEL_SEED
K = 8
BASE_MODEL = OUT / "base.model.json"
FLYWHEEL_MODEL = OUT / "flywheel.model.json"
CLAIMS_OUT = OUT / "claims.jsonl"
MANIFEST = OUT / "run_manifest.json"
ABLATION_CONFIG = ROOT / "eval/ablation/configs/flywheel.json"
REPORT = ROOT / "docs/reports/P2-05b-flywheel.md"


def log(message: str) -> None:
    print(message, flush=True)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def texts_digest(texts: list[str]) -> str:
    digest = hashlib.sha256()
    for text in texts:
        digest.update(text.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def embed(
    encoder: SentenceTransformer, texts: list[str], *, tag: str
) -> tuple[np.ndarray, float, bool]:
    digest = texts_digest(texts)
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{tag}-{digest[:16]}.npz"
    if path.exists():
        cached = np.load(path)
        if cached["embeddings"].shape[0] == len(texts):
            log(f"embeddings cache hit: {path.name}")
            seconds = float(cached["seconds"][0]) if "seconds" in cached.files else 0.0
            return cached["embeddings"], seconds, True
    start = time.perf_counter()
    embeddings = encoder.encode(
        texts,
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    seconds = time.perf_counter() - start
    log(f"encoded {len(texts)} sentences in {seconds:.1f}s")
    np.savez_compressed(
        path, embeddings=embeddings, digest=np.array([digest]), seconds=np.array([seconds])
    )
    return embeddings, seconds, False


def fit(examples: list[Example], embeddings: np.ndarray, *, seed: int) -> SentenceStudent:
    labels = np.array([example.label for example in examples], dtype=int)
    if labels.sum() == 0:
        raise StudentError("no positive examples to fit")
    classifier = LogisticRegression(
        C=1.0, class_weight="balanced", max_iter=4000, random_state=seed
    )
    classifier.fit(embeddings, labels)
    return SentenceStudent(
        encoder_name=MODEL_NAME,
        coefficients=tuple(float(value) for value in classifier.coef_[0]),
        intercept=float(classifier.intercept_[0]),
    )


def paper_mrr(
    model: SentenceStudent,
    examples: list[Example],
    embeddings: np.ndarray,
) -> dict[str, float]:
    """Mean reciprocal rank of the paper's teacher-positive sentences.

    The full ranking is used, not just the top-k, so a paper whose teacher
    claims are ranked below the output budget still gets a non-zero value.
    This avoids the zero tie that a binary top-k recall produces.
    """
    scores = model.score(embeddings)
    by_paper: dict[str, list[int]] = defaultdict(list)
    for index, example in enumerate(examples):
        by_paper[example.sentence.paper_id].append(index)
    values: dict[str, float] = {}
    for paper_id, indexes in by_paper.items():
        positives = [i for i in indexes if examples[i].label == 1]
        if not positives:
            continue
        order = sorted(indexes, key=lambda i: (-float(scores[i]), i))
        rank = {index: position + 1 for position, index in enumerate(order)}
        values[paper_id] = sum(1.0 / rank[index] for index in positives) / len(positives)
    return values


def mean(values: list[float]) -> float:
    return sum(values) / max(len(values), 1)


def gold_sentences(gold: list[GoldClaim]) -> list[Sentence]:
    sentences: list[Sentence] = []
    for paper_id in sorted({row.paper_id for row in gold}):
        document = build_baseline_document(
            parse_jats_file(SOURCE / f"{paper_id}.xml", paper_id=paper_id)
        )
        sentences.extend(sentence_rows(document, paper_id=paper_id))
    return sentences


def evaluate_gold(
    model: SentenceStudent,
    sentences: list[Sentence],
    embeddings: np.ndarray,
    gold: list[GoldClaim],
) -> tuple[dict[str, SplitScore], SplitScore, list[Sentence]]:
    claims = top_k_claims(sentences, model.score(embeddings), k=K)
    by_split, overall = score_student(claims, gold, source_dir=SOURCE)
    return by_split, overall, claims


def fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def fmt_ci(row: SplitScore) -> str:
    if row.precision is None or row.precision_ci_low is None or row.precision_ci_high is None:
        return "n/a"
    return (
        f"{row.precision * 100:.1f}% "
        f"[{row.precision_ci_low * 100:.1f}-{row.precision_ci_high * 100:.1f}]"
    )


def unverifiable(row: SplitScore) -> float | None:
    return None if row.emitted == 0 else (row.emitted - row.claim_aligned) / row.emitted


def write_claims(claims: list[Sentence], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for sentence in claims:
            handle.write(
                json.dumps(
                    {
                        "paper_id": sentence.paper_id,
                        "section": sentence.section,
                        "evidence_span": sentence.text,
                        "claim_text": sentence.text,
                        "claim_type": "other",
                        "student": "flywheel-student-v1",
                    },
                    sort_keys=True,
                )
                + "\n"
            )


def render_report(
    *,
    split: PoolSplit,
    selected: tuple[str, ...],
    threshold: float,
    candidate_e: float,
    heldout_e_before: float,
    heldout_e_after: float,
    heldout_agreement_before: list[float],
    heldout_agreement_after: list[float],
    base_split: dict[str, SplitScore],
    flywheel_split: dict[str, SplitScore],
    reference_split: dict[str, SplitScore],
    base_papers: int,
    base_examples: int,
    base_positives: int,
    pool_papers: int,
    pool_examples: int,
    added_sentences: int,
    added_positives: int,
    train_seconds: float,
    inference_ms: float,
    base_sha: str,
    flywheel_sha: str,
    reference_sha: str,
) -> str:
    lines = [
        "# P2-05b - Flywheel with targeted silver labels",
        "",
        "> Generated by `python scripts/flywheel_report.py`. The flywheel adds cached",
        "> teacher labels for **non-gold** papers selected by low student/teacher agreement.",
        "> No LLM call was made and the gold audit was not used for training.",
        "> **Gold measures precision only.** Retention is agreement with the baseline's own",
        "> audited output, **not recall**; absolute recall is unmeasured.",
        "",
        "## Method",
        "",
        f"- **Base student:** {base_papers} P1 non-gold papers, {base_examples:,} sentences,",
        f"  {base_positives} teacher-positive sentences. Frozen MiniLM encoder + logistic head,",
        f"  top-{K} sentences per paper.",
        f"- **Flywheel pool:** {pool_papers} non-gold P2-03a papers with at least one accepted",
        f"  teacher claim ({pool_examples:,} sentences). Cached labels; **no new LLM calls**.",
        f"- **Pool split:** {len(split.candidate)} candidate / {len(split.heldout)} held-out",
        f"  papers, seeded `{SEED}`, disjoint.",
        "- **Agreement signal:** per-paper mean reciprocal rank (MRR) of the",
        "  teacher-positive sentences in the student's full ranking. Low MRR means the",
        "  student ranks the teacher's claims low; it is continuous, unlike a top-k hit rate.",
        f"- **Threshold:** {threshold:.4f}, the {ESCALATION_FRACTION:.0%} low tail of the base",
        "  student's candidate-pool MRR. Ties can raise the realised rate; `e` is reported",
        "  as realised, not assumed.",
        f"- **Selected for new labels:** {len(selected)} candidate papers, {added_sentences:,}",
        f"  sentences and {added_positives} positive sentences added to the base set.",
        f"  Selected IDs: {', '.join(f'`{paper}`' for paper in selected)}.",
        "",
        "## Results",
        "",
        "### Held-out agreement (`e` at the frozen threshold)",
        "",
        "| Model | Mean reciprocal rank | Papers below threshold | `e` |",
        "| :-- | --: | --: | --: |",
        (
            f"| base ({base_papers} papers) | {mean(heldout_agreement_before) * 100:.2f}% | "
            f"{round(heldout_e_before * len(split.heldout))} / {len(split.heldout)} | "
            f"{heldout_e_before * 100:.1f}% |"
        ),
        (
            f"| flywheel ({base_papers + len(selected)} papers) | "
            f"{mean(heldout_agreement_after) * 100:.2f}% | "
            f"{round(heldout_e_after * len(split.heldout))} / {len(split.heldout)} | "
            f"{heldout_e_after * 100:.1f}% |"
        ),
        "",
        f"- Candidate realised `e`: **{candidate_e * 100:.1f}%** "
        f"({round(candidate_e * len(split.candidate))} / {len(split.candidate)}).",
        "",
        "### Frozen gold audit (evaluation only)",
        "",
        "| Model | Train papers | Dev retention | Dev precision |",
        "| :-- | --: | --: | --: |",
        (
            f"| base | {base_papers} | {fmt_pct(base_split['dev'].retention)} | "
            f"{fmt_ci(base_split['dev'])} |"
        ),
        (
            f"| flywheel | {base_papers + len(selected)} | "
            f"{fmt_pct(flywheel_split['dev'].retention)} | {fmt_ci(flywheel_split['dev'])} |"
        ),
        (
            "| frozen `student_v1` (reference, 98 papers) | 98 | "
            f"{fmt_pct(reference_split['dev'].retention)} | {fmt_ci(reference_split['dev'])} |"
        ),
        "",
        "| Model | Test retention | Test precision | Unverifiable |",
        "| :-- | --: | --: | --: |",
        (
            f"| base | {fmt_pct(base_split['test'].retention)} | "
            f"{fmt_ci(base_split['test'])} | {fmt_pct(unverifiable(base_split['test']))} |"
        ),
        (
            f"| flywheel | {fmt_pct(flywheel_split['test'].retention)} | "
            f"{fmt_ci(flywheel_split['test'])} | "
            f"{fmt_pct(unverifiable(flywheel_split['test']))} |"
        ),
        (
            "| frozen `student_v1` (reference, 98 papers) | "
            f"{fmt_pct(reference_split['test'].retention)} | "
            f"{fmt_ci(reference_split['test'])} | "
            f"{fmt_pct(unverifiable(reference_split['test']))} |"
        ),
        "",
        "## Verdict",
        "",
    ]
    dropped = heldout_e_after < heldout_e_before
    retention_held = flywheel_split["test"].retention >= base_split["test"].retention
    if dropped and retention_held:
        lines += [
            "- **Positive on this small experiment:** held-out `e` dropped and test",
            "  retention held. This is a 12-paper held-out pool; repeat before believing",
            "  the size.",
        ]
    else:
        lines += [
            "- **Negative result:** the flywheel did not improve both sides. Targeted labels",
            f"  changed held-out `e` by {(heldout_e_after - heldout_e_before) * 100:+.1f} points",
            "  and test retention by",
            f"  {(flywheel_split['test'].retention - base_split['test'].retention) * 100:+.1f}"
            " points.",
            "  With 12 held-out papers and a small added set this is a noisy test; it does",
            "  not justify a larger label budget.",
        ]
    lines += [
        "",
        "## Cost and provenance",
        "",
        "- **LLM spend: $0.** All teacher labels are cached; no call was made in this experiment.",
        f"- This run wall clock (warm cache): {train_seconds:.1f}s CPU; "
        f"cold gold pipeline ~{inference_ms:.0f} ms/paper.",
        f"- Base artifact SHA-256 `{base_sha[:16]}...`; flywheel `{flywheel_sha[:16]}...`;",
        f"  reference `student_v1` `{reference_sha[:16]}...`.",
        "- New-label source: `p2-03a-teacher-s20261114-n100`, 43 non-gold papers; the",
        f"  selected {len(selected)} are recorded in `eval/flywheel/run_manifest.json`.",
        "",
        "## Limits",
        "",
        "- Gold measures precision only; retention is agreement with the baseline's 200 audited",
        "  claims, not recall. Absolute recall is unknown.",
        "- The base is 55 papers, smaller than the frozen 98-paper student; the flywheel is a",
        "  controlled before/after, not a replacement for the frozen artifact.",
        "- The held-out pool is 12 papers and the added set is small; `e` is coarse.",
        "- The agreement signal is the teacher-label ranking on non-gold papers. It is not a",
        "  confidence measure and does not fix the P2-05 confidence failure.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    started = time.perf_counter()
    gold = load_gold(GOLD)
    gold_ids = {row.paper_id for row in gold}
    claims: dict[str, list[Claim]] = {}
    processed: dict[str, set[str]] = {}
    for name, run_dir in RUNS.items():
        claims.update(read_teacher_claims(run_dir / "silver_claims.jsonl"))
        processed[name] = read_processed_papers(run_dir / "papers_processed.jsonl")
    base_papers = sorted(processed["p1"] - gold_ids)
    pool_candidates = sorted(processed["p2_03a"] - gold_ids)
    pool_papers = sorted(paper for paper in pool_candidates if claims.get(paper))
    if not base_papers or not pool_papers:
        raise SystemExit("empty base or flywheel pool")
    if set(base_papers) & set(pool_papers):
        raise SystemExit("base and pool overlap")
    if (set(base_papers) | set(pool_papers)) & gold_ids:
        raise SystemExit("gold leak into flywheel data")
    log(f"base {len(base_papers)} papers; pool {len(pool_papers)} with claims")

    split = split_pool(pool_papers, seed=SEED)
    if set(split.candidate) & set(split.heldout):
        raise SystemExit("pool split overlaps")

    base_examples = build_examples(
        base_papers, source_dir=SOURCE, claims_by_paper=claims, gold=gold
    )
    pool_examples = build_examples(
        pool_papers, source_dir=SOURCE, claims_by_paper=claims, gold=gold
    )
    base_positives = sum(example.label for example in base_examples)
    if base_positives == 0:
        raise SystemExit("base has no positives")

    encoder = SentenceTransformer(MODEL_NAME)
    log("encoding base")
    base_embeddings, _, _ = embed(
        encoder, [example.sentence.text for example in base_examples], tag="flywheel-base"
    )
    log("encoding pool")
    pool_embeddings, _, _ = embed(
        encoder, [example.sentence.text for example in pool_examples], tag="flywheel-pool"
    )
    log("fitting base")
    base_model = fit(base_examples, base_embeddings, seed=SEED)

    base_agreement = paper_mrr(base_model, pool_examples, pool_embeddings)
    candidate_agreement = {paper: base_agreement[paper] for paper in split.candidate}
    heldout_before = {paper: base_agreement[paper] for paper in split.heldout}
    threshold = agreement_threshold(candidate_agreement, fraction=ESCALATION_FRACTION)
    selected = select_low_agreement(candidate_agreement, threshold)
    candidate_e = len(selected) / len(candidate_agreement)
    heldout_e_before = escalation_rate(heldout_before, threshold)
    log(
        f"threshold {threshold:.4f}; selected {len(selected)}/{len(candidate_agreement)}; "
        f"held-out e before {heldout_e_before:.3f}"
    )

    selected_set = set(selected)
    selected_indexes = [
        index
        for index, example in enumerate(pool_examples)
        if example.sentence.paper_id in selected_set
    ]
    flywheel_examples = base_examples + [pool_examples[index] for index in selected_indexes]
    flywheel_embeddings = np.vstack([base_embeddings, pool_embeddings[selected_indexes]])
    added_positives = sum(pool_examples[index].label for index in selected_indexes)
    log(f"fitting flywheel with {len(flywheel_examples)} examples")
    flywheel_model = fit(flywheel_examples, flywheel_embeddings, seed=SEED)

    flywheel_agreement = paper_mrr(flywheel_model, pool_examples, pool_embeddings)
    heldout_after = {paper: flywheel_agreement[paper] for paper in split.heldout}
    heldout_e_after = escalation_rate(heldout_after, threshold)

    # Gold pipeline: parse/split/encode once, then score each model.
    gold_start = time.perf_counter()
    sentences = gold_sentences(gold)
    log(f"encoding gold ({len(sentences)} sentences)")
    gold_embeddings, gold_seconds, gold_cached = embed(
        encoder, [sentence.text for sentence in sentences], tag="flywheel-gold"
    )
    base_split, base_overall, _ = evaluate_gold(base_model, sentences, gold_embeddings, gold)
    flywheel_split, flywheel_overall, flywheel_claims = evaluate_gold(
        flywheel_model, sentences, gold_embeddings, gold
    )
    inference_ms = (time.perf_counter() - gold_start) * 1000 / max(len(gold_ids), 1)
    cold_inference_ms = (
        inference_ms + gold_seconds * 1000 / max(len(gold_ids), 1) if gold_cached else inference_ms
    )

    reference_path = ROOT / "eval/student/student_v1.model.json"
    reference_model, _, reference_sha = SentenceStudent.load(reference_path)
    reference_split, _, _ = evaluate_gold(reference_model, sentences, gold_embeddings, gold)

    OUT.mkdir(parents=True, exist_ok=True)
    base_sha = base_model.save(
        BASE_MODEL,
        metadata={
            "train_papers": base_papers,
            "seed": SEED,
            "examples": len(base_examples),
            "positives": base_positives,
            "source_runs": [str(RUNS["p1"].relative_to(ROOT))],
        },
    )
    flywheel_sha = flywheel_model.save(
        FLYWHEEL_MODEL,
        metadata={
            "train_papers": base_papers + list(selected),
            "seed": SEED,
            "examples": len(flywheel_examples),
            "positives": base_positives + added_positives,
            "source_runs": [str(path.relative_to(ROOT)) for path in RUNS.values()],
            "selected": list(selected),
            "threshold": threshold,
        },
    )
    write_claims(flywheel_claims, CLAIMS_OUT)

    config = AblationConfig(
        name="flywheel-student",
        description=(
            "P2-05b flywheel: base 55 P1 + low-agreement P2-03a papers; "
            "frozen MiniLM + logistic head, top-8; no LLM calls"
        ),
        kind="student_run",
        claims_path=str(CLAIMS_OUT.relative_to(ROOT)).replace("\\", "/"),
        matching="sentence",
        paper_count=len(gold_ids),
        ledgers=(),
        inference_ms_per_paper=None,
        notes=(
            "Compute-only row; the flywheel adds cached teacher labels for non-gold papers; "
            "cold CPU timing is recorded in eval/flywheel/run_manifest.json."
        ),
    )
    ABLATION_CONFIG.write_text(
        json.dumps(config.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )

    train_seconds = time.perf_counter() - started
    manifest = {
        "experiment": "p2-05b-flywheel",
        "seed": SEED,
        "k": K,
        "escalation_fraction": ESCALATION_FRACTION,
        "base_train_papers": base_papers,
        "pool_papers": pool_papers,
        "candidate": list(split.candidate),
        "heldout": list(split.heldout),
        "selected": list(selected),
        "selected_count": len(selected),
        "candidate_e": candidate_e,
        "heldout_e_before": heldout_e_before,
        "heldout_e_after": heldout_e_after,
        "threshold": threshold,
        "heldout_agreement_before": heldout_before,
        "heldout_agreement_after": heldout_after,
        "base_examples": len(base_examples),
        "base_positives": base_positives,
        "flywheel_examples": len(flywheel_examples),
        "added_sentences": len(selected_indexes),
        "added_positives": added_positives,
        "gold": {
            "base": {name: row.model_dump(mode="json") for name, row in base_split.items()},
            "flywheel": {name: row.model_dump(mode="json") for name, row in flywheel_split.items()},
            "student_v1": {
                name: row.model_dump(mode="json") for name, row in reference_split.items()
            },
            "base_overall": base_overall.model_dump(mode="json"),
            "flywheel_overall": flywheel_overall.model_dump(mode="json"),
        },
        "artifacts": {
            "base": {"path": str(BASE_MODEL.relative_to(ROOT)), "sha256": base_sha},
            "flywheel": {"path": str(FLYWHEEL_MODEL.relative_to(ROOT)), "sha256": flywheel_sha},
            "student_v1": {"path": str(reference_path.relative_to(ROOT)), "sha256": reference_sha},
        },
        "source_runs": {name: str(path.relative_to(ROOT)) for name, path in RUNS.items()},
        "gold_sha256": sha256_file(GOLD),
        "train_seconds": train_seconds,
        "inference_ms_per_paper": cold_inference_ms,
        "gold_encode_seconds": gold_seconds,
        "gold_cached": gold_cached,
        "real_spend_usd": 0.0,
        "created_at": datetime.now(UTC).isoformat(),
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n")

    report = render_report(
        split=split,
        selected=selected,
        threshold=threshold,
        candidate_e=candidate_e,
        heldout_e_before=heldout_e_before,
        heldout_e_after=heldout_e_after,
        heldout_agreement_before=list(heldout_before.values()),
        heldout_agreement_after=list(heldout_after.values()),
        base_split=base_split,
        flywheel_split=flywheel_split,
        reference_split=reference_split,
        base_papers=len(base_papers),
        base_examples=len(base_examples),
        base_positives=base_positives,
        pool_papers=len(pool_papers),
        pool_examples=len(pool_examples),
        added_sentences=len(selected_indexes),
        added_positives=added_positives,
        train_seconds=train_seconds,
        inference_ms=cold_inference_ms,
        base_sha=base_sha,
        flywheel_sha=flywheel_sha,
        reference_sha=reference_sha,
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8", newline="\n")
    log(f"wrote {REPORT.relative_to(ROOT)}")
    log(
        f"held-out e {heldout_e_before:.3f} -> {heldout_e_after:.3f}; "
        f"test retention {base_split['test'].retention:.3f} -> "
        f"{flywheel_split['test'].retention:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
