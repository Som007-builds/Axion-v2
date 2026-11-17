"""Offline tests for the claim-sentence student pipeline (no encoder, no LLM)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from axion.eval.ablation import GoldClaim, SplitScore
from axion.extract.claims import Claim
from axion.train.student import (
    Example,
    Sentence,
    SentenceStudent,
    StudentError,
    assert_no_gold_papers,
    build_examples,
    read_teacher_claims,
    sentence_rows,
    split_papers,
    top_k_claims,
    unverifiable_rate,
)


def _article(pmcid: str, abstract: str, results: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <journal-meta><journal-title-group><journal-title>Tests</journal-title></journal-title-group></journal-meta>
    <article-meta>
      <article-id pub-id-type="pmcid">{pmcid}</article-id>
      <title-group><article-title>Example title</article-title></title-group>
      <abstract><p>{abstract}</p></abstract>
    </article-meta>
  </front>
  <body><sec><title>Results</title><p>{results}</p></sec></body>
</article>"""


def _paper(tmp_path: Path, pmcid: str) -> Path:
    source = tmp_path / "fulltext"
    source.mkdir(exist_ok=True)
    (source / f"{pmcid}.xml").write_text(
        _article(
            pmcid,
            "First abstract sentence. Second abstract sentence.",
            "Result sentence one. Result sentence two with a 42% effect.",
        ),
        encoding="utf-8",
    )
    return source


def _gold(paper_id: str) -> GoldClaim:
    return GoldClaim(
        claim_id=f"{paper_id}:0",
        paper_id=paper_id,
        split="dev",
        label="CORRECT",
        section="Abstract",
        evidence_span="First abstract sentence.",
    )


def _claim(text: str = "First abstract sentence.", section: str = "Abstract") -> Claim:
    return Claim(claim_text=text, section=section, evidence_span=text)


def test_read_teacher_claims(tmp_path: Path) -> None:
    path = tmp_path / "silver_claims.jsonl"
    rows = [
        {
            "paper_id": "PMC1",
            "claim": _claim().model_dump(mode="json"),
            "run_id": "r",
        }
    ]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    claims = read_teacher_claims(path)
    assert list(claims) == ["PMC1"]
    assert claims["PMC1"][0].evidence_span == "First abstract sentence."


def test_read_teacher_claims_rejects_bad_rows(tmp_path: Path) -> None:
    path = tmp_path / "silver_claims.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(StudentError):
        read_teacher_claims(path)


def test_sentence_rows_filters_and_dedupes(tmp_path: Path) -> None:
    source = _paper(tmp_path, "PMC1")
    from axion.extract.claims import build_baseline_document
    from axion.parse.jats import parse_jats_file

    document = build_baseline_document(parse_jats_file(source / "PMC1.xml", paper_id="PMC1"))
    rows = sentence_rows(document, paper_id="PMC1")
    texts = [row.text for row in rows]
    assert "First abstract sentence." in texts
    assert len(texts) == len(set(texts))
    assert all(len(text) >= 20 for text in texts)


def test_build_examples_labels_the_claim_sentence(tmp_path: Path) -> None:
    source = _paper(tmp_path, "PMC1")
    examples = build_examples(
        ["PMC1"],
        source_dir=source,
        claims_by_paper={"PMC1": [_claim()]},
        gold=[],
    )
    positive = [example for example in examples if example.label == 1]
    assert len(positive) == 1
    assert positive[0].sentence.text == "First abstract sentence."
    assert any(example.label == 0 for example in examples)


def test_build_examples_fails_closed_on_gold_leak(tmp_path: Path) -> None:
    source = _paper(tmp_path, "PMC1")
    with pytest.raises(StudentError, match="gold papers"):
        build_examples(
            ["PMC1"],
            source_dir=source,
            claims_by_paper={"PMC1": [_claim()]},
            gold=[_gold("PMC1")],
        )


def test_assert_no_gold_papers_is_clean_without_overlap() -> None:
    assert_no_gold_papers(["PMC2"], [_gold("PMC1")])
    with pytest.raises(StudentError):
        assert_no_gold_papers(["PMC1"], [_gold("PMC1")])


def test_split_papers_is_paper_level_and_deterministic() -> None:
    ids = [f"PMC{i}" for i in range(20)]
    train, val = split_papers(ids, seed=7, val_fraction=0.2)
    assert set(train).isdisjoint(val)
    assert len(train) + len(val) == len(ids)
    assert split_papers(ids, seed=7, val_fraction=0.2) == (train, val)
    assert split_papers(ids, seed=8, val_fraction=0.2) != (train, val)


def _sentence(paper: str, text: str) -> Sentence:
    return Sentence(paper_id=paper, section="Results", text=text, key=text.casefold())


def test_top_k_claims_is_per_paper() -> None:
    sentences = [
        _sentence("PMC1", "a"),
        _sentence("PMC1", "b"),
        _sentence("PMC1", "c"),
        _sentence("PMC2", "d"),
        _sentence("PMC2", "e"),
    ]
    scores = np.array([0.1, 0.9, 0.5, 0.8, 0.2])
    chosen = top_k_claims(sentences, scores, k=2)
    assert [s.text for s in chosen if s.paper_id == "PMC1"] == ["b", "c"]
    assert [s.text for s in chosen if s.paper_id == "PMC2"] == ["d", "e"]


def test_top_k_claims_validates_length() -> None:
    with pytest.raises(StudentError):
        top_k_claims([_sentence("PMC1", "a")], np.array([0.1, 0.2]))


def test_student_scores_and_round_trips(tmp_path: Path) -> None:
    student = SentenceStudent(encoder_name="fake", coefficients=(1.0, 0.0, -1.0), intercept=0.5)
    scores = student.score(np.array([[2.0, 0.0, 0.0], [0.0, 0.0, 0.0]]))
    assert scores.shape == (2,)
    assert scores[0] > scores[1]
    path = tmp_path / "model.json"
    digest = student.save(path, metadata={"seed": 1})
    loaded, metadata, loaded_digest = SentenceStudent.load(path)
    assert loaded == student
    assert metadata["seed"] == 1
    assert digest == loaded_digest
    with pytest.raises(StudentError):
        loaded.score(np.zeros((1, 4)))


def test_unverifiable_rate() -> None:
    row = SplitScore(
        split="dev",
        gold=10,
        retained=4,
        retention=0.4,
        aligned=4,
        aligned_correct=4,
        precision=1.0,
        precision_ci_low=0.5,
        precision_ci_high=1.0,
        emitted=10,
        claim_aligned=4,
        claim_correct=4,
        core_gold=2,
        core_retained=1,
        core_retention=0.5,
    )
    assert unverifiable_rate(row) == pytest.approx(0.6)


def test_example_dataclass_labels_are_zero_or_one() -> None:
    example = Example(sentence=_sentence("PMC1", "a"), label=1)
    assert example.label == 1
