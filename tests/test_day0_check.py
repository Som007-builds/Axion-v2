"""Offline tests for the Day-0 readiness checks."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from scripts.day0_check import (
    FAIL,
    PASS,
    SKIP,
    build_crossref_url,
    build_user_agent,
    check_dry_run,
    check_env_names,
    check_neo4j,
    check_python_version,
    effective_env_values,
    load_env_assignments,
    parse_neo4j_uri,
    required_env_names,
)


def test_load_env_assignments_ignores_comments_and_handles_export(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "# comment",
                "",
                "PLAIN=value",
                "export EXPORTED='quoted value'",
                'DOUBLE="double value"',
                "NO_EQUALS",
            ]
        ),
        encoding="utf-8",
    )

    assert load_env_assignments(env_file) == {
        "PLAIN": "value",
        "EXPORTED": "quoted value",
        "DOUBLE": "double value",
    }


def test_effective_env_prefers_process_environment(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("A=from-file\nB=from-file\n", encoding="utf-8")

    values = effective_env_values(env_file, {"A": "from-process"})

    assert values["A"] == "from-process"
    assert values["B"] == "from-file"


def test_required_env_names_include_provider_keys() -> None:
    names = required_env_names("groq, gemini")

    assert "GROQ_API_KEY" in names
    assert "GEMINI_API_KEY" in names
    assert "ANTHROPIC_API_KEY" not in names


def test_check_env_names_reports_names_not_values() -> None:
    values = {
        "LLM_PROVIDER_CHAIN": "groq",
        "GROQ_API_KEY": "super-secret-value",
    }

    result = check_env_names(values)

    assert result.status == FAIL
    assert "LLM_SMALL_MODEL" in result.detail
    assert "super-secret-value" not in result.detail


def test_check_env_names_accepts_complete_fake_environment() -> None:
    names = required_env_names("groq")
    values = {name: "fake-value" for name in names}
    values["LLM_PROVIDER_CHAIN"] = "groq"

    result = check_env_names(values)

    assert result.status == PASS


def test_check_env_names_reports_unknown_providers() -> None:
    names = required_env_names("groq")
    values = {name: "fake-value" for name in names}
    values["LLM_PROVIDER_CHAIN"] = "groq, mystery"

    result = check_env_names(values)

    assert result.status == FAIL
    assert "mystery" in result.detail


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ((3, 11, 9), PASS),
        ((3, 10, 14), FAIL),
        ((3, 12, 0), FAIL),
    ],
)
def test_python_version_range(
    version: tuple[int, int, int],
    expected: str,
) -> None:
    assert check_python_version(version).status == expected


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        ("bolt://127.0.0.1:7887", ("127.0.0.1", 7887)),
        ("neo4j://localhost", ("localhost", 7687)),
        ("http://localhost:7474", None),
        ("bolt://", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_neo4j_uri(uri: str | None, expected: tuple[str, int] | None) -> None:
    assert parse_neo4j_uri(uri) == expected


def test_neo4j_skips_when_not_configured() -> None:
    result = check_neo4j(None)

    assert result.status == SKIP


def test_neo4j_reports_bad_uri() -> None:
    result = check_neo4j("http://localhost:7474")

    assert result.status == FAIL


def test_dry_run_guard() -> None:
    assert check_dry_run({"AXION_DRY_RUN": "true"}).status == PASS
    assert check_dry_run({"AXION_DRY_RUN": "false"}).status == FAIL
    assert check_dry_run({}).status == FAIL


def test_crossref_url_encodes_mailto() -> None:
    url = build_crossref_url("person+tag@example.org")

    assert "mailto=person%2Btag@example.org" in url


def test_user_agent_identifies_the_tool_and_contact() -> None:
    agent = build_user_agent("person@example.org")

    assert agent.startswith("RetractionScope-Day0Check/")
    assert "mailto:person@example.org" in agent


@pytest.mark.network
@pytest.mark.skipif(
    os.getenv("AXION_RUN_NETWORK") != "1",
    reason="network checks are opt-in; set AXION_RUN_NETWORK=1",
)
def test_network_checks_are_reachable() -> None:
    from scripts.day0_check import check_network

    values = {
        "EUROPEPMC_CONTACT_EMAIL": os.getenv("EUROPEPMC_CONTACT_EMAIL", ""),
        "CROSSREF_CONTACT_EMAIL": os.getenv("CROSSREF_CONTACT_EMAIL", ""),
    }
    if not values["EUROPEPMC_CONTACT_EMAIL"] or not values["CROSSREF_CONTACT_EMAIL"]:
        pytest.skip("contact emails are not set in the process environment")

    results = check_network(values, timeout_s=30.0)

    assert [result.status for result in results] == [PASS, PASS]
