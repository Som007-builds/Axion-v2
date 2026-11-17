"""P2-06 prompt batching: several papers per teacher call.

The frozen baseline prompt is one paper per call. This module adds a batched
variant (``claim-extraction-batch-v1``) that packs whole papers into a single
request, so the fixed instruction overhead is paid once per batch instead of
once per paper.

Cost is token based, so the saving is only that shared overhead. The experiment
therefore measures what batching costs as well as what it saves: parse failures,
attribution failures (a claim that names a paper outside the batch), and
verbatim-span rejects. Nothing here changes the baseline prompt or its config.
"""

from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from axion.extract.baseline import PaperPlan
from axion.extract.claims import (
    Claim,
    ClaimExtraction,
    ClaimFailure,
    ClaimType,
    SilverClaim,
    append_processed_paper,
    append_silver_claims,
    read_processed_paper_ids,
    read_silver_paper_ids,
    utc_now_iso,
    verify_claims,
)
from axion.extract.prompting import PromptError, load_prompt_template
from axion.llm.client import LLMClient
from axion.llm.errors import AllProvidersFailedError, DailyQuotaError, StructuredOutputError
from axion.llm.models import LLMRequest
from axion.llm.pacing import RequestPacer

BATCH_PROMPT_VERSION = "claim-extraction-batch-v1"
DEFAULT_BATCH_SIZE = 3
# A batch must stay well inside the model's output budget: a paper can return up
# to `max_claims` claims, so the prompt is capped conservatively.
DEFAULT_MAX_BATCH_TOKENS = 24_000
CHARS_PER_TOKEN = 4.0
MAX_CONSECUTIVE_PROVIDER_FAILURES = 3


class BatchingError(Exception):
    """Raised when batches cannot be planned safely."""


class BatchClaim(BaseModel):
    """One claim attributed to a paper inside the batch."""

    model_config = ConfigDict(extra="forbid")

    paper_id: str = Field(min_length=1)
    claim_text: str = Field(min_length=1)
    section: str = Field(min_length=1)
    evidence_span: str = Field(min_length=1)
    claim_type: ClaimType = "other"


class BatchExtraction(BaseModel):
    """The structured response expected from a batched call."""

    model_config = ConfigDict(extra="forbid")

    claims: list[BatchClaim] = Field(default_factory=list)


@dataclass(frozen=True)
class BatchGroup:
    plans: tuple[PaperPlan, ...]
    prompt: str
    prompt_tokens_estimate: int

    @property
    def paper_ids(self) -> tuple[str, ...]:
        return tuple(plan.paper.pmcid for plan in self.plans)


@dataclass(frozen=True)
class BatchReport:
    run_id: str
    batch_size: int
    prompt_version: str
    batches: int
    papers: int
    claims: int
    calls: int
    parse_failures: int
    attribution_failures: int
    span_failures: int
    stopped_reason: str | None
    prompt_tokens_estimated: int
    per_batch: list[dict[str, object]] = field(default_factory=list)

    def payload(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "batch_size": self.batch_size,
            "prompt_version": self.prompt_version,
            "batches": self.batches,
            "papers": self.papers,
            "claims": self.claims,
            "calls": self.calls,
            "parse_failures": self.parse_failures,
            "attribution_failures": self.attribution_failures,
            "span_failures": self.span_failures,
            "parse_failure_rate": (self.parse_failures / self.calls if self.calls else None),
            "attribution_failure_rate": (
                self.attribution_failures / self.claims if self.claims else None
            ),
            "stopped_reason": self.stopped_reason,
            "prompt_tokens_estimated": self.prompt_tokens_estimated,
            "per_batch": self.per_batch,
        }


def _paper_block(paper_id: str, plan: PaperPlan) -> str:
    return f"=== PAPER {paper_id} ===\n{plan.document.text}"


def render_batch_prompt(
    plans: Sequence[PaperPlan],
    *,
    version: str = BATCH_PROMPT_VERSION,
    max_claims: int,
) -> str:
    """Render one prompt containing every paper in the batch."""
    if not plans:
        raise ValueError("a batch needs at least one paper")
    template = load_prompt_template(version)
    documents = "\n\n".join(_paper_block(plan.paper.pmcid, plan) for plan in plans)
    try:
        return template.format(max_claims=max_claims, documents=documents)
    except (KeyError, IndexError) as exc:
        raise PromptError(f"prompt {version!r} has an unknown placeholder") from exc


def _tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def plan_batches(
    plans: Sequence[PaperPlan],
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_batch_tokens: int = DEFAULT_MAX_BATCH_TOKENS,
    version: str = BATCH_PROMPT_VERSION,
    max_claims: int = 25,
) -> list[BatchGroup]:
    """Greedily pack whole papers up to ``batch_size`` and the token ceiling.

    A single paper always forms its own batch even if it exceeds the token
    ceiling; refusing it would silently drop a paper instead of recording the
    overflow, which is the failure batching is suspected of causing.
    """
    if batch_size < 1:
        raise BatchingError("batch_size must be at least 1")
    groups: list[BatchGroup] = []
    current: list[PaperPlan] = []
    for plan in plans:
        candidate = [*current, plan]
        prompt = render_batch_prompt(candidate, version=version, max_claims=max_claims)
        if current and (len(candidate) > batch_size or _tokens(prompt) > max_batch_tokens):
            prompt = render_batch_prompt(current, version=version, max_claims=max_claims)
            groups.append(BatchGroup(tuple(current), prompt, _tokens(prompt)))
            current = [plan]
            continue
        current = candidate
    if current:
        prompt = render_batch_prompt(current, version=version, max_claims=max_claims)
        groups.append(BatchGroup(tuple(current), prompt, _tokens(prompt)))
    return groups


def attribute(
    extraction: BatchExtraction, plans: Sequence[PaperPlan]
) -> tuple[dict[str, list[Claim]], list[ClaimFailure]]:
    """Split batched claims by paper and verify each against its own document.

    A claim naming a paper that is not in the batch is an ``unknown_paper``
    failure, recorded rather than guessed at; verification then reuses the
    baseline rules verbatim (section must exist, evidence span must be found).
    """
    by_id = {plan.paper.pmcid: plan for plan in plans}
    accepted: dict[str, list[Claim]] = {paper_id: [] for paper_id in by_id}
    failures: list[ClaimFailure] = []
    grouped: dict[str, list[Claim]] = {paper_id: [] for paper_id in by_id}
    for index, claim in enumerate(extraction.claims):
        if claim.paper_id not in by_id:
            failures.append(
                ClaimFailure(
                    paper_id=claim.paper_id,
                    claim_index=index,
                    reason="unknown_paper",
                    detail=f"batched claim names a paper outside the batch: {claim.paper_id!r}",
                    claim_text=claim.claim_text,
                    evidence_span=claim.evidence_span,
                    category="unknown_paper",
                )
            )
            continue
        grouped[claim.paper_id].append(
            Claim(
                claim_text=claim.claim_text,
                section=claim.section,
                evidence_span=claim.evidence_span,
                claim_type=claim.claim_type,
            )
        )
    for paper_id, claims in grouped.items():
        if not claims:
            continue
        valid, rejected = verify_claims(
            ClaimExtraction(claims=claims), by_id[paper_id].document, paper_id=paper_id
        )
        accepted[paper_id] = valid
        failures.extend(rejected)
    return accepted, failures


def _failure_row(failure: ClaimFailure) -> str:
    return json.dumps(failure.model_dump(mode="json"), sort_keys=True)


def run_batches(
    client: LLMClient,
    groups: Sequence[BatchGroup],
    *,
    run_id: str,
    output_dir: Path,
    prompt_version: str = BATCH_PROMPT_VERSION,
    max_calls: int = 100,
    max_output_tokens: int = 16384,
    model: str | None = None,
    temperature: float | None = None,
    thinking_level: str | None = None,
    pacer: RequestPacer | None = None,
) -> BatchReport:
    """Run every batch through ``LLMClient``; failures are kept, never dropped.

    Mirrors the baseline runner's stop policy: a daily-quota or rate-limit
    error stops at a checkpoint, three consecutive provider failures stop the
    run, and an isolated failure is recorded while the batch moves on.
    """
    if max_calls < 1:
        raise BatchingError("max_calls must be at least 1")
    output_dir.mkdir(parents=True, exist_ok=True)
    claims_path = output_dir / "silver_claims.jsonl"
    processed_path = output_dir / "papers_processed.jsonl"
    failures_path = output_dir / "failures.jsonl"

    done = read_silver_paper_ids(claims_path) | read_processed_paper_ids(processed_path)
    calls = 0
    parse_failures = 0
    attribution_failures = 0
    span_failures = 0
    claims_total = 0
    papers_total = 0
    stopped_reason: str | None = None
    consecutive_provider_failures = 0
    per_batch: list[dict[str, object]] = []

    with failures_path.open("a", encoding="utf-8") as failure_log:
        for group in groups:
            if all(paper_id in done for paper_id in group.paper_ids):
                continue
            if calls >= max_calls:
                stopped_reason = "max_calls_reached"
                break
            calls += 1
            try:
                result = client.complete(
                    LLMRequest(
                        prompt=group.prompt,
                        stage="teacher_label",
                        tier="small",
                        model=model,
                        run_id=run_id,
                        paper_id=group.paper_ids[0],
                        max_output_tokens=max_output_tokens,
                        temperature=temperature,
                        thinking_level=thinking_level,
                        response_schema=BatchExtraction,
                        metadata={"batch_papers": str(len(group.plans))},
                    ),
                    response_model=BatchExtraction,
                    attempt_gate=None if pacer is None else pacer.reserve,
                )
            except DailyQuotaError:
                stopped_reason = "daily_quota_reached"
                break
            except StructuredOutputError as exc:
                parse_failures += 1
                failure_log.write(
                    _failure_row(
                        ClaimFailure(
                            paper_id=group.paper_ids[0],
                            claim_index=-1,
                            reason="structured_output",
                            detail=str(exc)[:300],
                        )
                    )
                    + "\n"
                )
                per_batch.append({"papers": list(group.paper_ids), "status": "parse_failure"})
                continue
            except AllProvidersFailedError as exc:
                detail = str(exc)[:300]
                failure_log.write(
                    _failure_row(
                        ClaimFailure(
                            paper_id=group.paper_ids[0],
                            claim_index=-1,
                            reason="provider_failed",
                            detail=detail,
                        )
                    )
                    + "\n"
                )
                consecutive_provider_failures += 1
                per_batch.append({"papers": list(group.paper_ids), "status": "provider_failed"})
                if consecutive_provider_failures >= MAX_CONSECUTIVE_PROVIDER_FAILURES:
                    stopped_reason = "provider_failed"
                    break
                continue
            consecutive_provider_failures = 0
            if result.parsed is None:
                parse_failures += 1
                per_batch.append({"papers": list(group.paper_ids), "status": "empty_parse"})
                continue
            extraction = cast(BatchExtraction, result.parsed)
            accepted, failures = attribute(extraction, group.plans)
            for failure in failures:
                failure_log.write(_failure_row(failure) + "\n")
            unknown = sum(failure.reason == "unknown_paper" for failure in failures)
            attribution_failures += unknown
            span_failures += sum(
                failure.reason == "evidence_span_not_verbatim" for failure in failures
            )
            batch_claims = 0
            for plan in group.plans:
                paper_id = plan.paper.pmcid
                valid = accepted[paper_id]
                rows = [
                    SilverClaim(
                        run_id=run_id,
                        paper_id=paper_id,
                        pmcid=paper_id,
                        teacher_model=result.model,
                        prompt_version=prompt_version,
                        claim_index=index,
                        claim=claim,
                        created_at=utc_now_iso(),
                    )
                    for index, claim in enumerate(valid)
                ]
                append_silver_claims(claims_path, rows)
                append_processed_paper(
                    processed_path,
                    paper_id=paper_id,
                    claims=len(valid),
                    failures=sum(1 for failure in failures if failure.paper_id == paper_id),
                )
                done.add(paper_id)
                batch_claims += len(valid)
                papers_total += 1
            claims_total += batch_claims
            per_batch.append(
                {
                    "papers": list(group.paper_ids),
                    "status": "ok",
                    "claims": batch_claims,
                    "prompt_tokens_estimate": group.prompt_tokens_estimate,
                    "prompt_tokens": result.prompt_tokens,
                    "completion_tokens": result.completion_tokens,
                }
            )

    return BatchReport(
        run_id=run_id,
        batch_size=max((len(group.plans) for group in groups), default=0),
        prompt_version=prompt_version,
        batches=len(groups),
        papers=papers_total,
        claims=claims_total,
        calls=calls,
        parse_failures=parse_failures,
        attribution_failures=attribution_failures,
        span_failures=span_failures,
        stopped_reason=stopped_reason,
        prompt_tokens_estimated=sum(group.prompt_tokens_estimate for group in groups),
        per_batch=per_batch,
    )


__all__ = [
    "BATCH_PROMPT_VERSION",
    "BatchClaim",
    "BatchExtraction",
    "BatchGroup",
    "BatchReport",
    "BatchingError",
    "attribute",
    "plan_batches",
    "render_batch_prompt",
    "run_batches",
]
