"""P1-10 baseline extraction planning and execution (offline-testable).

The runner calls only :class:`axion.llm.client.LLMClient`; there is no provider
SDK here. A dry run parses real text and estimates calls/tokens without making
any call, so it fails closed while prices are blank.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from axion.eval.cost_estimate import DEFAULT_SEED, sample_papers
from axion.extract.claims import (
    PROMPT_VERSION,
    BaselineDocument,
    CandidateClaim,
    ClaimExtraction,
    ClaimFailure,
    SilverClaim,
    SilverManifest,
    append_candidate_claims,
    append_processed_paper,
    append_silver_claims,
    audit_context,
    build_baseline_document,
    read_processed_paper_ids,
    read_silver_paper_ids,
    utc_now_iso,
    verify_claims,
    write_failures,
    write_silver_manifest,
)
from axion.extract.prompting import render_claim_prompt
from axion.ingest.corpus import CorpusPaper
from axion.llm.client import LLMClient
from axion.llm.errors import (
    AllProvidersFailedError,
    DailyQuotaError,
    FailureDetail,
    StructuredOutputError,
    failure_detail,
)
from axion.llm.models import LLMRequest
from axion.llm.pacing import RequestPacer
from axion.parse.jats import JatsParseError, parse_jats_file

CHARS_PER_TOKEN = 4.0
DEFAULT_MAX_CLAIMS = 25
OUTPUT_TOKENS_PER_CLAIM = 120
DEFAULT_MAX_CALLS = 100


class ExtractionError(Exception):
    """Raised when a plan cannot be built safely."""


@dataclass(frozen=True)
class PaperPlan:
    paper: CorpusPaper
    document: BaselineDocument
    prompt: str
    prompt_tokens_estimate: int


@dataclass(frozen=True)
class PlanReport:
    requested: int
    with_text: int
    missing_fulltext: int
    parse_failures: int
    empty_documents: int
    mean_prompt_tokens: float
    median_prompt_tokens: float
    p95_prompt_tokens: float


class DryRunEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["estimate"] = "estimate"
    sample_size: int
    seed: int
    prompt_version: str
    papers_with_text: int
    estimated_calls: int
    prompt_tokens_total: int
    prompt_tokens_mean: float
    claims_per_paper_scenarios: dict[str, float] = Field(default_factory=dict)
    output_tokens_by_scenario: dict[str, int] = Field(default_factory=dict)
    expected_claims_by_scenario: dict[str, float] = Field(default_factory=dict)
    clears_200_claims_at_5_per_paper: bool
    recommended_sample_size: int
    method: str
    cost_status: str


@dataclass(frozen=True)
class RunReport:
    papers_processed: int
    claims: int
    failures: int
    calls: int
    claims_path: Path
    failures_path: Path
    manifest_path: Path
    candidates_path: Path
    stopped_reason: str | None = None
    strict_claims: int = 0
    strict_span_failures: int = 0
    span_failures: int = 0
    normalization_fixes: int = 0
    structured_output_failures: int = 0


def _prompt_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def _read_failures(path: Path) -> list[ClaimFailure]:
    if not path.exists():
        return []
    failures: list[ClaimFailure] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            failures.append(ClaimFailure.model_validate_json(line))
        except ValueError:
            continue
    return failures


def _daily_quota_cause(exc: BaseException) -> bool:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, DailyQuotaError):
            return True
        current = current.__cause__
    return False


def _provider_failure_reason(exc: AllProvidersFailedError, detail: FailureDetail) -> str:
    """Map a provider failure to the run's stop reason.

    A daily quota and a 429/RESOURCE_EXHAUSTED both stop the run cleanly; they
    must never be reported as a generic provider failure that invites a retry.
    """
    if _daily_quota_cause(exc) or detail.error_class == "DailyQuotaError":
        return "daily_quota_reached"
    if detail.error_class == "RateLimitError":
        return "rate_limited"
    return "provider_failed"


def _provider_failure(
    paper_id: str,
    exc: BaseException,
    *,
    reason: str,
    detail: FailureDetail,
) -> ClaimFailure:
    """Build a failure record carrying the sanitized root cause."""
    attempts = getattr(exc, "attempts", None) if isinstance(exc, BaseException) else None
    return ClaimFailure(
        paper_id=paper_id,
        claim_index=-1,
        reason=reason,
        detail=str(exc)[:300],
        error_class=detail.error_class,
        error_message=detail.message,
        http_status=detail.http_status,
        provider_status=detail.provider_status,
        finish_reason=detail.finish_reason,
        prompt_tokens=detail.prompt_tokens,
        completion_tokens=detail.completion_tokens,
        reasoning_tokens=detail.reasoning_tokens,
        attempts=attempts if isinstance(attempts, int) else None,
        retryable=detail.retryable,
    )


def build_plan(
    papers: Sequence[CorpusPaper],
    cache_dir: Path,
    *,
    sample_size: int = 100,
    seed: int = DEFAULT_SEED,
    prompt_version: str = PROMPT_VERSION,
    max_claims: int = DEFAULT_MAX_CLAIMS,
) -> tuple[list[PaperPlan], PlanReport]:
    """Parse a seeded paper sample and render one prompt per usable paper."""
    if sample_size < 1:
        raise ExtractionError("sample_size must be at least 1")
    chosen = sample_papers(papers, sample_size, seed=seed)
    plans: list[PaperPlan] = []
    missing = 0
    parse_failures = 0
    empty = 0
    for paper in chosen:
        path = cache_dir / "fulltext" / f"{paper.pmcid}.xml"
        if not path.exists():
            missing += 1
            continue
        try:
            parsed = parse_jats_file(path, paper_id=paper.pmcid)
        except JatsParseError:
            parse_failures += 1
            continue
        document = build_baseline_document(parsed)
        if not document.sections:
            empty += 1
            continue
        prompt = render_claim_prompt(document, version=prompt_version, max_claims=max_claims)
        plans.append(
            PaperPlan(
                paper=paper,
                document=document,
                prompt=prompt,
                prompt_tokens_estimate=_prompt_tokens(prompt),
            )
        )
    tokens = [plan.prompt_tokens_estimate for plan in plans]
    report = PlanReport(
        requested=len(chosen),
        with_text=len(plans),
        missing_fulltext=missing,
        parse_failures=parse_failures,
        empty_documents=empty,
        mean_prompt_tokens=statistics.fmean(tokens) if tokens else 0.0,
        median_prompt_tokens=statistics.median(tokens) if tokens else 0.0,
        p95_prompt_tokens=(
            sorted(tokens)[min(len(tokens) - 1, round(0.95 * (len(tokens) - 1)))] if tokens else 0.0
        ),
    )
    return plans, report


def dry_run_estimate(
    plans: Sequence[PaperPlan],
    report: PlanReport,
    *,
    seed: int,
    prompt_version: str = PROMPT_VERSION,
    claims_per_paper: Sequence[float] = (2.0, 5.0, 10.0),
) -> DryRunEstimate:
    """Estimate calls/tokens from real parsed text; no model call is made."""
    calls = len(plans)
    prompt_tokens = sum(plan.prompt_tokens_estimate for plan in plans)
    scenarios = {f"{rate:g}": rate for rate in claims_per_paper}
    output = {
        key: int(round(calls * rate * OUTPUT_TOKENS_PER_CLAIM)) for key, rate in scenarios.items()
    }
    expected = {key: calls * rate for key, rate in scenarios.items()}
    at_five = expected.get("5", 0.0)
    # Target 200 audited claims with margin; 5/paper is the conservative case
    # used for the size decision until the extractor measures the real rate.
    recommended = calls if at_five >= 300 else max(100, math.ceil(300 / 5.0))
    return DryRunEstimate(
        sample_size=report.requested,
        seed=seed,
        prompt_version=prompt_version,
        papers_with_text=calls,
        estimated_calls=calls,
        prompt_tokens_total=prompt_tokens,
        prompt_tokens_mean=report.mean_prompt_tokens,
        claims_per_paper_scenarios=scenarios,
        output_tokens_by_scenario=output,
        expected_claims_by_scenario=expected,
        clears_200_claims_at_5_per_paper=at_five >= 200,
        recommended_sample_size=recommended,
        method=(
            "Token counts are ceil(characters/4) over the rendered prompt "
            "(baseline sections plus instructions). Output assumes "
            f"{OUTPUT_TOKENS_PER_CLAIM} tokens per claim. Claims/paper is a scenario, "
            "not a measurement; no extractor has run."
        ),
        cost_status=(
            "not computed here: this is a dry-run estimate; the paid run records "
            "actual list-price cost in the ledger"
        ),
    )


def run_extraction(
    client: LLMClient,
    plans: Sequence[PaperPlan],
    *,
    run_id: str,
    output_dir: Path,
    corpus_manifest_sha256: str,
    papers_file: str,
    papers_sha256: str,
    sample_size: int,
    seed: int,
    prompt_version: str = PROMPT_VERSION,
    max_calls: int = DEFAULT_MAX_CALLS,
    max_output_tokens: int = 8192,
    thinking_level: str | None = None,
    temperature: float | None = None,
    pacer: RequestPacer | None = None,
) -> RunReport:
    """Run every planned paper through the client; failures are kept.

    The run is resumable: completed papers (including zero-claim papers) are
    skipped, silver claims and audit candidates are de-duplicated by key, and a
    provider failure stops at a clean checkpoint instead of losing the manifest.
    """
    if max_calls < 1:
        raise ExtractionError("max_calls must be at least 1")
    output_dir.mkdir(parents=True, exist_ok=True)
    claims_path = output_dir / "silver_claims.jsonl"
    candidates_path = output_dir / "candidates.jsonl"
    processed_path = output_dir / "papers_processed.jsonl"
    failures_path = output_dir / "failures.jsonl"
    manifest_path = output_dir / "silver_manifest.json"
    done = read_silver_paper_ids(claims_path) | read_processed_paper_ids(processed_path)
    failures: list[ClaimFailure] = _read_failures(failures_path)
    processed = 0
    calls = 0
    model_name = ""
    provider_name: str | None = None
    stopped_reason: str | None = None
    strict_claims = 0
    strict_span_failures = 0
    span_failures = 0
    normalization_fixes = 0
    structured_output_failures = 0

    for plan in plans:
        paper_id = plan.paper.pmcid
        if paper_id in done:
            continue
        if calls >= max_calls:
            failures.append(
                ClaimFailure(
                    paper_id=paper_id,
                    claim_index=-1,
                    reason="max_calls_reached",
                    detail=f"stopped at max_calls={max_calls}",
                )
            )
            stopped_reason = "max_calls_reached"
            break
        calls += 1
        try:
            result = client.complete(
                LLMRequest(
                    prompt=plan.prompt,
                    stage="teacher_label",
                    tier="large",
                    run_id=run_id,
                    paper_id=paper_id,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                    thinking_level=thinking_level,
                    response_schema=ClaimExtraction,
                ),
                response_model=ClaimExtraction,
                attempt_gate=None if pacer is None else pacer.reserve,
            )
        except DailyQuotaError as exc:
            failures.append(
                _provider_failure(
                    paper_id,
                    exc,
                    reason="daily_quota_reached",
                    detail=failure_detail(exc),
                )
            )
            stopped_reason = "daily_quota_reached"
            break
        except StructuredOutputError as exc:
            structured_output_failures += 1
            failures.append(
                ClaimFailure(
                    paper_id=paper_id,
                    claim_index=-1,
                    reason="structured_output",
                    detail=str(exc)[:300],
                )
            )
            continue
        except AllProvidersFailedError as exc:
            detail = exc.detail or failure_detail(exc)
            reason = _provider_failure_reason(exc, detail)
            failures.append(_provider_failure(paper_id, exc, reason=reason, detail=detail))
            stopped_reason = reason
            break
        model_name = result.model
        provider_name = result.provider
        if result.parsed is None:
            structured_output_failures += 1
            failures.append(
                ClaimFailure(
                    paper_id=paper_id,
                    claim_index=-1,
                    reason="structured_output",
                    detail="client returned no parsed model",
                )
            )
            continue
        extraction = cast(ClaimExtraction, result.parsed)
        valid, rejected = verify_claims(extraction, plan.document, paper_id=paper_id)
        strict_valid, strict_rejected = verify_claims(
            extraction, plan.document, paper_id=paper_id, normalize=False
        )
        strict_span_failures += sum(
            failure.reason == "evidence_span_not_verbatim" for failure in strict_rejected
        )
        rejected_spans = sum(failure.reason == "evidence_span_not_verbatim" for failure in rejected)
        span_failures += rejected_spans
        normalization_fixes += max(
            0,
            sum(failure.reason == "evidence_span_not_verbatim" for failure in strict_rejected)
            - rejected_spans,
        )
        strict_claims += len(strict_valid)
        failures.extend(rejected)
        rows = [
            SilverClaim(
                run_id=run_id,
                paper_id=paper_id,
                pmcid=plan.paper.pmcid,
                teacher_model=result.model,
                prompt_version=prompt_version,
                claim_index=index,
                claim=claim,
                created_at=utc_now_iso(),
            )
            for index, claim in enumerate(valid)
        ]
        candidates: list[CandidateClaim] = []
        for index, claim in enumerate(valid):
            before, after = audit_context(
                plan.document, section_label=claim.section, evidence_span=claim.evidence_span
            )
            candidates.append(
                CandidateClaim(
                    claim_id=f"{paper_id}:{index}",
                    paper_id=paper_id,
                    claim_text=claim.claim_text,
                    evidence_span=claim.evidence_span,
                    section=claim.section,
                    paper_title=plan.document.paper_title,
                    context_before=before,
                    context_after=after,
                )
            )
        append_candidate_claims(candidates_path, candidates)
        append_silver_claims(claims_path, rows)
        append_processed_paper(
            processed_path, paper_id=paper_id, claims=len(rows), failures=len(rejected)
        )
        processed += 1
        done.add(paper_id)

    write_failures(failures_path, failures)
    claims_on_disk = (
        len([line for line in claims_path.read_text(encoding="utf-8").splitlines() if line.strip()])
        if claims_path.exists()
        else 0
    )
    manifest = SilverManifest(
        run_id=run_id,
        created_at=utc_now_iso(),
        teacher_model=model_name or "unknown",
        prompt_version=prompt_version,
        provider=provider_name,
        thinking_level=thinking_level,
        max_output_tokens=max_output_tokens,
        temperature=temperature,
        seed=seed,
        sample_size=sample_size,
        papers_processed=len(
            read_processed_paper_ids(processed_path) | read_silver_paper_ids(claims_path)
        ),
        claims=claims_on_disk,
        failures=len(failures),
        corpus_manifest_sha256=corpus_manifest_sha256,
        papers_file=papers_file,
        papers_sha256=papers_sha256,
        failures_file=str(failures_path),
    )
    write_silver_manifest(manifest_path, manifest)
    return RunReport(
        papers_processed=manifest.papers_processed,
        claims=claims_on_disk,
        failures=len(failures),
        calls=calls,
        claims_path=claims_path,
        failures_path=failures_path,
        manifest_path=manifest_path,
        candidates_path=candidates_path,
        stopped_reason=stopped_reason,
        strict_claims=strict_claims,
        strict_span_failures=strict_span_failures,
        span_failures=span_failures,
        normalization_fixes=normalization_fixes,
        structured_output_failures=structured_output_failures,
    )


__all__ = [
    "CHARS_PER_TOKEN",
    "DEFAULT_MAX_CALLS",
    "DEFAULT_MAX_CLAIMS",
    "DryRunEstimate",
    "ExtractionError",
    "PaperPlan",
    "PlanReport",
    "RunReport",
    "build_plan",
    "dry_run_estimate",
    "run_extraction",
]
