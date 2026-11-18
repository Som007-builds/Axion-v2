"""Regression tests for the locked (accepted) P2 operating point."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
import yaml

from axion.eval import escalation
from axion.extract.prompting import load_prompt_template

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "src" / "axion" / "config" / "p2_operating_point.yaml"


def _config() -> dict[str, object]:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_config_is_present_and_accepted() -> None:
    config = _config()
    assert config["status"] == "accepted"
    assert config["adr"] == "ADR-0022"


def test_policy_version_and_fraction_match_the_measured_policy() -> None:
    config = _config()
    assert config["policy_version"] == escalation.POLICY_VERSION
    assert config["escalation"]["risk_signal"] == escalation.RISK_SIGNAL
    assert config["escalation"]["fraction"] == pytest.approx(escalation.ESCALATION_FRACTION)


def test_stage1_prompt_exists_and_stage_models_are_priced() -> None:
    config = _config()
    load_prompt_template(str(config["stage1"]["prompt_version"]))
    pricing = (ROOT / "src" / "axion" / "config" / "pricing.yaml").read_text(encoding="utf-8")
    assert str(config["stage1"]["model"]) in pricing
    assert str(config["stage2"]["model"]) in pricing


def test_student_k_matches_the_frozen_student_manifest() -> None:
    manifest_path = ROOT / "eval" / "student" / "student_v1.manifest.json"
    if not manifest_path.exists():
        pytest.skip("student artifact is local-only")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    harness_row = manifest.get("harness_row", {})
    k = _config()["student"]["k"]
    if isinstance(harness_row, dict) and "k" in harness_row:
        assert harness_row["k"] == k


def _synth_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Build the three inputs the projection reads, so the test needs no local artifacts.

    `eval/ablation/results/results.json` and `data/ledger.sqlite3` are gitignored and
    regenerable, so CI never has them; synthesising them keeps this a real determinism
    test instead of a skip.
    """
    results = tmp_path / "results.json"
    results.write_text(
        json.dumps([{"config": "baseline", "cost_per_paper_usd": "0.005644590"}]),
        encoding="utf-8",
    )
    escalation_manifest = tmp_path / "run_manifest.json"
    escalation_manifest.write_text(
        json.dumps(
            {
                "e": {"all": 0.3},
                "s_compute": {"0.05": 0.01},
                "cost": {"net_per_paper": "0.002505"},
                "stage2": {
                    "teacher_zero_claim_rate": 0.1,
                    "unit_cost_intro_usd": "0.01",
                },
            }
        ),
        encoding="utf-8",
    )
    ledger = tmp_path / "ledger.sqlite3"
    run_id = "p1-10-flashlite-s20261114-n100"  # cost_model.BASELINE_RUN_ID
    connection = sqlite3.connect(ledger)
    try:
        connection.execute(
            "create table llm_calls (run_id text, paper_id text, prompt_tokens integer,"
            " completion_tokens integer, usd text, error text)"
        )
        connection.execute(
            "insert into llm_calls values (?, ?, ?, ?, ?, ?)",
            (run_id, "PMC1", 1000, 250, "0.005644590", None),
        )
        connection.commit()
    finally:
        connection.close()
    return results, escalation_manifest, ledger


def test_projection_script_is_deterministic(tmp_path: Path) -> None:
    """Two runs of the ledger-driven projection must produce identical output."""
    path = ROOT / "scripts" / "cost_model.py"
    spec = importlib.util.spec_from_file_location("cost_model_p2_test", path)
    if spec is None or spec.loader is None:  # pragma: no cover - import guard
        pytest.skip("cost_model.py cannot be imported")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    results, escalation_manifest, ledger = _synth_inputs(tmp_path)
    first = tmp_path / "a.md"
    second = tmp_path / "b.md"
    args = [
        "--results",
        str(results),
        "--escalation",
        str(escalation_manifest),
        "--ledger",
        str(ledger),
    ]
    assert module.main([*args, "--report", str(first)]) == 0
    assert module.main([*args, "--report", str(second)]) == 0
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
    assert "MEASURED" in first.read_text(encoding="utf-8")
