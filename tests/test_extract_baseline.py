"""Offline tests for the P1-10 baseline extraction path."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from axion.config.pricing import PricingTable
from axion.config.settings import Settings
from axion.extract.baseline import build_plan, dry_run_estimate, run_extraction
from axion.extract.claims import (
    Claim,
    ClaimExtraction,
    audit_context,
    build_baseline_document,
    verify_claims,
)
from axion.extract.prompting import load_prompt_template, render_claim_prompt
from axion.ingest.corpus import CorpusPaper
from axion.llm.adapters import ProviderAdapter, ProviderAdapterConfig
from axion.llm.cache import SQLiteCache
from axion.llm.client import LLMClient, RetryPolicy
from axion.llm.errors import FailureDetail, RateLimitError, TransientProviderError
from axion.llm.ledger import SQLiteLedger
from axion.llm.models import ProviderResponse
from axion.llm.pacing import RateLimit, RequestPacer
from axion.llm.providers import ProviderRegistry, ScriptedProvider
from axion.parse.jats import parse_jats

XML = """<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <journal-meta><journal-title-group><journal-title>J</journal-title></journal-title-group></journal-meta>
    <article-meta>
      <article-id pub-id-type="pmcid">PMC1</article-id>
      <article-id pub-id-type="pmid">42</article-id>
      <title-group><article-title>Paper</article-title></title-group>
      <abstract><title>Abstract</title>
        <p>Drug X reduced mortality in the trial cohort.</p></abstract>
    </article-meta>
  </front>
  <body>
    <sec><title>Results</title>
      <p>Drug X reduced mortality in the trial cohort. The effect was consistent across sites.</p>
    </sec>
    <sec><title>Acknowledgements</title><p>We thank the funders.</p></sec>
    <sec><title>Funding</title><p>Grant 123.</p></sec>
    <sec><title>Conflict of interest</title><p>None declared.</p></sec>
  </body>
  <back><ref-list><ref id="b1">
    <element-citation><article-title>Other</article-title></element-citation>
  </ref></ref-list></back>
</article>
"""


def _paper() -> CorpusPaper:
    return CorpusPaper(pmcid="PMC1", pmid="42", doi="10.1000/x", role="source")


def _write_cache(cache: Path) -> Path:
    fulltext = cache / "fulltext"
    fulltext.mkdir(parents=True)
    (fulltext / "PMC1.xml").write_text(XML, encoding="utf-8")
    return cache


def test_baseline_document_excludes_references_and_statements() -> None:
    parsed = parse_jats(XML, paper_id="PMC1")
    document = build_baseline_document(parsed)
    labels = [section.label for section in document.sections]
    assert "Abstract" in labels
    assert "Results" in labels
    assert all("acknowledg" not in label.casefold() for label in labels)
    assert all("funding" not in label.casefold() for label in labels)
    assert all("conflict" not in label.casefold() for label in labels)


def test_claims_require_a_verbatim_span_in_the_named_section() -> None:
    document = build_baseline_document(parse_jats(XML, paper_id="PMC1"))
    extraction = ClaimExtraction(
        claims=[
            Claim(
                claim_text="Drug X reduced mortality.",
                section="Results",
                evidence_span="Drug X reduced mortality in the trial cohort.",
            ),
            Claim(
                claim_text="A paraphrase.",
                section="Results",
                evidence_span="Drug X lowered death.",
            ),
            Claim(
                claim_text="Unknown section.",
                section="Discussion",
                evidence_span="Drug X reduced mortality in the trial cohort.",
            ),
        ]
    )
    valid, failures = verify_claims(extraction, document, paper_id="PMC1")
    assert len(valid) == 1
    assert {failure.reason for failure in failures} == {
        "evidence_span_not_verbatim",
        "unknown_section",
    }


def test_audit_context_contains_the_verbatim_span_and_neighbour() -> None:
    document = build_baseline_document(parse_jats(XML, paper_id="PMC1"))
    span = "Drug X reduced mortality in the trial cohort."
    before, after = audit_context(document, section_label="Results", evidence_span=span)
    assert span in before
    assert "consistent across sites" in before
    assert after == ""


def test_prompt_is_versioned_and_renders_sections() -> None:
    document = build_baseline_document(parse_jats(XML, paper_id="PMC1"))
    template = load_prompt_template("claim-extraction-v1")
    assert "verbatim" in template
    prompt = render_claim_prompt(document, max_claims=5)
    assert "## Results" in prompt
    assert "Drug X reduced mortality" in prompt
    assert "at most 5" in prompt


def test_dry_run_estimates_without_calls(tmp_path: Path) -> None:
    cache = _write_cache(tmp_path / "cache")
    plans, report = build_plan([_paper()], cache, sample_size=1, seed=7)
    estimate = dry_run_estimate(plans, report, seed=7)
    assert report.with_text == 1
    assert estimate.estimated_calls == 1
    assert estimate.prompt_tokens_total > 0
    assert estimate.expected_claims_by_scenario["5"] == 5
    assert estimate.cost_status.startswith("not computed")


def test_runner_uses_fake_provider_and_records_failures(tmp_path: Path) -> None:
    cache = _write_cache(tmp_path / "cache")
    plans, _ = build_plan([_paper()], cache, sample_size=1, seed=7)
    response = ClaimExtraction(
        claims=[
            Claim(
                claim_text="Drug X reduced mortality.",
                section="Results",
                evidence_span="Drug X reduced mortality in the trial cohort.",
            ),
            Claim(
                claim_text="Unsupported.",
                section="Results",
                evidence_span="This sentence is absent.",
            ),
        ]
    ).model_dump_json()
    provider = ScriptedProvider(
        name="fake",
        outcomes=[ProviderResponse(text=response, prompt_tokens=100, completion_tokens=50)],
    )
    registry = ProviderRegistry()
    registry.register(provider)
    settings = Settings(
        _env_file=None,
        llm_large_model="test-large",
        llm_provider_chain=["fake"],
        llm_cache_enabled=False,
        dry_run=False,
    )
    ledger = SQLiteLedger(tmp_path / "ledger.sqlite3")
    client = LLMClient(
        settings,
        registry,
        ledger,
        PricingTable(
            version=1,
            models={
                "test-large": {
                    "provider": "fake",
                    "input_usd_per_mtok": "1",
                    "output_usd_per_mtok": "2",
                }
            },
        ),
        cache=SQLiteCache(tmp_path / "cache.sqlite3"),
        retry=RetryPolicy(max_attempts=1, base_delay_s=0, max_delay_s=0),
    )
    first = run_extraction(
        client,
        plans,
        run_id="run-1",
        output_dir=tmp_path / "silver",
        corpus_manifest_sha256="a" * 64,
        papers_file="papers.csv",
        papers_sha256="b" * 64,
        sample_size=1,
        seed=7,
        model="test-large",
    )
    assert first.calls == 1
    assert first.claims == 1
    assert first.failures == 1
    assert len(provider.calls) == 1
    assert provider.calls[0].model == "test-large"

    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["label_kind"] == "silver"
    assert manifest["not_gold"] is True
    assert manifest["prompt_version"] == "claim-extraction-v1"
    assert manifest["teacher_model"] == "test-large"

    second = run_extraction(
        client,
        plans,
        run_id="run-1",
        output_dir=tmp_path / "silver",
        corpus_manifest_sha256="a" * 64,
        papers_file="papers.csv",
        papers_sha256="b" * 64,
        sample_size=1,
        seed=7,
        model="test-large",
    )
    assert second.calls == 0
    assert second.claims == 1


def test_provider_adapter_is_an_interface_only() -> None:
    with pytest.raises(TypeError):
        ProviderAdapter()  # type: ignore[abstract]
    config = ProviderAdapterConfig(name="future", api_key_env="FUTURE_API_KEY")
    assert config.api_key_env == "FUTURE_API_KEY"


def test_adapter_interface_does_not_import_a_provider_sdk() -> None:
    source = Path("src/axion/llm/adapters.py").read_text(encoding="utf-8")
    assert "import openai" not in source
    assert "import groq" not in source
    assert "import anthropic" not in source


def test_provider_failure_record_carries_the_root_cause(tmp_path: Path) -> None:
    cache = _write_cache(tmp_path / "cache")
    plans, _ = build_plan([_paper()], cache, sample_size=1, seed=7)
    detail = FailureDetail(
        error_class="TransientProviderError",
        message="Gemini server error (503): UNAVAILABLE",
        http_status=503,
        provider_status="UNAVAILABLE",
        retryable=True,
    )
    provider = ScriptedProvider(
        name="fake",
        outcomes=[TransientProviderError("503 UNAVAILABLE", detail=detail)],
    )
    registry = ProviderRegistry()
    registry.register(provider)
    settings = Settings(
        _env_file=None,
        llm_large_model="test-large",
        llm_provider_chain=["fake"],
        llm_cache_enabled=False,
        dry_run=False,
    )
    client = LLMClient(
        settings,
        registry,
        SQLiteLedger(tmp_path / "ledger.sqlite3"),
        PricingTable(
            version=1,
            models={
                "test-large": {
                    "provider": "fake",
                    "input_usd_per_mtok": "1",
                    "output_usd_per_mtok": "2",
                }
            },
        ),
        retry=RetryPolicy(max_attempts=1, base_delay_s=0, max_delay_s=0),
    )

    run = run_extraction(
        client,
        plans,
        run_id="run-fail",
        output_dir=tmp_path / "silver",
        corpus_manifest_sha256="a" * 64,
        papers_file="papers.csv",
        papers_sha256="b" * 64,
        sample_size=1,
        seed=7,
        model="test-large",
        configured_model="test-large",
        configured_provider="fake",
        billing="free_tier",
    )

    # One isolated provider failure no longer ends the batch.
    assert run.stopped_reason is None
    assert run.papers_processed == 0
    rows = [
        json.loads(line)
        for line in run.failures_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    failure = rows[-1]
    assert failure["error_class"] == "TransientProviderError"
    assert failure["http_status"] == 503
    assert failure["provider_status"] == "UNAVAILABLE"
    assert failure["attempts"] == 1
    assert failure["retryable"] is True
    assert failure["detail"].startswith("all LLM providers failed")

    manifest = json.loads(run.manifest_path.read_text(encoding="utf-8"))
    assert manifest["teacher_model"] == "test-large"
    assert manifest["provider"] == "fake"
    assert manifest["billing"] == "free_tier"
    assert manifest["run_id"] == "run-fail"
    assert manifest["prompt_version"] == "claim-extraction-v1"


def test_three_consecutive_provider_failures_stop_the_run(tmp_path: Path) -> None:
    ids = ["PMC1", "PMC2", "PMC3"]
    cache = tmp_path / "cache"
    fulltext = cache / "fulltext"
    fulltext.mkdir(parents=True)
    for index, pmcid in enumerate(ids, start=1):
        xml = XML.replace("PMC1", pmcid).replace(">42<", f">{index}<")
        (fulltext / f"{pmcid}.xml").write_text(xml, encoding="utf-8")
    papers = [
        CorpusPaper(pmcid=pmcid, pmid=str(index), doi=f"10.1000/{pmcid}", role="source")
        for index, pmcid in enumerate(ids, start=1)
    ]
    plans, _ = build_plan(papers, cache, sample_size=3, seed=7)
    provider = ScriptedProvider(
        name="fake",
        outcomes=[TransientProviderError("503 UNAVAILABLE") for _ in range(6)],
    )
    registry = ProviderRegistry()
    registry.register(provider)
    settings = Settings(
        _env_file=None,
        llm_large_model="test-large",
        llm_provider_chain=["fake"],
        llm_cache_enabled=False,
        dry_run=False,
    )
    client = LLMClient(
        settings,
        registry,
        SQLiteLedger(tmp_path / "ledger.sqlite3"),
        PricingTable(
            version=1,
            models={
                "test-large": {
                    "provider": "fake",
                    "input_usd_per_mtok": "1",
                    "output_usd_per_mtok": "2",
                }
            },
        ),
        retry=RetryPolicy(max_attempts=2, base_delay_s=0, max_delay_s=0),
    )

    run = run_extraction(
        client,
        plans,
        run_id="run-outage",
        output_dir=tmp_path / "silver-outage",
        corpus_manifest_sha256="a" * 64,
        papers_file="papers.csv",
        papers_sha256="b" * 64,
        sample_size=3,
        seed=7,
        model="test-large",
    )

    assert run.stopped_reason == "provider_failed"
    assert len(provider.calls) == 6
    rows = [
        json.loads(line)
        for line in run.failures_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert sum(1 for row in rows if row["reason"] == "provider_failed") == 3


def test_rate_limit_stops_the_run_at_a_checkpoint(tmp_path: Path) -> None:
    cache = _write_cache(tmp_path / "cache")
    plans, _ = build_plan([_paper()], cache, sample_size=1, seed=7)
    detail = FailureDetail(
        error_class="RateLimitError",
        message="Gemini rate limit: RESOURCE_EXHAUSTED",
        http_status=429,
        provider_status="RESOURCE_EXHAUSTED",
        retryable=False,
    )
    provider = ScriptedProvider(
        name="fake",
        outcomes=[RateLimitError("429 RESOURCE_EXHAUSTED", detail=detail)],
    )
    registry = ProviderRegistry()
    registry.register(provider)
    settings = Settings(
        _env_file=None,
        llm_large_model="test-large",
        llm_provider_chain=["fake"],
        llm_cache_enabled=False,
        dry_run=False,
    )
    client = LLMClient(
        settings,
        registry,
        SQLiteLedger(tmp_path / "ledger.sqlite3"),
        PricingTable(
            version=1,
            models={
                "test-large": {
                    "provider": "fake",
                    "input_usd_per_mtok": "1",
                    "output_usd_per_mtok": "2",
                }
            },
        ),
        retry=RetryPolicy(max_attempts=2, base_delay_s=0, max_delay_s=0),
    )

    run = run_extraction(
        client,
        plans,
        run_id="run-rate-limit",
        output_dir=tmp_path / "silver-rl",
        corpus_manifest_sha256="a" * 64,
        papers_file="papers.csv",
        papers_sha256="b" * 64,
        sample_size=1,
        seed=7,
        model="test-large",
    )

    assert run.stopped_reason == "rate_limited"
    assert len(provider.calls) == 1
    rows = [
        json.loads(line)
        for line in run.failures_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows[-1]["reason"] == "rate_limited"
    assert rows[-1]["http_status"] == 429


def test_daily_quota_is_a_clean_checkpoint(tmp_path: Path) -> None:
    cache = _write_cache(tmp_path / "cache")
    plans, _ = build_plan([_paper()], cache, sample_size=1, seed=7)
    provider = ScriptedProvider(name="fake", outcomes=[])
    registry = ProviderRegistry()
    registry.register(provider)
    settings = Settings(
        _env_file=None,
        llm_large_model="test-large",
        llm_provider_chain=["fake"],
        llm_cache_enabled=False,
        dry_run=False,
    )
    client = LLMClient(
        settings,
        registry,
        SQLiteLedger(tmp_path / "ledger.sqlite3"),
        PricingTable(
            version=1,
            models={
                "test-large": {
                    "provider": "fake",
                    "input_usd_per_mtok": "1",
                    "output_usd_per_mtok": "2",
                }
            },
        ),
        retry=RetryPolicy(max_attempts=1, base_delay_s=0, max_delay_s=0),
    )
    pacer = RequestPacer(RateLimit(rpm=5, tpm=250_000, rpd=20, daily_margin=2), requests_today=18)

    run = run_extraction(
        client,
        plans,
        run_id="run-quota",
        output_dir=tmp_path / "silver-quota",
        corpus_manifest_sha256="a" * 64,
        papers_file="papers.csv",
        papers_sha256="b" * 64,
        sample_size=1,
        seed=7,
        model="test-large",
        pacer=pacer,
    )

    assert run.stopped_reason == "daily_quota_reached"
    assert provider.calls == []
    rows = [
        json.loads(line)
        for line in run.failures_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert rows[-1]["reason"] == "daily_quota_reached"
    assert "daily request cap" in rows[-1]["detail"]
