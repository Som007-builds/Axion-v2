"""Claim-sentence student: silver data assembly, scoring, and gold evaluation.

The student is a sentence-level selector. A sentence encoder maps each sentence
to a vector; a linear head trained on **silver** labels scores it; the top-``k``
sentences per paper become the student's claims. Silver labels come from the
frozen P1/P2-03a teacher runs and **never** from gold papers.

Gold measures precision only. The student is scored with the same harness as
every other P2 configuration: aligned precision, retention of the audited
baseline claims, unverifiable rate, and cost (here: no LLM cost; inference time
is reported separately). Absolute recall is unmeasured.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from axion.eval.ablation import (
    DocumentIndex,
    GoldClaim,
    SplitScore,
    score,
    sentence_key,
)
from axion.extract.claims import Claim, normalize_for_match
from axion.parse.jats import JatsParseError, parse_jats_file, split_sentences

STUDENT_VERSION = "student-v1-minilm-lr"
MIN_SENTENCE_CHARS = 20
# Fixed before test scoring: the baseline emits 8.47 claims/paper on the gold
# papers, so the student gets the same budget. The learning curve is flat, and
# choosing a larger k to chase retention would silently multiply downstream
# volume; the sweep is reported instead.
CLAIMS_PER_PAPER = 8


class StudentError(Exception):
    """Raised when student data or artifacts are inconsistent."""


@dataclass(frozen=True)
class Sentence:
    paper_id: str
    section: str
    text: str
    key: str


@dataclass(frozen=True)
class Example:
    sentence: Sentence
    label: int


def sentence_rows(document: object, *, paper_id: str) -> list[Sentence]:
    """Split every baseline section into deduplicated, non-trivial sentences."""
    rows: list[Sentence] = []
    seen: set[str] = set()
    sections = getattr(document, "sections", ())
    for section in sections:
        for text in split_sentences(section.text):
            text = text.strip()
            key = normalize_for_match(text).casefold().strip()
            if len(text) < MIN_SENTENCE_CHARS or not key or key in seen:
                continue
            seen.add(key)
            rows.append(Sentence(paper_id=paper_id, section=section.label, text=text, key=key))
    return rows


def read_teacher_claims(path: Path) -> dict[str, list[Claim]]:
    """Read a teacher silver-claims JSONL, keyed by paper."""
    if not path.exists():
        raise StudentError(f"missing teacher claims: {path}")
    claims: dict[str, list[Claim]] = defaultdict(list)
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise StudentError(f"{path}:{line_number}: invalid JSON") from exc
        if not isinstance(raw, dict) or not isinstance(raw.get("paper_id"), str):
            raise StudentError(f"{path}:{line_number}: missing paper_id")
        claim = raw.get("claim")
        if not isinstance(claim, dict):
            raise StudentError(f"{path}:{line_number}: missing claim object")
        claims[str(raw["paper_id"])].append(Claim.model_validate(claim))
    return dict(claims)


def read_processed_papers(path: Path) -> set[str]:
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


def assert_no_gold_papers(train_papers: Iterable[str], gold: Sequence[GoldClaim]) -> None:
    """Fail closed if a gold paper leaks into training."""
    gold_ids = {row.paper_id for row in gold}
    overlap = sorted(set(train_papers) & gold_ids)
    if overlap:
        raise StudentError(f"gold papers in the training set: {', '.join(overlap[:5])}")


def build_examples(
    paper_ids: Sequence[str],
    *,
    source_dir: Path,
    claims_by_paper: dict[str, list[Claim]],
    gold: Sequence[GoldClaim],
) -> list[Example]:
    """Label every sentence by whether it contains a teacher claim."""
    assert_no_gold_papers(paper_ids, gold)
    examples: list[Example] = []
    for paper_id in paper_ids:
        path = source_dir / f"{paper_id}.xml"
        if not path.exists():
            raise StudentError(f"missing full text for {paper_id}")
        try:
            parsed = parse_jats_file(path, paper_id=paper_id)
        except JatsParseError as exc:
            raise StudentError(f"cannot parse {paper_id}") from exc
        from axion.extract.claims import build_baseline_document

        document = build_baseline_document(parsed)
        positive = {
            key
            for claim in claims_by_paper.get(paper_id, [])
            if (
                key := sentence_key(
                    document, section_label=claim.section, evidence_span=claim.evidence_span
                )
            )
        }
        for sentence in sentence_rows(document, paper_id=paper_id):
            examples.append(Example(sentence=sentence, label=1 if sentence.key in positive else 0))
    if not examples:
        raise StudentError("no sentence examples")
    if not any(example.label == 1 for example in examples):
        raise StudentError("no positive sentence examples")
    return examples


def split_papers(
    paper_ids: Sequence[str], *, seed: int, val_fraction: float = 0.15
) -> tuple[list[str], list[str]]:
    """Paper-level split; no paper can appear on both sides."""
    if not 0.0 < val_fraction < 1.0:
        raise StudentError("val_fraction must be between 0 and 1")
    ids = np.array(sorted(set(paper_ids)))
    np.random.default_rng(seed).shuffle(ids)
    n_val = max(1, round(val_fraction * len(ids)))
    val = ids[:n_val].tolist()
    train = ids[n_val:].tolist()
    if not train or not val:
        raise StudentError("split produced an empty side")
    return train, val


@dataclass(frozen=True)
class SentenceStudent:
    """A linear head over frozen sentence embeddings."""

    encoder_name: str
    coefficients: tuple[float, ...]
    intercept: float
    version: str = STUDENT_VERSION
    feature: str = "sentence"

    def score(self, embeddings: np.ndarray) -> np.ndarray:
        if embeddings.ndim != 2 or embeddings.shape[1] != len(self.coefficients):
            raise StudentError(
                f"embeddings have shape {embeddings.shape}, expected *x{len(self.coefficients)}"
            )
        logits = embeddings @ np.asarray(self.coefficients) + self.intercept
        return np.asarray(1.0 / (1.0 + np.exp(-logits)))

    def to_json(self) -> dict[str, object]:
        return {
            "version": self.version,
            "encoder": self.encoder_name,
            "feature": self.feature,
            "coefficients": list(self.coefficients),
            "intercept": self.intercept,
        }

    def save(self, path: Path, *, metadata: dict[str, object]) -> str:
        payload = {**self.to_json(), "metadata": metadata}
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @classmethod
    def load(cls, path: Path) -> tuple[SentenceStudent, dict[str, object], str]:
        text = path.read_text(encoding="utf-8")
        payload = json.loads(text)
        model = cls(
            encoder_name=str(payload["encoder"]),
            coefficients=tuple(float(value) for value in payload["coefficients"]),
            intercept=float(payload["intercept"]),
            version=str(payload.get("version", STUDENT_VERSION)),
            feature=str(payload.get("feature", "sentence")),
        )
        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise StudentError("model metadata is not an object")
        return model, metadata, hashlib.sha256(text.encode("utf-8")).hexdigest()


def top_k_claims(
    sentences: Sequence[Sentence], scores: np.ndarray, *, k: int = CLAIMS_PER_PAPER
) -> list[Sentence]:
    """Take the k highest-scoring sentences **per paper**."""
    if len(sentences) != len(scores):
        raise StudentError("sentence/score length mismatch")
    if k < 0:
        raise StudentError("k must be non-negative")
    by_paper: dict[str, list[int]] = defaultdict(list)
    for index, sentence in enumerate(sentences):
        by_paper[sentence.paper_id].append(index)
    chosen: list[Sentence] = []
    for indexes in by_paper.values():
        order = sorted(indexes, key=lambda index: (-float(scores[index]), index))[:k]
        chosen.extend(sentences[index] for index in order)
    return chosen


def score_student(
    emitted: Sequence[Sentence],
    gold: Sequence[GoldClaim],
    *,
    source_dir: Path,
) -> tuple[dict[str, SplitScore], SplitScore]:
    from axion.eval.ablation import ConfigClaim

    claims = [
        ConfigClaim(paper_id=s.paper_id, section=s.section, evidence_span=s.text) for s in emitted
    ]
    return score(gold, claims, matching="sentence", index=DocumentIndex.load(source_dir))


def unverifiable_rate(row: SplitScore) -> float | None:
    if row.emitted == 0:
        return None
    return (row.emitted - row.claim_aligned) / row.emitted


__all__ = [
    "CLAIMS_PER_PAPER",
    "MIN_SENTENCE_CHARS",
    "STUDENT_VERSION",
    "Example",
    "Sentence",
    "SentenceStudent",
    "StudentError",
    "assert_no_gold_papers",
    "build_examples",
    "read_processed_papers",
    "read_teacher_claims",
    "score_student",
    "sentence_rows",
    "split_papers",
    "top_k_claims",
    "unverifiable_rate",
]
