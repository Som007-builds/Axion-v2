"""Tests for the P3-08 cost scaffold and the silver-plan sizing (numbers only)."""

from __future__ import annotations

from pathlib import Path

import pytest
import scripts.p3_08_cost as cost

from axion.config.settings import Settings


def _ctx(ctx_id: str, source: str, text: str = "B cites A [1].") -> dict[str, str]:
    return {"ctx_id": ctx_id, "source_pmcid": source, "text": text}


def test_silver_pool_excludes_gold_and_every_test_source_context() -> None:
    contexts = [
        _ctx("g1", "SRC_DEV"),
        _ctx("d1", "SRC_DEV"),
        _ctx("t1", "SRC_TEST"),
        _ctx("t2", "SRC_TEST"),
        _ctx("e1", "SRC_DEV", text=""),
    ]
    split = {"SRC_DEV": "dev", "SRC_TEST": "test"}

    eligible, excluded = cost.silver_pool(contexts, split, {"g1", "t1"})

    assert [row["ctx_id"] for row in eligible] == ["d1"]
    assert excluded == {
        "gold_row": 2,
        "test_source_context": 1,
        "empty_context_text": 1,
    }


def test_silver_pool_uses_the_whole_test_source_not_just_sampled_rows() -> None:
    contexts = [_ctx("t2", "SRC_TEST"), _ctx("t3", "SRC_TEST")]
    eligible, excluded = cost.silver_pool(contexts, {"SRC_TEST": "test"}, set())

    assert eligible == []
    assert excluded["test_source_context"] == 2


def test_token_estimate_is_labelled_heuristic() -> None:
    tokens = cost.token_estimate([_ctx("a", "S", text="x" * 400)])

    assert tokens["rows"] == 1
    assert tokens["token_count_is"].startswith("heuristic")
    assert tokens["prompt_tokens"] == 275


def test_price_uses_the_pricing_table_and_per_call_maths() -> None:
    tokens = cost.token_estimate([_ctx("a", "S", text="x" * 400), _ctx("b", "S")])
    priced = cost.price(tokens, Settings().resolved_pricing_path)

    assert priced["model"] == cost.MODEL
    assert priced["list_price_usd"] is not None
    assert float(priced["list_price_per_call_usd"]) > 0


def test_cost_section_reports_e_s_and_the_projection(tmp_path: Path) -> None:
    summary = tmp_path / "detector.json"
    summary.write_text(
        '{"dev": {"candidate_rate": 0.5}}',
        encoding="utf-8",
    )

    block = cost.cost_section(summary, Settings().resolved_pricing_path)

    assert block["escalation_rate_e"] == 0.5
    assert block["stage1_share"] == 0.5
    assert block["student_share_s"] is None, "no student exists; s must not be invented"
    projection = block["projection"]
    assert isinstance(projection, dict)
    assert projection["label"] == "PROJECTED"
    assumptions = projection["assumptions"]
    assert isinstance(assumptions, dict)
    assert assumptions["citer_sources"] == cost.CITER_SOURCES
    assert assumptions["corpus_contexts"] == cost.CORPUS_CONTEXTS
    assert projection["corpus_requests"] == pytest.approx(cost.CORPUS_CONTEXTS * 0.5)


def test_cost_section_requires_the_detector_summary(tmp_path: Path) -> None:
    with pytest.raises(cost.CostError):
        cost.cost_section(tmp_path / "missing.json", Settings().resolved_pricing_path)


def _ledger(tmp_path: Path) -> Path:
    import sqlite3

    path = tmp_path / "ledger.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE llm_calls (stage TEXT, ts TEXT, error TEXT, cache_hit INTEGER,"
            " prompt_tokens INTEGER, completion_tokens INTEGER, usd TEXT)"
        )
        connection.executemany(
            "INSERT INTO llm_calls VALUES (?,?,?,?,?,?,?)",
            [
                ("dependency_llm_v2", "2026-11-19T08:00:00+00:00", None, 0, 400, 40, "0.0002"),
                ("dependency_llm_v2", "2026-11-19T08:00:05+00:00", None, 1, 400, 40, "0"),
                ("dependency_llm_v2", "2026-11-19T08:00:10+00:00", "Transient", 0, 0, 0, "0"),
                ("other_stage", "2026-11-19T08:00:15+00:00", None, 0, 999, 99, "9"),
            ],
        )
    return path


def test_ledger_run_reads_only_its_stage(tmp_path: Path) -> None:
    block = cost.ledger_run(_ledger(tmp_path))

    assert block["attempts"] == 3
    assert block["succeeded"] == 2
    assert block["errors"] == 1
    assert block["cache_hits"] == 1
    assert block["prompt_tokens"] == 800
    assert block["list_price_usd"] == "0.0002"


def test_reconcile_names_the_gap_in_both_directions() -> None:
    ledger = {"prompt_tokens": 71359, "completion_tokens": 5948, "list_price_usd": "0.036276"}
    estimate = {
        "prompt_tokens_estimate": 72283,
        "completion_tokens_estimate": 12080,
        "list_price_usd": "0.051885",
    }

    block = cost.reconcile(ledger, estimate)

    assert block["prompt_token_delta_pct"] == pytest.approx(-0.0128, abs=1e-4)
    assert block["completion_token_delta_pct"] == pytest.approx(-0.5076, abs=1e-4)
    assert block["list_price_actual_usd"] == "0.036276"
