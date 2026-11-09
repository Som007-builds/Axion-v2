"""Smoke tests for the package skeleton."""

from __future__ import annotations

import importlib

import axion

SUBPACKAGES = (
    "api",
    "config",
    "extract",
    "ingest",
    "link",
    "llm",
    "parse",
    "propagate",
    "store",
)


def test_version_is_set() -> None:
    assert axion.__version__ == "0.1.0"


def test_subpackages_importable() -> None:
    for name in SUBPACKAGES:
        importlib.import_module(f"axion.{name}")
