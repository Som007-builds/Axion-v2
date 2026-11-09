#!/usr/bin/env python3
"""Offline secret scan used by pre-commit.

Scans text files in the working tree for common credential shapes. It never
prints the matched value, only the file, line, and rule name. The real local
``.env`` and the untracked private folder are skipped by design.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SELF = Path(__file__).resolve()

EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "_private",
    "data",
    "node_modules",
    "venv",
}

TEXT_SUFFIXES = {
    ".cff",
    ".cfg",
    ".example",
    ".ini",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

# Skip real environment files; only the committed example is inspected.
SKIP_NAMES = {".env", ".env.local", ".env.production", ".env.development"}

PLACEHOLDER_HINTS = (
    "changeme",
    "example",
    "placeholder",
    "redacted",
    "replace",
    "todo",
    "your",
)

HARD_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("github-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("anthropic-key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("groq-key", re.compile(r"\bgsk_[A-Za-z0-9]{20,}\b")),
    ("openai-key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
]

GENERIC_PATTERN = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"]?([A-Za-z0-9_\-/+=.]{12,})['\"]?"
)


def _is_candidate(path: Path) -> bool:
    if path == SELF:
        return False
    if path.name in SKIP_NAMES:
        return False
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".env.example":
        return False
    return not any(part in EXCLUDED_DIRS for part in path.parts)


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(hint in lowered for hint in PLACEHOLDER_HINTS) or set(value) <= {"*", "x", "-"}


def scan_file(path: Path) -> list[tuple[int, str]]:
    findings: list[tuple[int, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return findings

    for lineno, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in HARD_PATTERNS:
            if pattern.search(line):
                findings.append((lineno, rule))
        generic = GENERIC_PATTERN.search(line)
        if generic is not None and not _looks_like_placeholder(generic.group(1)):
            findings.append((lineno, "generic-credential-assignment"))
    return findings


def main() -> int:
    failures = 0
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or not _is_candidate(path):
            continue
        for lineno, rule in scan_file(path):
            relative = path.relative_to(ROOT)
            print(f"{relative}:{lineno}: {rule}")
            failures += 1

    if failures:
        print(f"secret scan failed: {failures} finding(s)", file=sys.stderr)
        return 1
    print("secret scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
