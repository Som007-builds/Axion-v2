"""Tests for the P3-05 LLM v2 calibration script (no network, no calls)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
import scripts.dependency_llm_v2 as lv2

from axion.config.settings import Settings


def _row(
    row_id: str,
    label: str = "MENTIONS",
    claim: str = "A claims X.",
    abstract: str = "",
    context: str = "B mentions the topic [1].",
    section: str = "Discussion",
) -> dict[str, str]:
    return {
        "row_id": row_id,
        "wave": "wave1",
        "split": "dev",
        "text_bearing": "true" if (claim or abstract) else "false",
        "weight": "1.0",
        "frame": "text_bearing" if (claim or abstract) else "stub",
        "section": section,
        "section_bucket": "discussion",
        "label": label,
        "context_text": context,
        "paragraph_text": "",
        "source_title": "Source",
        "source_claim_text": claim,
        "source_abstract": abstract,
        "citer_title": "Citer",
    }


def test_label_from_score_uses_the_threshold() -> None:
    assert lv2.label_from_score(70, 60) == "RELIES_ON"
    assert lv2.label_from_score(59, 60) == "MENTIONS"
    assert lv2.label_from_score(0, 0) == "RELIES_ON"


def test_prompt_v2_asks_the_counterfactual_and_requires_a_score() -> None:
    prompt = lv2.build_prompt_v2(_row("a", claim="A claims that X causes Y."))

    assert "Would B's sentence have to change" in prompt
    assert "A claims that X causes Y." in prompt
    assert f"{lv2.BAND_MENTION} or below" in prompt
    assert f"{lv2.BAND_RELIES} or above" in prompt
    assert '"score"' in prompt
    assert "corroboration" in prompt.lower()
    assert "retracted is NOT dependency" in prompt


def test_prompt_v2_says_when_the_source_claim_is_missing() -> None:
    prompt = lv2.build_prompt_v2(_row("b", claim="", abstract=""))
    assert "not available for this source" in prompt


def test_diagnose_counts_claim_availability_and_errors() -> None:
    rows = [
        _row("a", label="RELIES_ON", claim="A claims X."),
        _row("b", label="RELIES_ON", claim="", abstract="Abstract text."),
        _row("c", label="MENTIONS", claim="", abstract=""),
        _row("d", label="MENTIONS", claim="A claims Y."),
    ]
    v1 = {
        "a": {"label": "RELIES_ON"},
        "b": {"label": "MENTIONS"},
        "c": {"label": "MENTIONS"},
        "d": {"label": "RELIES_ON"},
    }

    diagnosis = lv2.diagnose(rows, v1)

    assert diagnosis["rows"] == 4
    assert diagnosis["rows_with_claim"] == 2
    assert diagnosis["rows_abstract_only"] == 1
    assert diagnosis["rows_with_no_source_text"] == 1
    assert diagnosis["rows_with_any_source_text"] == 3
    assert diagnosis["positives_with_claim"] == 1
    assert diagnosis["positives_abstract_only"] == 1
    assert diagnosis["recall"]["hits"] == 1
    assert diagnosis["recall"]["rows"] == 2
    assert diagnosis["predicted_positive_rows"] == 2


def test_diagnose_rejects_rows_without_predictions() -> None:
    with pytest.raises(lv2.LLMv2Error):
        lv2.diagnose([_row("a")], {})


def test_estimate_is_labelled_as_a_heuristic() -> None:
    rows = [_row("a"), _row("b")]
    estimate = lv2.estimate(rows, Settings().resolved_pricing_path)

    assert estimate["rows"] == 2
    assert estimate["token_count_is"] == "heuristic ceil(chars/4)"
    assert estimate["list_price_usd"] is not None
    assert "free_tier" in str(estimate["billing"])


def test_run_live_refuses_over_budget_before_any_call(tmp_path: Path) -> None:
    settings = Settings()
    rows = [_row("a")]
    with pytest.raises(lv2.LLMv2Error, match="exceeds budget"):
        lv2.run_live(
            rows,
            settings=settings,
            pricing_path=settings.resolved_pricing_path,
            max_calls=1,
            budget_usd=Decimal("0"),
        )


def test_v2_checkpoint_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "v2.csv"
    lv2.append_v2(
        path, "a", lv2.DependencyScore(score=88, would_change="uses A's effect size", cue="uses A")
    )

    loaded = json.loads(json.dumps(lv2.read_v2(path)))
    assert loaded["a"]["score"] == "88"
    assert loaded["a"]["cue"] == "uses A"


def test_dev_metrics_compares_v1_v2_and_the_heuristic() -> None:
    rows = [
        _row("p1", label="RELIES_ON", claim="we used the assay from A."),
        _row("p2", label="RELIES_ON", claim="A claims X."),
        _row("n1", label="MENTIONS", context="has been reviewed in [1].", section="Introduction"),
    ]
    v2 = {"p1": {"score": "90"}, "p2": {"score": "10"}, "n1": {"score": "10"}}
    v1 = {"p1": {"label": "RELIES_ON"}, "p2": {"label": "MENTIONS"}, "n1": {"label": "MENTIONS"}}

    metrics = lv2.dev_metrics(rows, v2, v1)

    distribution = metrics["score_distribution"]
    assert isinstance(distribution, dict)
    assert distribution["band_ge_70"] == 1
    assert distribution["band_le_30"] == 2
    table = metrics["table"]
    assert isinstance(table, dict)
    frame = table["text_bearing"]
    assert isinstance(frame, dict)
    assert frame["v1"]["recall"] == 0.5
    assert frame["v2@70"]["recall"] == 0.5
    assert set(frame) >= {"v1", "heuristic", "v2@70"}
