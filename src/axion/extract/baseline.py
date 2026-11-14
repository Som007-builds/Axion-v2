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
    ClaimExtraction,
    ClaimFailure,
    SilverClaim,
    SilverManifest,
    append_silver_claims,
    build_baseline_document,
    read_silver_paper_ids,
    utc_now_iso,
    verify_claims,
    write_failures,
    write_silver_manifest,
)
from axion.extract.prompting import render_claim_prompt
from axion.ingest.corpus import CorpusPaper
from axion.llm.client import LLMClient
from axion.llm.errors import StructuredOutputError
from axion.llm.models import LLMRequest
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


def _prompt_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN)


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
        cost_status="not computed: pricing.yaml is blank; no paid call is authorized",
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
) -> RunReport:
    """Run every planned paper through the client; failures are kept."""
    if max_calls < 1:
        raise ExtractionError("max_calls must be at least 1")
    output_dir.mkdir(parents=True, exist_ok=True)
    claims_path = output_dir / "silver_claims.jsonl"
    failures_path = output_dir / "failures.jsonl"
    manifest_path = output_dir / "silver_manifest.json"
    done = read_silver_paper_ids(claims_path)
    failures: list[ClaimFailure] = []
    processed = 0
    claim_count = 0
    calls = 0
    model_name = ""

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
                ),
                response_model=ClaimExtraction,
            )
        except StructuredOutputError as exc:
            failures.append(
                ClaimFailure(
                    paper_id=paper_id,
                    claim_index=-1,
                    reason="structured_output",
                    detail=str(exc)[:300],
                )
            )
            continue
        model_name = result.model
        if result.parsed is None:
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
        claim_count += append_silver_claims(claims_path, rows)
        processed += 1

    write_failures(failures_path, failures)
    # Re-count from disk so a resumed run reports the full manifest, not this run.
    claims_on_disk = (
        sum(1 for line in claims_path.read_text(encoding="utf-8").splitlines() if line.strip())
        if claims_path.exists()
        else 0
    )
    manifest = SilverManifest(
        run_id=run_id,
        created_at=utc_now_iso(),
        teacher_model=model_name or "unknown",
        prompt_version=prompt_version,
        seed=seed,
        sample_size=sample_size,
        papers_processed=len(done) + processed,
        claims=claims_on_disk,
        failures=len(failures),
        corpus_manifest_sha256=corpus_manifest_sha256,
        papers_file=papers_file,
        papers_sha256=papers_sha256,
        failures_file=str(failures_path),
    )
    write_silver_manifest(manifest_path, manifest)
    return RunReport(
        papers_processed=len(done) + processed,
        claims=claims_on_disk,
        failures=len(failures),
        calls=calls,
        claims_path=claims_path,
        failures_path=failures_path,
        manifest_path=manifest_path,
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
