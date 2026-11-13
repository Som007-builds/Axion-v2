"""Tests for the persistent LLM response cache."""

from __future__ import annotations

from pathlib import Path

from axion.llm.cache import SQLiteCache, make_cache_key
from axion.llm.models import LLMRequest


def _request(prompt: str = "hello", **kwargs: object) -> LLMRequest:
    return LLMRequest(prompt=prompt, stage="extract", **kwargs)  # type: ignore[arg-type]


def test_cache_key_is_deterministic_and_sensitive() -> None:
    base = _request()
    assert make_cache_key(base, "model-a") == make_cache_key(base, "model-a")
    assert make_cache_key(base, "model-a") != make_cache_key(base, "model-b")
    assert make_cache_key(base, "model-a") != make_cache_key(_request("other"), "model-a")
    assert make_cache_key(base, "model-a") != make_cache_key(_request(temperature=0.5), "model-a")


def test_put_get_and_clear(tmp_path: Path) -> None:
    cache = SQLiteCache(tmp_path / "ledger.sqlite3")
    key = make_cache_key(_request(), "model-a")

    assert cache.get(key) is None
    cache.put(key, provider="primary", model="model-a", text="answer")

    cached = cache.get(key)
    assert cached is not None
    assert cached.provider == "primary"
    assert cached.model == "model-a"
    assert cached.text == "answer"
    assert cache.size() == 1

    cache.clear()
    assert cache.get(key) is None
    assert cache.size() == 0


def test_put_overwrites_same_key(tmp_path: Path) -> None:
    cache = SQLiteCache(tmp_path / "ledger.sqlite3")
    key = make_cache_key(_request(), "model-a")

    cache.put(key, provider="primary", model="model-a", text="first")
    cache.put(key, provider="secondary", model="model-a", text="second")

    cached = cache.get(key)
    assert cached is not None
    assert cached.provider == "secondary"
    assert cached.text == "second"
    assert cache.size() == 1
