#!/usr/bin/env python3
"""Day-0 readiness checks.

The checks are deliberately conservative and never print secret values. Only
environment-variable names, statuses, and non-sensitive details are printed.
Network checks are opt-in with ``--network`` and require contact emails.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import urllib.parse
import urllib.request
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Status = Literal["PASS", "FAIL", "SKIP"]

PASS: Status = "PASS"
FAIL: Status = "FAIL"
SKIP: Status = "SKIP"

DEFAULT_ENV_FILE = Path(".env")
DEFAULT_TIMEOUT_S = 10.0

PROVIDER_KEY_NAMES: dict[str, str] = {
    "groq": "GROQ_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
}

BASE_REQUIRED_ENV_NAMES = (
    "LLM_PROVIDER_CHAIN",
    "LLM_SMALL_MODEL",
    "LLM_LARGE_MODEL",
    "NEO4J_URI",
    "NEO4J_USERNAME",
    "NEO4J_PASSWORD",
    "CROSSREF_CONTACT_EMAIL",
    "EUROPEPMC_CONTACT_EMAIL",
    "AXION_DRY_RUN",
)

EUROPEPMC_URL = (
    "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    "?query=retraction&format=json&pageSize=1"
)
CROSSREF_URL = "https://api.crossref.org/works?rows=1&mailto={email}"


@dataclass(frozen=True)
class CheckResult:
    """One check outcome. Details must not contain secret values."""

    name: str
    status: Status
    detail: str


def split_provider_chain(value: str | None) -> list[str]:
    """Return provider names from a comma-separated chain."""
    if not value:
        return []
    return [item.strip().lower() for item in value.split(",") if item.strip()]


def provider_key_name(provider: str) -> str | None:
    """Return the environment variable that holds a provider key, if known."""
    return PROVIDER_KEY_NAMES.get(provider.strip().lower())


def required_env_names(provider_chain: str | None) -> list[str]:
    """Return required env names for the configured provider chain."""
    names = list(BASE_REQUIRED_ENV_NAMES)
    for provider in split_provider_chain(provider_chain):
        key_name = provider_key_name(provider)
        if key_name is not None:
            names.append(key_name)
    return names


def load_env_assignments(path: Path) -> dict[str, str]:
    """Read dotenv assignments for presence checks only.

    Values stay in memory and are never printed by this module.
    """
    if not path.is_file():
        return {}

    assignments: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if name:
            assignments[name] = value
    return assignments


def effective_env_values(
    env_file: Path,
    environ: Mapping[str, str],
) -> dict[str, str]:
    """Merge the local dotenv file with the process environment.

    Process environment wins, matching pydantic-settings' usual precedence.
    """
    values = load_env_assignments(env_file)
    values.update({name: value for name, value in environ.items()})
    return values


def check_python_version(
    version_info: tuple[int, int, int] | None = None,
) -> CheckResult:
    """Check the project's supported Python range (3.11.x)."""
    if version_info is None:
        current = sys.version_info
        version_info = (current.major, current.minor, current.micro)
    major, minor, micro = version_info
    supported = (major, minor) == (3, 11)
    return CheckResult(
        name="Python version",
        status=PASS if supported else FAIL,
        detail=f"{major}.{minor}.{micro} (requires 3.11.x)",
    )


def check_env_names(values: Mapping[str, str]) -> CheckResult:
    """Check that required env names exist and are non-empty.

    Only names are reported. Values are never included in the result.
    """
    provider_chain = values.get("LLM_PROVIDER_CHAIN")
    missing = [
        name for name in required_env_names(provider_chain) if not values.get(name, "").strip()
    ]
    unknown_providers = [
        provider
        for provider in split_provider_chain(provider_chain)
        if provider_key_name(provider) is None
    ]

    problems: list[str] = []
    if missing:
        problems.append("missing names: " + ", ".join(missing))
    if unknown_providers:
        problems.append("unknown providers: " + ", ".join(unknown_providers))
    if problems:
        return CheckResult("Environment names", FAIL, "; ".join(problems))
    return CheckResult(
        "Environment names",
        PASS,
        "all required names are present (values not printed)",
    )


def check_dry_run(values: Mapping[str, str]) -> CheckResult:
    """Require dry-run to remain enabled until prices and budgets are verified."""
    raw = values.get("AXION_DRY_RUN", "").strip().lower()
    enabled = raw in {"1", "true", "yes", "on"}
    if enabled:
        return CheckResult("Dry-run guard", PASS, "AXION_DRY_RUN is enabled")
    if not raw:
        return CheckResult("Dry-run guard", FAIL, "AXION_DRY_RUN is not set")
    return CheckResult("Dry-run guard", FAIL, "AXION_DRY_RUN is not true")


def check_docker(timeout_s: float = DEFAULT_TIMEOUT_S) -> CheckResult:
    """Check that the Docker CLI exists and the daemon answers."""
    try:
        completed = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CheckResult("Docker", FAIL, f"docker command failed: {type(exc).__name__}")
    if completed.returncode != 0:
        return CheckResult("Docker", FAIL, "Docker daemon is not reachable")
    return CheckResult("Docker", PASS, "Docker daemon is reachable")


def parse_neo4j_uri(uri: str | None) -> tuple[str, int] | None:
    """Return (host, port) for a Bolt/Neo4j URI, or None when malformed."""
    if not uri:
        return None
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme not in {"bolt", "neo4j", "bolt+s", "neo4j+s", "bolt+ssc", "neo4j+ssc"}:
        return None
    if not parsed.hostname:
        return None
    try:
        port = parsed.port or 7687
    except ValueError:
        return None
    return parsed.hostname, port


def check_neo4j(uri: str | None, timeout_s: float = 2.0) -> CheckResult:
    """Check TCP reachability when a Neo4j URI is configured."""
    if not uri:
        return CheckResult("Neo4j", SKIP, "NEO4J_URI is not set")
    endpoint = parse_neo4j_uri(uri)
    if endpoint is None:
        return CheckResult("Neo4j", FAIL, "NEO4J_URI is not a valid Bolt/Neo4j URI")
    host, port = endpoint
    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            pass
    except OSError:
        return CheckResult(
            "Neo4j",
            SKIP,
            "configured but not reachable; start it with docker compose up -d",
        )
    return CheckResult("Neo4j", PASS, f"TCP reachable at {host}:{port}")


def build_user_agent(contact_email: str | None) -> str:
    """Build a polite, identifying User-Agent without changing request semantics."""
    agent = "RetractionScope-Day0Check/0.1 (https://github.com/Som007-builds/RetractionScope)"
    if contact_email:
        agent = f"{agent} mailto:{contact_email}"
    return agent


def build_crossref_url(contact_email: str) -> str:
    """Build the Crossref URL with an encoded polite-pool mailto parameter."""
    return CROSSREF_URL.format(email=urllib.parse.quote(contact_email, safe="@"))


def check_http(
    name: str,
    url: str,
    *,
    user_agent: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> CheckResult:
    """Make one read-only GET request and report only the HTTP status."""
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = getattr(response, "status", response.getcode())
    except Exception as exc:
        return CheckResult(name, FAIL, f"request failed: {type(exc).__name__}")
    if 200 <= int(status) < 300:
        return CheckResult(name, PASS, f"HTTP {status}")
    return CheckResult(name, FAIL, f"HTTP {status}")


def check_network(
    values: Mapping[str, str],
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> list[CheckResult]:
    """Run opt-in read-only reachability checks with contact information."""
    europepmc_email = values.get("EUROPEPMC_CONTACT_EMAIL", "").strip()
    crossref_email = values.get("CROSSREF_CONTACT_EMAIL", "").strip()
    results: list[CheckResult] = []

    if not europepmc_email:
        results.append(
            CheckResult("Europe PMC reachability", SKIP, "EUROPEPMC_CONTACT_EMAIL is not set")
        )
    else:
        results.append(
            check_http(
                "Europe PMC reachability",
                EUROPEPMC_URL,
                user_agent=build_user_agent(europepmc_email),
                timeout_s=timeout_s,
            )
        )

    if not crossref_email:
        results.append(
            CheckResult("Crossref reachability", SKIP, "CROSSREF_CONTACT_EMAIL is not set")
        )
    else:
        results.append(
            check_http(
                "Crossref reachability",
                build_crossref_url(crossref_email),
                user_agent=build_user_agent(crossref_email),
                timeout_s=timeout_s,
            )
        )
    return results


def run_checks(
    env_file: Path = DEFAULT_ENV_FILE,
    environ: Mapping[str, str] | None = None,
    *,
    network: bool = False,
    timeout_s: float = DEFAULT_TIMEOUT_S,
) -> list[CheckResult]:
    """Run the Day-0 checks. Network checks are opt-in."""
    values = effective_env_values(env_file, environ if environ is not None else os.environ)
    results = [
        check_python_version(),
        check_env_names(values),
        check_dry_run(values),
        check_docker(timeout_s=timeout_s),
        check_neo4j(values.get("NEO4J_URI")),
    ]
    if network:
        results.extend(check_network(values, timeout_s=timeout_s))
    return results


def print_results(results: Sequence[CheckResult]) -> None:
    """Print one line per check; details never include secret values."""
    for result in results:
        print(f"{result.status:4} {result.name}: {result.detail}")


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Run RetractionScope Day-0 readiness checks.")
    parser.add_argument(
        "--env-file",
        type=Path,
        default=DEFAULT_ENV_FILE,
        help="dotenv file to read names from (default: .env)",
    )
    parser.add_argument(
        "--network",
        action="store_true",
        help="also run opt-in Europe PMC and Crossref reachability checks",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        help="per-request timeout in seconds (default: 10)",
    )
    args = parser.parse_args(argv)

    results = run_checks(args.env_file, network=args.network, timeout_s=args.timeout)
    print_results(results)
    return 1 if any(result.status == FAIL for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
