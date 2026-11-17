"""Offline tests for exact and near-duplicate sentence detection."""

from __future__ import annotations

import pytest

from axion.extract.dedup import (
    dedup_stats,
    duplicate_groups,
    jaccard,
    normalize_sentence,
    shingle_hashes,
    word_shingles,
)


def test_normalize_sentence_collapses_and_casefolds() -> None:
    assert normalize_sentence("  The  Effect\tof COVID-19. ") == "the effect of covid-19."


def test_exact_duplicates_share_a_group() -> None:
    texts = [
        "A long enough sentence about the same result.",
        "Different sentence here.",
        "A long enough sentence about the same result.",
    ]
    groups = duplicate_groups(texts, threshold=0.99)
    grouped = [group for group in groups if len(group.members) > 1]
    assert len(grouped) == 1
    assert grouped[0].members == (0, 2)
    assert grouped[0].exact is True


def test_near_duplicates_are_verified_by_jaccard() -> None:
    # 100 tokens -> 96 shingles; changing one token touches 5 shingles, so
    # Jaccard is 91/101 and the pair is a genuine near-duplicate.
    left = " ".join(f"token{index}" for index in range(100))
    right = left.replace("token50", "different")
    similarity = jaccard(shingle_hashes(left), shingle_hashes(right))
    assert 0.89 < similarity < 0.92
    groups = duplicate_groups([left, right], threshold=0.9)
    assert any(len(group.members) == 2 for group in groups)
    strict = duplicate_groups([left, right], threshold=0.99)
    assert all(len(group.members) == 1 for group in strict)


def test_short_text_is_still_comparable() -> None:
    assert word_shingles("short text") == frozenset({"short text"})
    groups = duplicate_groups(["short text", "short text"], threshold=0.9)
    assert any(group.members == (0, 1) for group in groups)


def test_groups_are_deterministic() -> None:
    texts = ["Alpha beta gamma delta epsilon zeta.", "Alpha beta gamma delta epsilon zeta."]
    first = duplicate_groups(texts, threshold=0.9, seed=7)
    second = duplicate_groups(texts, threshold=0.9, seed=7)
    assert first == second


def test_dedup_stats_splits_cross_and_within_paper() -> None:
    texts = [
        "A repeated boilerplate sentence that appears in two different papers.",
        "A repeated boilerplate sentence that appears in two different papers.",
        "A unique sentence about the actual intervention and its measured outcome.",
        "A unique sentence about the actual intervention and its measured outcome.",
    ]
    paper_ids = ["PMC1", "PMC2", "PMC1", "PMC1"]
    stats, groups = dedup_stats(texts, paper_ids, threshold=0.99)
    assert stats.sentences == 4
    assert stats.duplicate_sentences == 2
    assert stats.exact_duplicate_sentences == 2
    assert stats.cross_paper_duplicate_sentences == 1
    assert stats.within_paper_duplicate_sentences == 1
    assert stats.duplicate_chars > 0
    assert stats.estimated_tokens_saved == round(stats.duplicate_chars / 4.0)
    assert sum(1 for group in groups if len(group.members) > 1) == 2


def test_no_duplicates_yields_singletons() -> None:
    stats, groups = dedup_stats(
        ["One distinct sentence about alpha.", "Another distinct sentence about beta."],
        ["PMC1", "PMC2"],
    )
    assert stats.duplicate_sentences == 0
    assert all(len(group.members) == 1 for group in groups)


def test_length_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError):
        dedup_stats(["one"], [])


def test_threshold_is_validated() -> None:
    with pytest.raises(ValueError):
        duplicate_groups(["one"], threshold=1.5)
