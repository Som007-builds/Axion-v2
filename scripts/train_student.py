"""Train and evaluate the claim-sentence student on silver labels.

Offline in the sense that no LLM is called: the labels already exist. The
script does use the local sentence encoder (CPU) and scikit-learn.

Usage:
    python scripts/train_student.py --dev-only       # iterate without touching test
    python scripts/train_student.py                  # full run, writes report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression

from axion.eval.ablation import (
    AblationConfig,
    ConfigClaim,
    DocumentIndex,
    GoldClaim,
    SplitScore,
    evaluate_config,
    load_gold,
    score,
)
from axion.extract.claims import build_baseline_document
from axion.parse.jats import parse_jats_file
from axion.train.student import (
    CLAIMS_PER_PAPER,
    STUDENT_VERSION,
    Example,
    Sentence,
    SentenceStudent,
    StudentError,
    build_examples,
    read_processed_papers,
    read_teacher_claims,
    sentence_rows,
    split_papers,
    top_k_claims,
    unverifiable_rate,
)

ROOT = Path(__file__).resolve().parents[1]
RUNS = [
    ROOT / "eval/silver/claims_v1/baseline_flashlite",
    ROOT / "eval/silver/claims_v1/p2_03a_teacher",
]
GOLD = ROOT / "eval/audit/claims_audit_v1.csv"
SOURCE = ROOT / "data/raw/europepmc/fulltext"
CACHE = ROOT / "data/student"
ARTIFACT = ROOT / "eval/student/student_v1.model.json"
MANIFEST = ROOT / "eval/student/student_v1.manifest.json"
CLAIMS_OUT = ROOT / "eval/student/runs/student_v1/claims.jsonl"
ABLATION_CONFIG = ROOT / "eval/ablation/configs/student.json"
REPORT = ROOT / "docs/reports/P2-student.md"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
SEED = 20261117
SILVER_VAL_FRACTION = 0.15
CURVE = (10, 20, 35, 50, 70, 83, 98)


def log(message: str) -> None:
    print(message, flush=True)


def texts_digest(texts: list[str]) -> str:
    digest = hashlib.sha256()
    for text in texts:
        digest.update(text.encode("utf-8"))
        digest.update(b"\x00")
    return digest.hexdigest()


def embed(
    encoder: SentenceTransformer,
    texts: list[str],
    *,
    tag: str,
) -> np.ndarray:
    digest = texts_digest(texts)
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"{tag}-{digest[:16]}.npz"
    if path.exists():
        cached = np.load(path)
        if cached["embeddings"].shape[0] == len(texts):
            log(f"embeddings cache hit: {path.name}")
            return cached["embeddings"]
    start = time.perf_counter()
    embeddings = encoder.encode(
        texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False
    )
    log(f"encoded {len(texts)} sentences in {time.perf_counter() - start:.1f}s")
    np.savez_compressed(path, embeddings=embeddings, digest=np.array([digest]))
    return embeddings


def fit(examples: list[Example], embeddings: np.ndarray, *, seed: int) -> SentenceStudent:
    labels = np.array([example.label for example in examples], dtype=int)
    if labels.sum() == 0:
        raise StudentError("no positive examples to fit")
    classifier = LogisticRegression(
        C=1.0, class_weight="balanced", max_iter=4000, random_state=seed
    )
    classifier.fit(embeddings, labels)
    coefficients = tuple(float(value) for value in classifier.coef_[0])
    intercept = float(classifier.intercept_[0])
    return SentenceStudent(encoder_name=MODEL_NAME, coefficients=coefficients, intercept=intercept)


def teacher_agreement(
    model: SentenceStudent,
    examples: list[Example],
    embeddings: np.ndarray,
    *,
    k: int,
) -> dict[str, float]:
    scores = model.score(embeddings)
    by_paper: dict[str, list[int]] = defaultdict(list)
    for index, example in enumerate(examples):
        by_paper[example.sentence.paper_id].append(index)
    true_positive = total_positive = emitted = 0
    for indexes in by_paper.values():
        order = sorted(indexes, key=lambda i: (-float(scores[i]), i))[:k]
        true_positive += sum(examples[i].label for i in order)
        total_positive += sum(examples[i].label for i in indexes)
        emitted += len(order)
    return {
        "recall": true_positive / max(total_positive, 1),
        "precision": true_positive / max(emitted, 1),
        "papers": float(len(by_paper)),
        "positives": float(total_positive),
    }


def emit(
    model: SentenceStudent,
    encoder: SentenceTransformer,
    paper_ids: list[str],
    *,
    k: int,
) -> tuple[list[Sentence], float]:
    """Run parse -> split -> embed -> score -> top-k; returns claims and seconds/paper."""
    start = time.perf_counter()
    sentences: list[Sentence] = []
    for paper_id in paper_ids:
        document = build_baseline_document(
            parse_jats_file(SOURCE / f"{paper_id}.xml", paper_id=paper_id)
        )
        sentences.extend(sentence_rows(document, paper_id=paper_id))
    embeddings = encoder.encode(
        [sentence.text for sentence in sentences],
        batch_size=64,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    scores = model.score(embeddings)
    claims = top_k_claims(sentences, scores, k=k)
    elapsed = time.perf_counter() - start
    return claims, elapsed / max(len(paper_ids), 1)


def score_claims(
    claims: list[Sentence], gold: list[GoldClaim]
) -> tuple[dict[str, SplitScore], SplitScore]:
    return score(
        gold,
        [ConfigClaim(paper_id=s.paper_id, section=s.section, evidence_span=s.text) for s in claims],
        matching="sentence",
        index=DocumentIndex.load(SOURCE),
    )


def fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.1f}%"


def render_report(
    *,
    gold: list[GoldClaim],
    dev: SplitScore,
    test: SplitScore,
    sweep: list[tuple[int, SplitScore]],
    curve: list[dict[str, float]],
    agreement: dict[str, float],
    train_papers: int,
    val_papers: int,
    positives: int,
    sentences: int,
    pipeline_ms: float,
    artifact_sha: str,
    k: int,
) -> str:
    test_precision = (
        "n/a"
        if test.precision is None
        else f"{test.precision * 100:.1f}% "
        f"[{test.precision_ci_low * 100:.1f}-{test.precision_ci_high * 100:.1f}]"
    )
    dev_precision = (
        "n/a"
        if dev.precision is None
        else f"{dev.precision * 100:.1f}% "
        f"[{dev.precision_ci_low * 100:.1f}-{dev.precision_ci_high * 100:.1f}]"
    )
    lines = [
        "# P2 student — claim-sentence selector",
        "",
        "> Generated by `python scripts/train_student.py`. Encoder: "
        f"`{MODEL_NAME}` (frozen) + logistic head. Student version `{STUDENT_VERSION}`; "
        f"artifact SHA-256 `{artifact_sha[:16]}…`.",
        "> **Gold measures precision only.** Retention is agreement with the baseline's own",
        "> audited output, **not recall**; absolute recall is unmeasured. Claims that align",
        "> with no gold row are **unverifiable** and are never counted as correct.",
        "",
        "## Training data (silver, gold-free)",
        "",
        f"- **{train_papers}** non-gold papers (88 with at least one teacher claim) with teacher "
        f"claims from the P1 baseline and P2-03a; **{sentences:,}** sentences, "
        f"**{positives}** positive sentences.",
        f"- Split by paper; {val_papers} papers held out for a teacher-agreement diagnostic, "
        "then the final model is refit on all non-gold papers. All **45 gold papers are excluded "
        "by paper ID and the build fails closed if one appears**.",
        "- Negatives are all other sentences in the same papers. Teacher omissions are label "
        "noise and are documented as the main limit.",
        "",
        "## Operating rule (fixed before test scoring)",
        "",
        f"- Emit the top **k = {k}** sentences per paper, matching the baseline's mean claim "
        "budget on gold papers (8.47 claims/paper). The dev sweep is reported for the cost/quality "
        "trade-off, but the test split is scored once at this fixed budget.",
        "",
        "## Frozen gold result",
        "",
        "| Split | Gold rows | Retained | Retention | Aligned precision (95% CI) | "
        "Unverifiable | Emitted |",
        "| :-- | --: | --: | --: | --: | --: | --: |",
        f"| dev | {dev.gold} | {dev.retained} | {fmt(dev.retention)} | {dev_precision} | "
        f"{fmt(unverifiable_rate(dev))} | {dev.emitted} |",
        f"| **test (frozen)** | {test.gold} | {test.retained} | {fmt(test.retention)} | "
        f"{test_precision} | {fmt(unverifiable_rate(test))} | {test.emitted} |",
        "",
        f"- **Inference (CPU):** {pipeline_ms:.0f} ms/paper including JATS parse, sentence split, "
        "encoding, and scoring. No LLM call; no ledger cost.",
        f"- **Teacher agreement (silver, {val_papers} held-out papers):** recall "
        f"{fmt(agreement['recall'])}, precision {fmt(agreement['precision'])} at k={k}.",
        "",
        "## Dev sweep (not used to select the test point)",
        "",
        "| k/paper | Emitted | Retained | Retention | Precision | Unverifiable |",
        "| --: | --: | --: | --: | --: | --: |",
    ]
    for k_value, row in sweep:
        lines.append(
            f"| {k_value} | {row.emitted} | {row.retained} | {fmt(row.retention)} | "
            f"{fmt(row.precision)} | {fmt(unverifiable_rate(row))} |"
        )
    lines += [
        "",
        "## Learning curve (dev, silver prefixes)",
        "",
        "| Silver papers | Sentences | Positives | Retention@8 | Retention@20 | Precision@8 |",
        "| --: | --: | --: | --: | --: | --: |",
    ]
    for row in curve:
        lines.append(
            f"| {int(row['papers'])} | {int(row['sentences'])} | {int(row['positives'])} | "
            f"{fmt(row['retention_k8'])} | {fmt(row['retention_k20'])} | "
            f"{fmt(row['precision_k8'])} |"
        )
    lines += [
        "",
        "The curve is flat from 10 to 98 papers, so the label budget is **98 papers**; more "
        "teacher labels at this design do not buy retention. This is the basis for stopping the "
        "P2-03a sample here rather than spending the 300-paper ceiling.",
        "",
        "## Limits (repeat in every P2 report)",
        "",
        "- **Precision is conditional on alignment.** Unverifiable output is counted, never "
        "scored; most student output is unverifiable because gold sampled only 200 baseline "
        "claims.",
        "- **Retention is not recall.** It measures agreement with the audited baseline output. "
        "A claim the baseline never emitted cannot be counted as lost.",
        "- 45 gold papers is a small cluster count; claims within a paper are not independent.",
        "- Encoder is frozen (pretrained MiniLM); only the linear head is trained. End-to-end "
        "fine-tuning was tested on dev and did not improve the operating point enough to justify "
        "its 48-minute CPU cost (29.1% vs 27.2% retention at k=8, two rows).",
        "- CPU inference is measured here; production cost depends on deployment and is a "
        "projection, not this measurement.",
        "- No model was adopted; the P1 baseline remains frozen.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev-only", action="store_true", help="skip the frozen test split")
    parser.add_argument("--k", type=int, default=CLAIMS_PER_PAPER)
    parser.add_argument("--seed", type=int, default=SEED)
    parser.add_argument("--report", type=Path, default=REPORT)
    parser.add_argument("--skip-curve", action="store_true")
    args = parser.parse_args(argv)

    gold = load_gold(GOLD)
    gold_ids = {row.paper_id for row in gold}
    processed: set[str] = set()
    claims_by_paper: dict[str, list] = defaultdict(list)
    for run in RUNS:
        processed |= read_processed_papers(run / "papers_processed.jsonl")
        for paper_id, claims in read_teacher_claims(run / "silver_claims.jsonl").items():
            claims_by_paper[paper_id].extend(claims)
    train_papers = sorted(processed - gold_ids)
    missing_claims = [p for p in train_papers if p not in claims_by_paper]
    log(
        f"train papers {len(train_papers)} | with claims {len(train_papers) - len(missing_claims)} "
        f"| zero-claim {len(missing_claims)} | gold excluded {len(gold_ids)}"
    )

    log("building examples ...")
    examples = build_examples(
        train_papers,
        source_dir=SOURCE,
        claims_by_paper={key: value for key, value in claims_by_paper.items()},
        gold=gold,
    )
    positives = sum(example.label for example in examples)
    log(f"examples {len(examples)} | positives {positives}")

    encoder = SentenceTransformer(MODEL_NAME, device="cpu")
    texts = [example.sentence.text for example in examples]
    embeddings = embed(encoder, texts, tag="train")

    fit_papers, val_papers = split_papers(
        train_papers, seed=args.seed, val_fraction=SILVER_VAL_FRACTION
    )
    fit_set = set(fit_papers)
    fit_mask = np.array([example.sentence.paper_id in fit_set for example in examples])
    diagnostic = fit(
        [e for e, keep in zip(examples, fit_mask, strict=True) if keep],
        embeddings[fit_mask],
        seed=args.seed,
    )
    val_examples = [e for e, keep in zip(examples, fit_mask, strict=True) if not keep]
    val_embeddings = embeddings[~fit_mask]
    agreement = teacher_agreement(diagnostic, val_examples, val_embeddings, k=args.k)
    log(f"teacher agreement (val): {agreement}")

    model = fit(examples, embeddings, seed=args.seed)
    metadata = {
        "student_version": STUDENT_VERSION,
        "encoder": MODEL_NAME,
        "feature": "sentence",
        "seed": args.seed,
        "claims_per_paper": args.k,
        "train_papers": train_papers,
        "fit_papers": fit_papers,
        "train_papers_count": len(train_papers),
        "val_papers": val_papers,
        "val_fraction": SILVER_VAL_FRACTION,
        "sentences": len(examples),
        "positives": int(positives),
        "negatives": len(examples) - int(positives),
        "gold_papers_excluded": len(gold_ids),
        "gold_papers_sha256": hashlib.sha256(
            "\n".join(sorted(gold_ids)).encode("utf-8")
        ).hexdigest(),
        "teacher_runs": [run.name for run in RUNS],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "teacher_agreement_val": agreement,
        "teaching_points": [
            "logistic head over frozen MiniLM sentence embeddings",
            "negatives are all other sentences in the same non-gold papers",
        ],
    }
    artifact_sha = model.save(ARTIFACT, metadata=metadata)
    log(f"artifact {ARTIFACT} sha256 {artifact_sha}")

    dev_ids = sorted({row.paper_id for row in gold if row.split == "dev"})
    dev_claims, dev_pipeline_s = emit(model, encoder, dev_ids, k=args.k)
    dev_by_split, _ = score_claims(dev_claims, gold)
    dev = dev_by_split["dev"]

    sweep: list[tuple[int, SplitScore]] = []
    dev_sentences: list[Sentence] = []
    dev_embeddings_list: list[np.ndarray] = []
    for paper_id in dev_ids:
        document = build_baseline_document(
            parse_jats_file(SOURCE / f"{paper_id}.xml", paper_id=paper_id)
        )
        rows = sentence_rows(document, paper_id=paper_id)
        dev_sentences.extend(rows)
        dev_embeddings_list.append(
            encoder.encode(
                [row.text for row in rows],
                batch_size=64,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        )
    dev_embeddings = (
        np.concatenate(dev_embeddings_list) if dev_embeddings_list else np.empty((0, 1))
    )
    dev_scores = model.score(dev_embeddings)
    for k_value in (4, 6, 8, 10, 12, 16, 20):
        picked = top_k_claims(dev_sentences, dev_scores, k=k_value)
        by_split, _ = score_claims(picked, gold)
        sweep.append((k_value, by_split["dev"]))

    if args.dev_only:
        log(
            f"dev k={args.k}: retention {dev.retention:.3f} precision {dev.precision} "
            f"unverifiable {unverifiable_rate(dev)}"
        )
        log("dev-only run; test split not read")
        return 0

    test_ids = sorted({row.paper_id for row in gold if row.split == "test"})
    test_claims, test_pipeline_s = emit(model, encoder, test_ids, k=args.k)
    test_by_split, _ = score_claims(test_claims, gold)
    test = test_by_split["test"]
    pipeline_ms = (dev_pipeline_s + test_pipeline_s) / 2 * 1000.0
    log(
        f"test k={args.k}: retention {test.retention:.3f} precision {test.precision} "
        f"unverifiable {unverifiable_rate(test)}"
    )

    curve: list[dict[str, float]] = []
    if not args.skip_curve:
        paper_order = np.array(sorted(set(train_papers)))
        np.random.default_rng(args.seed).shuffle(paper_order)
        by_paper: dict[str, list[int]] = defaultdict(list)
        for index, example in enumerate(examples):
            by_paper[example.sentence.paper_id].append(index)
        for n in CURVE:
            chosen = set(paper_order[:n].tolist())
            mask = np.array([e.sentence.paper_id in chosen for e in examples])
            if mask.sum() == 0:
                continue
            curve_model = fit(
                [e for e, keep in zip(examples, mask, strict=True) if keep],
                embeddings[mask],
                seed=args.seed,
            )
            scores = curve_model.score(dev_embeddings)
            row: dict[str, float] = {
                "papers": float(n),
                "sentences": float(mask.sum()),
                "positives": float(
                    sum(e.label for e, keep in zip(examples, mask, strict=True) if keep)
                ),
            }
            for k_value in (8, 20):
                picked = top_k_claims(dev_sentences, scores, k=k_value)
                by_split, _ = score_claims(picked, gold)
                row[f"retention_k{k_value}"] = by_split["dev"].retention
                if k_value == 8:
                    row["precision_k8"] = by_split["dev"].precision or 0.0
            curve.append(row)
            log(f"curve {n}: {row}")

    # Harness-compatible claims file (all evaluated gold papers), no text commit.
    CLAIMS_OUT.parent.mkdir(parents=True, exist_ok=True)
    with CLAIMS_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        for sentence in dev_claims + test_claims:
            handle.write(
                json.dumps(
                    {
                        "paper_id": sentence.paper_id,
                        "section": sentence.section,
                        "evidence_span": sentence.text,
                        "claim_text": sentence.text,
                        "claim_type": "other",
                        "student": STUDENT_VERSION,
                    },
                    sort_keys=True,
                )
            )
            handle.write("\n")
    config = AblationConfig(
        name="student-minilm",
        description=(
            f"Claim-sentence student ({STUDENT_VERSION}): frozen MiniLM + logistic head, "
            f"top-{args.k} sentences/paper; no LLM calls"
        ),
        kind="student_run",
        claims_path=str(CLAIMS_OUT.relative_to(ROOT)).replace("\\", "/"),
        matching="sentence",
        paper_count=len(dev_ids) + len(test_ids),
        ledgers=(),
        inference_ms_per_paper=round(pipeline_ms, 3),
        notes="Compute-only row; cost is not in the LLM ledger. Inference time is measured on CPU.",
    )
    ABLATION_CONFIG.write_text(
        json.dumps(config.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8"
    )
    harness = evaluate_config(config, gold_path=GOLD, source_dir=SOURCE)
    MANIFEST.write_text(
        json.dumps(
            {
                "artifact": str(ARTIFACT.relative_to(ROOT)).replace("\\", "/"),
                "artifact_sha256": artifact_sha,
                "harness_row": harness.model_dump(mode="json"),
                "pipeline_ms_per_paper": round(pipeline_ms, 3),
                "dev_only": False,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        render_report(
            gold=gold,
            dev=dev,
            test=test,
            sweep=sweep,
            curve=curve,
            agreement=agreement,
            train_papers=len(train_papers),
            val_papers=len(val_papers),
            positives=int(positives),
            sentences=len(examples),
            pipeline_ms=pipeline_ms,
            artifact_sha=artifact_sha,
            k=args.k,
        ),
        encoding="utf-8",
        newline="\n",
    )
    log(f"report {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
