"""Deterministic exact and near-duplicate sentence detection.

The P2 leverage question is how much prompt text is repeated, not only whether a
paper was already processed. Exact duplicates are found by a normalized key;
near-duplicates are found with a fixed-seed MinHash + LSH pass and verified
with Jaccard similarity over word shingles.

Nothing here calls an LLM and nothing here changes a prompt. The census reports
what is repeated; applying dedup to a prompt is a separate, measurable lever.
"""

from __future__ import annotations

import hashlib
import random
import re
from collections import defaultdict
from dataclasses import dataclass

from axion.extract.claims import normalize_for_match

SHINGLE_SIZE = 5
NEAR_DUPLICATE_THRESHOLD = 0.9
NUM_HASHES = 32
BANDS = 8
ROWS = NUM_HASHES // BANDS  # 4 rows per band
PRIME = (1 << 61) - 1
DEFAULT_SEED = 20261117
_WORD = re.compile(r"\w+", re.UNICODE)


def normalize_sentence(text: str) -> str:
    """Case-folded, whitespace-collapsed key for exact matching."""
    return normalize_for_match(text).casefold().strip()


def _tokens(text: str) -> list[str]:
    return _WORD.findall(normalize_sentence(text))


def word_shingles(text: str, size: int = SHINGLE_SIZE) -> frozenset[str]:
    """Word n-grams; short text is one shingle so it can still be compared."""
    tokens = _tokens(text)
    if len(tokens) < size:
        return frozenset({" ".join(tokens)})
    return frozenset(
        " ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)
    )


def shingle_hashes(text: str, size: int = SHINGLE_SIZE) -> frozenset[int]:
    return frozenset(
        int.from_bytes(hashlib.blake2b(shingle.encode("utf-8"), digest_size=8).digest(), "big")
        for shingle in word_shingles(text, size)
    )


def jaccard(left: frozenset[int], right: frozenset[int]) -> float:
    if not left and not right:
        return 1.0
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / len(union)


def _coefficients(seed: int, count: int = NUM_HASHES) -> list[tuple[int, int]]:
    rng = random.Random(seed)
    return [(rng.randrange(1, PRIME), rng.randrange(0, PRIME)) for _ in range(count)]


def minhash_signature(
    shingles: frozenset[int], coefficients: list[tuple[int, int]]
) -> tuple[int, ...]:
    if not shingles:
        return tuple(0 for _ in coefficients)
    return tuple(min((a * value + b) % PRIME for value in shingles) for a, b in coefficients)


@dataclass(frozen=True)
class DuplicateGroup:
    """One canonical sentence and every copy (including the canonical)."""

    canonical: int
    members: tuple[int, ...]
    exact: bool


@dataclass(frozen=True)
class DedupStats:
    sentences: int
    duplicate_sentences: int
    duplicate_groups: int
    exact_duplicate_sentences: int
    near_duplicate_sentences: int
    cross_paper_duplicate_sentences: int
    within_paper_duplicate_sentences: int
    duplicate_chars: int
    estimated_tokens_saved: int
    threshold: float


class _UnionFind:
    def __init__(self, size: int) -> None:
        self._parent = list(range(size))

    def find(self, node: int) -> int:
        while self._parent[node] != node:
            self._parent[node] = self._parent[self._parent[node]]
            node = self._parent[node]
        return node

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        # Smallest index is the canonical sentence; keeps output order stable.
        low, high = sorted((root_left, root_right))
        self._parent[high] = low


def duplicate_groups(
    texts: list[str],
    *,
    threshold: float = NEAR_DUPLICATE_THRESHOLD,
    seed: int = DEFAULT_SEED,
) -> list[DuplicateGroup]:
    """Group exact copies and near-duplicates (Jaccard >= threshold).

    Exact groups are formed first; MinHash/LSH then proposes candidates between
    the canonical representatives only, and Jaccard verifies each candidate on
    the full shingle sets. The pass is deterministic for a given input order and
    seed.
    """
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between 0 and 1")
    if not texts:
        return []

    normalized = [normalize_sentence(text) for text in texts]
    exact_by_key: dict[str, list[int]] = defaultdict(list)
    for index, key in enumerate(normalized):
        exact_by_key[key].append(index)
    representatives = [members[0] for members in exact_by_key.values()]
    representative_of: dict[int, int] = {}
    for members in exact_by_key.values():
        for member in members:
            representative_of[member] = members[0]

    shingles = {index: shingle_hashes(texts[index]) for index in representatives}
    coefficients = _coefficients(seed)
    signatures = {
        index: minhash_signature(shingles[index], coefficients) for index in representatives
    }

    buckets: dict[tuple[int, tuple[int, ...]], list[int]] = defaultdict(list)
    for index in representatives:
        signature = signatures[index]
        for band in range(BANDS):
            start = band * ROWS
            band_key = (band, signature[start : start + ROWS])
            buckets[band_key].append(index)

    union = _UnionFind(len(texts))
    for members in exact_by_key.values():
        for member in members[1:]:
            union.union(members[0], member)

    compared: set[tuple[int, int]] = set()
    for members in buckets.values():
        if len(members) < 2:
            continue
        for left_position in range(len(members)):
            for right_position in range(left_position + 1, len(members)):
                left, right = sorted((members[left_position], members[right_position]))
                pair = (left, right)
                if pair in compared:
                    continue
                compared.add(pair)
                if jaccard(shingles[left], shingles[right]) >= threshold:
                    union.union(left, right)

    grouped: dict[int, list[int]] = defaultdict(list)
    for index in range(len(texts)):
        grouped[union.find(index)].append(index)

    groups: list[DuplicateGroup] = []
    for members in grouped.values():
        members.sort()
        canonical = members[0]
        same_key = all(normalized[member] == normalized[canonical] for member in members)
        groups.append(
            DuplicateGroup(
                canonical=canonical,
                members=tuple(members),
                exact=same_key,
            )
        )
    groups.sort(key=lambda group: group.canonical)
    return groups


def dedup_stats(
    texts: list[str],
    paper_ids: list[str],
    *,
    threshold: float = NEAR_DUPLICATE_THRESHOLD,
    seed: int = DEFAULT_SEED,
) -> tuple[DedupStats, list[DuplicateGroup]]:
    """Census over a sentence list, splitting duplicates by paper boundary."""
    if len(texts) != len(paper_ids):
        raise ValueError("texts and paper_ids must have the same length")
    groups = duplicate_groups(texts, threshold=threshold, seed=seed)
    exact_duplicates = 0
    near_duplicates = 0
    cross_paper = 0
    within_paper = 0
    duplicate_chars = 0
    duplicate_sentences = 0
    for group in groups:
        if len(group.members) < 2:
            continue
        canonical_paper = paper_ids[group.canonical]
        for member in group.members[1:]:
            duplicate_sentences += 1
            duplicate_chars += len(texts[member])
            if normalize_sentence(texts[member]) == normalize_sentence(texts[group.canonical]):
                exact_duplicates += 1
            else:
                near_duplicates += 1
            if paper_ids[member] == canonical_paper:
                within_paper += 1
            else:
                cross_paper += 1
    stats = DedupStats(
        sentences=len(texts),
        duplicate_sentences=duplicate_sentences,
        duplicate_groups=sum(1 for group in groups if len(group.members) > 1),
        exact_duplicate_sentences=exact_duplicates,
        near_duplicate_sentences=near_duplicates,
        cross_paper_duplicate_sentences=cross_paper,
        within_paper_duplicate_sentences=within_paper,
        duplicate_chars=duplicate_chars,
        estimated_tokens_saved=round(duplicate_chars / 4.0),
        threshold=threshold,
    )
    return stats, groups


__all__ = [
    "BANDS",
    "DEFAULT_SEED",
    "NEAR_DUPLICATE_THRESHOLD",
    "NUM_HASHES",
    "ROWS",
    "SHINGLE_SIZE",
    "DedupStats",
    "DuplicateGroup",
    "dedup_stats",
    "duplicate_groups",
    "jaccard",
    "minhash_signature",
    "normalize_sentence",
    "shingle_hashes",
    "word_shingles",
]
