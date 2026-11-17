"""Regression tests for the locked (proposed) P2 operating point."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from axion.eval import escalation
from axion.extract.prompting import load_prompt_template

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "src" / "axion" / "config" / "p2_operating_point.yaml"


def _config() -> dict[str, object]:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def test_config_is_present_and_still_proposed() -> None:
    config = _config()
    assert config["status"] == "proposed"
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


def test_projection_script_is_deterministic(tmp_path: Path) -> None:
    """Two runs of the ledger-driven projection must produce identical output."""
    path = ROOT / "scripts" / "cost_model.py"
    spec = importlib.util.spec_from_file_location("cost_model_p2_test", path)
    if spec is None or spec.loader is None:  # pragma: no cover - import guard
        pytest.skip("cost_model.py cannot be imported")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    first = tmp_path / "a.md"
    second = tmp_path / "b.md"
    if not (ROOT / "eval" / "escalation" / "run_manifest.json").exists():
        pytest.skip("escalation manifest is local-only")
    assert module.main(["--report", str(first)]) == 0
    assert module.main(["--report", str(second)]) == 0
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
