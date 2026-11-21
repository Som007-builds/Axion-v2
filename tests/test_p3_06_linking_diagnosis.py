"""Tests for the P3-06 linking diagnosis (no network, no LLM, no full-text cache)."""

from __future__ import annotations

from pathlib import Path

import pytest
import scripts.p3_06_linking_diagnosis as dx


def _row(
    row_id: str,
    *,
    label: str = "MENTIONS",
    context: str = "We used the assay from the earlier study [1].",
    claim: str = "",
    abstract: str = "",
    section: str = "results",
) -> dict[str, str]:
    return {
        "row_id": row_id,
        "wave": "wave1",
        "split": "dev",
        "text_bearing": "true" if (claim or abstract) else "false",
        "weight": "1.0",
        "frame": "text_bearing" if (claim or abstract) else "stub",
        "section": section,
        "section_bucket": section,
        "paragraph_text": "",
        "label": label,
        "context_text": context,
        "source_title": "Source",
        "source_claim_text": claim,
        "source_abstract": abstract,
        "citer_title": "Citer",
    }


def test_content_tokens_drop_stopwords_and_short_words() -> None:
    tokens = dx.content_tokens("The assay was used in the study of BCG vaccine")

    assert "assay" in tokens
    assert "study" in tokens
    assert "the" not in tokens
    assert "was" not in tokens
    assert "of" not in tokens


def test_numeric_tokens_keep_percentages_and_decimals() -> None:
    assert dx.numeric_tokens("mortality fell 12.5% across 94 patients") == {"12.5%", "94"}


def test_link_decision_is_unavailable_without_source_text() -> None:
    decision = dx.link_decision("we used their assay", [])

    assert decision["status"] == "unavailable"
    assert decision["best"] == 0.0


def test_link_decision_accepts_a_clear_single_winner() -> None:
    sentences = [
        "The assay measured cytokine release in whole blood samples from patients.",
        "Funding was provided by a national research council.",
    ]

    decision = dx.link_decision(
        "We used the assay measuring cytokine release in whole blood samples.",
        sentences,
    )

    assert decision["status"] == "accepted"
    assert decision["best"] > 0.5
    assert decision["runner_up"] < decision["best"]


def test_link_decision_is_ambiguous_when_two_sentences_tie() -> None:
    sentences = [
        "The assay measured cytokine release in whole blood.",
        "The assay measured cytokine release in whole blood too.",
    ]

    decision = dx.link_decision("the assay measured cytokine release in whole blood", sentences)

    assert decision["status"] == "ambiguous"


def test_rule_grid_moves_accept_and_escalation_in_opposite_directions() -> None:
    rows = [
        _row("r1", context="The assay measured cytokine release in whole blood samples."),
        _row("r2", context="A completely different topic about hospital admissions."),
    ]
    per_row = [
        {
            "row_id": "r1",
            "label": "MENTIONS",
        },
        {"row_id": "r2", "label": "MENTIONS"},
    ]

    def loader(_pmcid: str) -> list[str]:
        return [
            "The assay measured cytokine release in whole blood samples from patients.",
            "Hospital admissions rose sharply in the winter months.",
        ]

    manifests = {"r1": {"source_pmcid": "PMC1"}, "r2": {"source_pmcid": "PMC1"}}

    grid = dx.rule_grid(per_row, rows, loader, manifests, coverages=(0.2, 0.5), margins=(0.05,))

    cells = grid["cells"]
    assert isinstance(cells, list)
    loose, tight = cells[0], cells[1]
    assert loose["accepted"] >= tight["accepted"]
    assert loose["escalation_rate"] <= tight["escalation_rate"]


def test_diagnose_reports_coverage_and_names_the_dropped_positives(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    rows = [
        _row("p1", label="RELIES_ON", claim="A found 42% mortality."),
        _row("p2", label="MENTIONS", claim="A found others."),
        _row("p3", label="MENTIONS"),
    ]
    manifests = {
        "p1": {"row_id": "p1", "linked": "true", "source_pmcid": "PMC1"},
        "p2": {"row_id": "p2", "linked": "true", "source_pmcid": "PMC1"},
        "p3": {"row_id": "p3", "linked": "false", "source_pmcid": "PMC2"},
    }
    body = {
        "PMC1": ["The cohort showed 42% mortality among untreated patients."],
        "PMC2": [],
    }
    monkeypatch.setattr(dx, "REPORT", tmp_path / "report.md")

    summary = dx.diagnose(
        rows,
        manifests,
        v2={"p1": {"score": "90"}, "p2": {"score": "10"}, "p3": {"score": "0"}},
        v3={"p1": {"score": "40"}},
        sentence_loader=lambda pmcid: body.get(pmcid, []),
    )

    assert summary["rows"] == 3
    assert summary["positives_count"] == 1
    assert summary["linkage"]["linked"] == 2
    assert summary["source_text"]["rows_without_body"] == 1
    assert summary["cascade_ceiling"]["dropped"] == []
    assert summary["detectors"]["v3"]["hits"] == 1

    dx.write_report(summary)
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "P3-06" in text
    assert "| Min cov |" in text
    assert "no LLM calls" in text.lower() or "No LLM calls" in text
