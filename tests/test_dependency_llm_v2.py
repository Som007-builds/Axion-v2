"""Tests for the P3-05 LLM v2 calibration script (no network, no calls)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
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


def test_combine_judgements_gives_a_graded_range() -> None:
    scores = {lv2.combine_judgements(result, method) for result in range(4) for method in range(4)}

    assert lv2.combine_judgements(0, 0) == 0
    assert lv2.combine_judgements(3, 3) == 100
    assert len(scores) > 3
    assert min(scores) < 40 < 60 < max(scores)
    assert lv2.combine_judgements(3, 0) > lv2.combine_judgements(0, 3)


def test_combine_checklist_caps_corroboration() -> None:
    answer = lv2.DependencyChecklist(
        uses_result_number=True,
        uses_method=True,
        uses_definition_or_parameter=True,
        rests_on_conclusion=True,
        background_or_corroboration=True,
    )

    assert lv2.combine_checklist(answer) == lv2.CORROBORATION_CAP
    plain = lv2.DependencyChecklist(uses_result_number=True, uses_method=True)
    assert lv2.combine_checklist(plain) == 60


def test_score_bands_detects_an_extreme_only_variant() -> None:
    v2_like = lv2.score_bands([0, 5, 10, 95, 100, 100])

    assert v2_like["extreme_only"] is True
    assert v2_like["graded"] is False
    assert v2_like["interior_rows"] == 0


def test_score_bands_detects_a_graded_variant() -> None:
    graded = lv2.score_bands([0, 25, 50, 75, 100, 100])

    assert graded["extreme_only"] is False
    assert graded["graded"] is True
    assert graded["interior_rows"] == 3
    assert graded["distinct_scores"] == 5


def test_variant_metrics_reports_points_and_distribution(tmp_path: Path) -> None:
    rows = [
        _row("p1", label="RELIES_ON", claim="we used the assay from A."),
        _row("n1", label="MENTIONS", context="has been reviewed [1].", section="Introduction"),
        _row("n2", label="MENTIONS", context="see [1] for background.", section="Introduction"),
    ]
    v1 = {row["row_id"]: {"label": "MENTIONS"} for row in rows}
    scores = {"p1": {"score": "90"}, "n1": {"score": "10"}, "n2": {"score": "55"}}

    block = lv2.variant_metrics(rows, scores, v1)

    assert block["rows_scored"] == 3
    distribution = block["distribution"]
    assert isinstance(distribution, dict)
    assert distribution["interior_rows"] == 1
    points = block["points"]
    assert isinstance(points, dict)
    assert points["@80"]["recall"] == 1.0
    assert points["@80"]["false_alarm_rate"] == 0.0


def test_record_variant_replaces_rather_than_duplicates(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "variants.json"
    monkeypatch.setattr(lv2, "VARIANTS_FILE", log_path)
    metrics = {"distribution": {"interior_rows": 1, "distinct_scores": 4}}

    monkeypatch.setattr(lv2, "VARIANTS_FILE", log_path)
    lv2.record_variant("v3", {"variant": "v3", "prompt_version": "a", "metrics": metrics})
    log = lv2.record_variant("v3", {"variant": "v3", "prompt_version": "b", "metrics": metrics})

    assert log["variants_tried"] == 1
    entries = log["variants"]
    assert entries[0]["prompt_version"] == "b"
    assert "best of 1" in log["selection_effect"]


def test_request_schema_and_prompt_come_from_the_same_variant() -> None:
    """The bug this guards: a v3 prompt sent with v2's answer schema."""
    row = _row("p1", label="RELIES_ON", claim="we used the assay from A.")

    for name, expected in (("v2", lv2.DependencyScore), ("v3", lv2.DependencyJudgement)):
        variant = lv2.get_variant(name)
        request = lv2.build_request(row, variant, "run-1")
        assert request.response_schema is expected
        assert request.prompt == variant.prompt(row)
        assert "result_level" in request.prompt if name == "v3" else True

    v3b = lv2.build_request(row, lv2.get_variant("v3b"), "run-1")
    assert v3b.response_schema is lv2.DependencyChecklist
    assert "uses_result_number" in v3b.prompt


def test_variant_stage_keeps_v2_ledgered_under_its_original_name() -> None:
    assert lv2.variant_stage(lv2.get_variant("v2")) == "dependency_llm_v2"
    assert lv2.variant_stage(lv2.get_variant("v3")) == "dependency_llm_v3"


def test_one_stray_interior_row_is_not_a_graded_score() -> None:
    """v2's actual shape: 110 low, 1 middle, 40 high - a decision, not a scale."""
    bands = lv2.score_bands([5] * 110 + [35] + [95] * 39 + [100])

    assert bands["interior_rows"] == 1
    assert bands["interior_band_populated"] is True
    assert bands["graded"] is False


def test_require_complete_names_the_shortfall_and_how_to_resume() -> None:
    rows = [_row("p1"), _row("p2"), _row("p3")]

    with pytest.raises(lv2.IncompleteCheckpoint) as caught:
        lv2.require_complete(rows, {"p1": {"score": "50"}}, "dev rows")

    assert str(caught.value) == "incomplete: 1 of 3 dev rows scored, run again to resume"


def test_require_complete_is_silent_when_every_row_is_scored() -> None:
    rows = [_row("p1"), _row("p2")]

    lv2.require_complete(rows, {"p1": {"score": "50"}, "p2": {"score": "0"}}, "dev rows")


def test_metrics_refuse_a_partial_checkpoint_instead_of_imputing() -> None:
    """The failure the owner hit: 17 of 151 rows, then a BaselineError inside metrics."""
    rows = [_row(f"p{index}", label="RELIES_ON") for index in range(4)]
    partial = {row["row_id"]: {"score": "50"} for row in rows[:2]}
    v1 = {row["row_id"]: {"label": "MENTIONS"} for row in rows}

    with pytest.raises(lv2.IncompleteCheckpoint):
        lv2.dev_metrics(rows, partial, v1)
    with pytest.raises(lv2.IncompleteCheckpoint):
        lv2.variant_metrics(rows, partial, v1)


def test_main_reports_incomplete_checkpoint_and_exits_two(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(lv2, "REPORT", tmp_path / "report.md")
    monkeypatch.setattr(lv2, "VARIANTS_FILE", tmp_path / "variants.json")
    partial = {
        "P3W1-001": {"score": "25", "prompt_version": "p3-05-llm-v3"},
    }
    monkeypatch.setattr(lv2, "read_v2", lambda path=None: partial)

    code = lv2.main(["--variant", "v3"])

    out = capsys.readouterr().out
    assert code == 2
    assert "incomplete: 1 of 151 dev rows scored, run again to resume" in out
    assert "no recall and no false-alarm rate" in (tmp_path / "report.md").read_text(
        encoding="utf-8"
    )


def test_report_lists_failed_attempts_for_an_incomplete_stage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The section the owner asked for: totals plus each failed call, not just a count."""
    ledger_path = tmp_path / "ledger.sqlite3"
    import sqlite3

    with sqlite3.connect(ledger_path) as connection:
        connection.execute(
            "CREATE TABLE llm_calls (id INTEGER PRIMARY KEY, stage TEXT, ts TEXT,"
            " paper_id TEXT, error_class TEXT, error TEXT, cache_hit INTEGER,"
            " prompt_tokens INTEGER, completion_tokens INTEGER, usd TEXT)"
        )
        connection.executemany(
            "INSERT INTO llm_calls VALUES (NULL,?,?,?,?,?,?,?,?,?)",
            [
                (
                    "dependency_llm_v3",
                    "2026-11-19T10:00:00+00:00",
                    "P3W1-001",
                    None,
                    None,
                    0,
                    700,
                    90,
                    "0.0004",
                ),
                (
                    "dependency_llm_v3",
                    "2026-11-19T10:00:10+00:00",
                    "P3W1-018",
                    "ReadError",
                    "TransientProviderError: Gemini transport error: ReadError: [SSL: "
                    "SSLV3_ALERT_BAD_RECORD_MAC]",
                    0,
                    None,
                    None,
                    None,
                ),
            ],
        )

    activity = lv2.ledger_activity("dependency_llm_v3", ledger_path)
    assert activity is not None
    assert activity["attempts"] == 2
    assert activity["succeeded"] == 1
    assert activity["errors"] == 1
    assert activity["failures"][0]["error_class"] == "ReadError"

    from scripts.dependency_baselines import load_rows, scored_rows, spec_rows

    dev = spec_rows(scored_rows(load_rows()), "dev")
    diagnosis = lv2.diagnose(dev, lv2.read_v1())

    monkeypatch.setattr(lv2, "REPORT", tmp_path / "report.md")
    lv2.write_report(
        diagnosis,
        {
            "variant": "v3",
            "incomplete": "incomplete: 17 of 151 dev rows scored, run again to resume",
            "ledger_activity": activity,
        },
    )
    text = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "**incomplete: 17 of 151 dev rows scored, run again to resume.**" in text
    assert "| P3W1-018 | `ReadError` |" in text
    assert "nothing was imputed or dropped" in text


def _ledger_with(rows: list[tuple[str, str | None, int | None]], tmp_path: Path) -> Path:
    import sqlite3

    path = tmp_path / "ledger.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE llm_calls (id INTEGER PRIMARY KEY, ts TEXT, error_class TEXT,"
            " http_status INTEGER)"
        )
        connection.executemany("INSERT INTO llm_calls VALUES (NULL,?,?,?)", rows)
    return path


def test_provider_window_blocks_while_a_fresh_failure_is_recent(tmp_path: Path) -> None:
    """The owner's resume: three SSL failures minutes old must block."""
    path = _ledger_with(
        [
            ("2026-11-19T10:15:56+00:00", None, None),
            ("2026-11-19T10:16:11+00:00", "ReadError", None),
            ("2026-11-19T10:16:26+00:00", "ReadError", None),
        ],
        tmp_path,
    )
    now = datetime(2026, 11, 19, 10, 17, 30, tzinfo=UTC)

    window = lv2.provider_window(path, now=now, cooldown_s=300)

    assert window["blocked"] is True
    assert window["age_s"] == 64
    assert "inside the 300s cooldown" in window["reason"]


def test_provider_window_lets_a_stale_failure_through(tmp_path: Path) -> None:
    """Same ledger six hours later is not an outage, and must not block a resume."""
    path = _ledger_with(
        [
            ("2026-11-19T10:15:56+00:00", None, None),
            ("2026-11-19T10:16:26+00:00", "ReadError", None),
        ],
        tmp_path,
    )
    now = datetime(2026, 11, 19, 16, 30, 0, tzinfo=UTC)

    window = lv2.provider_window(path, now=now, cooldown_s=300)

    assert window["blocked"] is False
    assert "outside the 300s cooldown" in window["reason"]


def test_provider_window_allows_a_run_after_a_success(tmp_path: Path) -> None:
    path = _ledger_with(
        [
            ("2026-11-19T10:16:11+00:00", "ReadError", None),
            ("2026-11-19T10:17:00+00:00", None, None),
        ],
        tmp_path,
    )

    window = lv2.provider_window(path, now=datetime(2026, 11, 19, 10, 17, 30, tzinfo=UTC))

    assert window["blocked"] is False
    assert window["reason"] == "the most recent attempt succeeded"
