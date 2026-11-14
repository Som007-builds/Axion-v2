"""Dry-run sizing for the P1-10 baseline extraction sample.

No extractor, provider SDK, or LLM call lives here. The estimate is computed
from the real parsed JATS text of a seeded, paper-level sample so the owner can
set a budget. ``tokens`` is a heuristic (``ceil(chars / 4)``), not a tokenizer
count; the report labels it as an estimate.
"""

from __future__ import annotations

import math
import random
import re
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from axion.ingest.corpus import CorpusPaper
from axion.parse.jats import ParsedPaper

DEFAULT_SEED = 20261114
CHARS_PER_TOKEN = 4.0


@dataclass(frozen=True)
class PaperTextStats:
    pmcid: str
    sections: int
    paragraphs: int
    chars: int
    words: int
    sentences: int
    contexts: int

    @property
    def tokens(self) -> int:
        """Heuristic token count; not a tokenizer measurement."""
        return math.ceil(self.chars / CHARS_PER_TOKEN)


@dataclass(frozen=True)
class TextSummary:
    papers: int
    sections_mean: float
    paragraphs_mean: float
    chars_mean: float
    chars_median: float
    chars_p95: float
    words_mean: float
    words_p95: float
    tokens_mean: float
    tokens_median: float
    tokens_p95: float
    sentences_mean: float
    contexts_mean: float


@dataclass(frozen=True)
class TokenEstimate:
    papers: int
    claims_per_paper: float
    expected_claims: float
    text_tokens: float
    prompt_tokens: float
    input_tokens: float
    output_tokens: float
    total_tokens: float


def sample_papers(
    papers: Sequence[CorpusPaper], size: int, *, seed: int = DEFAULT_SEED
) -> list[CorpusPaper]:
    """Uniform, seeded, paper-level sample; deterministic for a stable input."""
    if size < 1:
        raise ValueError("sample size must be at least 1")
    ordered = sorted(papers, key=lambda paper: paper.pmcid)
    if size >= len(ordered):
        return ordered
    return sorted(random.Random(seed).sample(ordered, size), key=lambda paper: paper.pmcid)


_SENTENCE_END = re.compile(r"[.!?]+(?:\s+|$)")


def _sentences(text: str) -> int:
    # Deliberately simple and deterministic; abbreviations inflate it slightly.
    return max(len([part for part in _SENTENCE_END.split(text) if part.strip()]), 1)


def paper_text_stats(parsed: ParsedPaper) -> PaperTextStats:
    paragraphs = [paragraph.text for paragraph in parsed.paragraphs if paragraph.text]
    text = "\n".join(paragraphs)
    return PaperTextStats(
        pmcid=parsed.pmcid or parsed.paper_id or "",
        sections=len(parsed.sections),
        paragraphs=len(paragraphs),
        chars=len(text),
        words=len(text.split()),
        sentences=sum(_sentences(paragraph) for paragraph in paragraphs),
        contexts=len(parsed.citation_contexts),
    )


def _percentile(values: Sequence[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(fraction * (len(ordered) - 1))))
    return ordered[index]


def summarize(stats: Sequence[PaperTextStats]) -> TextSummary:
    if not stats:
        raise ValueError("cannot summarize an empty sample")
    chars = [item.chars for item in stats]
    words = [item.words for item in stats]
    tokens = [item.tokens for item in stats]
    return TextSummary(
        papers=len(stats),
        sections_mean=statistics.fmean(item.sections for item in stats),
        paragraphs_mean=statistics.fmean(item.paragraphs for item in stats),
        chars_mean=statistics.fmean(chars),
        chars_median=statistics.median(chars),
        chars_p95=_percentile(chars, 0.95),
        words_mean=statistics.fmean(words),
        words_p95=_percentile(words, 0.95),
        tokens_mean=statistics.fmean(tokens),
        tokens_median=statistics.median(tokens),
        tokens_p95=_percentile(tokens, 0.95),
        sentences_mean=statistics.fmean(item.sentences for item in stats),
        contexts_mean=statistics.fmean(item.contexts for item in stats),
    )


def estimate_tokens(
    summary: TextSummary,
    *,
    papers: int,
    claims_per_paper: float,
    prompt_overhead_tokens: int,
    output_tokens_per_claim: int,
) -> TokenEstimate:
    """Project tokens for ``papers`` at an assumed claims/paper rate."""
    if papers < 1 or claims_per_paper <= 0:
        raise ValueError("papers and claims_per_paper must be positive")
    text_tokens = summary.tokens_mean * papers
    prompt_tokens = float(prompt_overhead_tokens * papers)
    input_tokens = text_tokens + prompt_tokens
    output_tokens = float(papers * claims_per_paper * output_tokens_per_claim)
    return TokenEstimate(
        papers=papers,
        claims_per_paper=claims_per_paper,
        expected_claims=papers * claims_per_paper,
        text_tokens=text_tokens,
        prompt_tokens=prompt_tokens,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def papers_for_claims(target: int, claims_per_paper: float, margin: float = 1.5) -> int:
    """Papers needed to expect ``target`` claims with a safety margin."""
    if target < 1 or claims_per_paper <= 0 or margin < 1.0:
        raise ValueError("target, claims_per_paper, and margin must be positive")
    return math.ceil(target * margin / claims_per_paper)


def usd_cost(
    estimate: TokenEstimate, *, input_usd_per_mtok: float, output_usd_per_mtok: float
) -> float:
    """Formula only; prices must be supplied by the owner (pricing.yaml)."""
    return (
        estimate.input_tokens * input_usd_per_mtok / 1_000_000
        + estimate.output_tokens * output_usd_per_mtok / 1_000_000
    )


__all__ = [
    "CHARS_PER_TOKEN",
    "DEFAULT_SEED",
    "PaperTextStats",
    "TextSummary",
    "TokenEstimate",
    "estimate_tokens",
    "paper_text_stats",
    "papers_for_claims",
    "sample_papers",
    "summarize",
    "usd_cost",
]
