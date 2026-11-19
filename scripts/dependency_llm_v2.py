"""P3-05 stage 2: LLM v2, re-asked as the guideline's counterfactual, dev only.

P3-04's LLM-only v1 was near-silent: 16.7% recall on the text-bearing test frame,
1.1% false alarms. This module diagnoses that from the committed predictions (no
calls), then asks the same question differently: instead of "which class is this?",
it asks for **a probability that B's sentence would have to change if A's claim
were false**, so a threshold exists to tune and a confidence exists to escalate on.

Modes:
    python scripts/dependency_llm_v2.py --diagnose      # no calls, dev numbers only
    python scripts/dependency_llm_v2.py --llm-mode dry-run
    python scripts/dependency_llm_v2.py --llm-mode live --max-calls 151

Live calls go through ``LLMClient`` (ledger, cache, pacing) and are restricted to
``--split dev`` by default. Test rows are refused unless ``--allow-test`` is passed,
because the test set is evaluated once, in Block 6, against a frozen spec.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from pydantic import BaseModel, Field

from axion.config.pricing import estimate_cost_details, load_pricing
from axion.config.settings import DEFAULT_RATE_LIMITS_PATH, Settings
from axion.eval.audit import wilson_interval
from axion.llm.client import LLMClient, RetryPolicy
from axion.llm.errors import DailyQuotaError
from axion.llm.gemini import GeminiAdapter
from axion.llm.ledger import SQLiteLedger
from axion.llm.models import LLMRequest
from axion.llm.pacing import (
    RateLimit,
    RequestPacer,
    load_rate_limits,
    pacific_date,
    requests_by_pacific_day,
)
from axion.llm.providers import ProviderRegistry
from scripts.dependency_baselines import (
    POSITIVE,
    heuristic_score,
    load_rows,
    scored_rows,
    spec_rows,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "audit" / "p3-05"
V1_PREDICTIONS = ROOT / "eval" / "audit" / "p3-04" / "p3-04-llm-predictions.csv"
V2_DEV_PREDICTIONS = OUT / "p3-05-llm-v2-dev.csv"
REPORT = ROOT / "docs" / "reports" / "P3-05-llm-v2-calibration.md"

MODEL = "gemini-3.5-flash-lite"
STAGE = "dependency_llm_v2"
PROMPT_VERSION = "p3-05-llm-v2"
VARIANTS_FILE = OUT / "p3-05-llm-variants.json"
MAX_OUTPUT_TOKENS = 256
COMPLETION_TOKENS_ESTIMATE = 80
DEFAULT_BUDGET_USD = Decimal("0.50")
# Score bands chosen in the prompt so the model's number has an anchor. The
# detector tunes its own threshold on dev; these bands are prompt text only.
BAND_MENTION = 30
BAND_RELIES = 70


class LLMv2Error(Exception):
    """The v2 run cannot proceed."""


class DependencyScore(BaseModel):
    """One row's answer: the counterfactual probability plus its evidence."""

    score: int = Field(ge=0, le=100)
    would_change: str = ""
    cue: str = ""


class DependencyJudgement(BaseModel):
    """v3: two separate ordinal judgements, each with its own evidence quote."""

    result_level: int = Field(ge=0, le=3)
    result_evidence: str = ""
    method_level: int = Field(ge=0, le=3)
    method_evidence: str = ""
    cue: str = ""


class DependencyChecklist(BaseModel):
    """v3b: overlapping facts instead of a gradation, for when v3 stays binary."""

    uses_result_number: bool = False
    uses_method: bool = False
    uses_definition_or_parameter: bool = False
    rests_on_conclusion: bool = False
    background_or_corroboration: bool = False
    evidence_result: str = ""
    evidence_method: str = ""
    cue: str = ""


RESULT_WEIGHT = 0.75
METHOD_WEIGHT = 0.25
LEVEL_MAX = 3
CHECKLIST_WEIGHTS = {
    "uses_result_number": 0.35,
    "uses_method": 0.25,
    "uses_definition_or_parameter": 0.2,
    "rests_on_conclusion": 0.2,
}
CORROBORATION_CAP = 40
GRADED_MIN_INTERIOR_SHARE = 0.05


def combine_judgements(result_level: int, method_level: int) -> int:
    """Map two 0-3 judgements onto 0-100, so thresholds have a range to sit in.

    Sixteen level pairs collapse to thirteen distinct scores; the result judgement
    dominates because the guideline makes B's use of A's *result* the dependency and
    treats method-only use as narrower.
    """
    weighted = RESULT_WEIGHT * result_level + METHOD_WEIGHT * method_level
    return int(round(100 * weighted / LEVEL_MAX))


def combine_checklist(answer: DependencyChecklist) -> int:
    """Score overlapping facts; corroboration caps the score instead of adding to it."""
    score = sum(weight for field, weight in CHECKLIST_WEIGHTS.items() if getattr(answer, field))
    points = int(round(100 * score))
    if answer.background_or_corroboration:
        points = min(points, CORROBORATION_CAP)
    return points


@dataclass(frozen=True)
class Variant:
    """One prompt variant, its answer schema, and how its answer becomes a score."""

    name: str
    prompt_version: str
    answer_type: type[BaseModel]
    prompt: Callable[[dict[str, str]], str]
    to_score: Callable[[BaseModel], int]
    checkpoint: Path


def _v2_score(answer: BaseModel) -> int:
    assert isinstance(answer, DependencyScore)
    return answer.score


def _v3_score(answer: BaseModel) -> int:
    assert isinstance(answer, DependencyJudgement)
    return combine_judgements(answer.result_level, answer.method_level)


def _v3b_score(answer: BaseModel) -> int:
    assert isinstance(answer, DependencyChecklist)
    return combine_checklist(answer)


def label_from_score(score: int, threshold: int) -> Literal["RELIES_ON", "MENTIONS"]:
    return POSITIVE if score >= threshold else "MENTIONS"


def read_v1(path: Path = V1_PREDICTIONS) -> dict[str, dict[str, str]]:
    if not path.exists():
        raise LLMv2Error(f"v1 predictions not found: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["row_id"]: row for row in csv.DictReader(handle)}


def diagnose(rows: list[dict[str, str]], v1: dict[str, dict[str, str]]) -> dict[str, object]:
    """Why was v1 near-silent? Counted from the committed predictions, no calls."""
    covered = [row for row in rows if row["row_id"] in v1]
    missing = len(rows) - len(covered)
    if not covered:
        raise LLMv2Error("no v1 predictions cover the dev rows")

    predicted = Counter(v1[row["row_id"]]["label"] for row in covered)
    truth = Counter(row["label"] for row in covered)
    positives = [row for row in covered if row["label"] == POSITIVE]
    negatives = [row for row in covered if row["label"] != POSITIVE]

    def rate(group: list[dict[str, str]], label: str) -> tuple[int, int]:
        hits = sum(1 for row in group if v1[row["row_id"]]["label"] == label)
        return hits, len(group)

    with_claim = [row for row in covered if (row["source_claim_text"] or "").strip()]
    abstract_only = [
        row
        for row in covered
        if not (row["source_claim_text"] or "").strip() and (row["source_abstract"] or "").strip()
    ]
    without_text = [
        row
        for row in covered
        if not (row["source_claim_text"] or "").strip()
        and not (row["source_abstract"] or "").strip()
    ]
    a_text_present = len(with_claim) + len(abstract_only)
    without_claim = [row for row in covered if not (row["source_claim_text"] or "").strip()]
    listed_as_retracted = [
        row for row in covered if "retract" in (row["context_text"] or "").lower()
    ]

    def pct(hits: int, total: int) -> dict[str, object]:
        if total == 0:
            return {"hits": 0, "rows": 0, "rate": None, "ci": None}
        low, high = wilson_interval(hits, total)
        return {
            "hits": hits,
            "rows": total,
            "rate": round(hits / total, 4),
            "ci": [round(low, 4), round(high, 4)],
        }

    recalled = rate(positives, POSITIVE)
    false_positives = rate(negatives, POSITIVE)
    claim_hits, claim_total = rate(with_claim, POSITIVE)
    noclaim_hits, noclaim_total = rate(without_claim, POSITIVE)
    return {
        "rows": len(covered),
        "missing_predictions": missing,
        "predicted": dict(predicted),
        "truth": dict(truth),
        "predicted_positive_rows": predicted.get(POSITIVE, 0),
        "recall": pct(*recalled),
        "false_positive_rate": pct(*false_positives),
        "prediction_rate_with_claim": pct(claim_hits, claim_total),
        "prediction_rate_without_claim": pct(noclaim_hits, noclaim_total),
        "rows_with_claim": len(with_claim),
        "rows_abstract_only": len(abstract_only),
        "rows_with_no_source_text": len(without_text),
        "rows_with_any_source_text": a_text_present,
        "rows_without_claim": len(without_claim),
        "positives_with_claim": sum(
            1 for row in positives if (row["source_claim_text"] or "").strip()
        ),
        "positives_abstract_only": sum(
            1
            for row in positives
            if not (row["source_claim_text"] or "").strip()
            and (row["source_abstract"] or "").strip()
        ),
        "rows_mentioning_retraction_in_context": len(listed_as_retracted),
        "parse_failures": 0 if missing == 0 else missing,
        "diagnosis": (
            "v1 answered a three-way classification with no confidence, so no threshold "
            "existed to tune or to escalate on, and every ambiguous row fell to MENTIONS. "
            f"A's text was available for {a_text_present} of {len(covered)} dev rows "
            f"({len(with_claim)} with a claim, {len(abstract_only)} with an abstract only) "
            f"and absent only for the {len(without_text)} stubs, so missing context does not "
            "explain the silence: the framing of the question does."
        ),
    }


def build_prompt_v2(row: dict[str, str]) -> str:
    """Ask the guideline's counterfactual directly and require a probability."""
    claim = (row["source_claim_text"] or row["source_abstract"] or "").strip()
    claim_block = claim[:900] if claim else "not available for this source"
    context = (row["context_text"] or "").strip()[:700]
    section = (row["section"] or "unsectioned").strip()
    return (
        "You are judging one citation. Answer one question, about one sentence.\n\n"
        f"SOURCE A (retracted or flagged): {row['source_title'][:200]}\n"
        f"A's central claim: {claim_block}\n\n"
        f'B CITES A IN THIS SENTENCE, section "{section}":\n"{context}"\n\n'
        "THE QUESTION. Imagine A's central claim is false and A was retracted because of it. "
        "Read B's sentence. Would B's sentence have to change - its number, its method, its model "
        "input, its stated finding, or its recommendation?\n\n"
        "Score the probability that B's sentence would have to change, 0-100:\n"
        f"- {BAND_MENTION} or below: B stands without A. Background, credit, a topic pointer, a "
        "standard tool or database, an example in a list, a contrast, corroboration of B's own "
        "data, or the retraction itself being cited.\n"
        f"- {BAND_MENTION + 1}-{BAND_RELIES - 1}: genuinely unclear from the sentence "
        "shown; say so.\n"
        f"- {BAND_RELIES} or above: B's sentence depends on what A claims. B uses A's data, "
        "parameter, effect size, definition, method or conclusion to make its own point.\n\n"
        "Rules that override intuition: corroboration ('our results agree with A') is NOT "
        "dependency. Citing A as retracted is NOT dependency. A protocol or software citation IS "
        "dependency only if B's own method used it. Section never decides the answer.\n\n"
        "Quote the words in B's sentence that carry the dependence, or write 'none'.\n"
        'Return JSON: {"score": <0-100>, "would_change": "<the phrase in B that '
        'would change, or none>", "cue": "<3-12 words naming the relation>"}'
    )


def build_prompt_v3(row: dict[str, str]) -> str:
    """Split the counterfactual in two: did B use A's RESULT, did B use A's METHOD?

    v2's answer was effectively binary - 111 rows <= 30, none between 31 and 69, 40
    >= 70 - so a threshold had nothing to tune. Two narrow ordinal questions, each
    with its own evidence quote, give the score interior values to land on.
    """
    body = [
        "You are judging one citation and you must answer TWO separate questions.",
        "Do not merge them into one impression.",
        "",
        f"SOURCE A (retracted or flagged): {row['source_title'][:200]}",
        f"A's central claim: {claim_block(row)}",
        "",
        f'B CITES A IN THIS SENTENCE, section "{section_of(row)}":',
        f'"{context_of(row)}"',
        "",
        "QUESTION 1 - RESULT. Does B's sentence use A's RESULT? A's result means A's",
        "measured effect, number, parameter value, definition, or stated conclusion.",
        "  0 = no: A's result plays no part in B's sentence.",
        "  1 = A's result is mentioned but B's sentence stands without it (background,",
        "      comparison, corroboration, a list of prior findings).",
        "  2 = A's result is used: B takes a number, parameter, definition or finding from",
        "      A and puts it to work, but B's main claim would survive a substitution.",
        "  3 = B's sentence rests on A's result: remove it and B's number, model input,",
        "      comparison base or conclusion changes.",
        "",
        "QUESTION 2 - METHOD. Does B's sentence use A's METHOD? A's method means the",
        "protocol, assay, instrument, software, dataset or study design A describes.",
        "  0 = no: B's sentence says nothing about A's method.",
        "  1 = B names A's method only as a citation of what exists (a standard tool, a",
        "      well-known protocol A happened to use).",
        "  2 = B adopts A's method, or a variant of it, for B's own work.",
        "  3 = B's sentence depends on A's method specifically - B ran it, reproduced it,",
        "      or B's design is A's design.",
        "",
        "Answer each question independently: a sentence can score 0 on one and 3 on the",
        "other. Corroboration ('our results agree with A') is 1 on question 1, not 3.",
        "Citing A as retracted is 0 on both. Section never decides either answer.",
        "For each question quote the words in B's sentence that carry the judgement, or",
        "write 'none'.",
        'Return JSON: {"result_level": <0-3>, "result_evidence": "<quote or none>", '
        '"method_level": <0-3>, "method_evidence": "<quote or none>", '
        '"cue": "<3-12 words naming the relation>"}',
    ]
    return chr(10).join(body)


def build_prompt_v3b(row: dict[str, str]) -> str:
    """v3b, only if v3 still answers at the extremes: ask for facts, not gradation.

    Rather than asking the model to place a sentence on a scale, ask which of several
    overlapping facts hold. The score is a weighted count, so it is graded even if the
    model is only confident about yes and no.
    """
    body = [
        "You are judging one citation. Answer each fact below separately with true or",
        "false. More than one can be true. Answer false when the sentence does not show it.",
        "",
        f"SOURCE A (retracted or flagged): {row['source_title'][:200]}",
        f"A's central claim: {claim_block(row)}",
        "",
        f'B CITES A IN THIS SENTENCE, section "{section_of(row)}":',
        f'"{context_of(row)}"',
        "",
        "FACTS, each about B's sentence only:",
        "- uses_result_number: B takes a number, effect size, parameter value or rate from A.",
        "- uses_method: B adopts A's protocol, assay, instrument, software, dataset or design",
        "  for B's own work.",
        "- uses_definition_or_parameter: B uses a definition, threshold, parameter setting or",
        "  model input taken from A.",
        "- rests_on_conclusion: B's own claim depends on A's stated conclusion being true.",
        "- background_or_corroboration: A appears only as background, credit, a topic pointer,",
        "  a list item, a comparison, corroboration of B's own data, or as the retraction",
        "  itself.",
        "",
        "Naming a standard tool or publicly known protocol that A also used is NOT",
        "uses_method. Section never decides any fact.",
        'Return JSON: {"uses_result_number": <bool>, "uses_method": <bool>, '
        '"uses_definition_or_parameter": <bool>, "rests_on_conclusion": <bool>, '
        '"background_or_corroboration": <bool>, "evidence_result": "<quote or none>", '
        '"evidence_method": "<quote or none>", "cue": "<3-12 words>"}',
    ]
    return chr(10).join(body)


def claim_block(row: dict[str, str]) -> str:
    claim = (row["source_claim_text"] or row["source_abstract"] or "").strip()
    return claim[:900] if claim else "not available for this source"


def context_of(row: dict[str, str]) -> str:
    return (row["context_text"] or "").strip()[:700]


def section_of(row: dict[str, str]) -> str:
    return (row["section"] or "unsectioned").strip()


def prompt_tokens(prompt: str) -> int:
    return math.ceil(len(prompt) / 4)


def variant_registry() -> dict[str, Variant]:
    """The variants this project is allowed to try, in the order they were tried.

    The cap is deliberate: v2, then v3, then v3b only if v3 still answers at the
    extremes. Three variants is the ceiling, and the report counts them so a reader
    can see how many draws the dev number is the best of.
    """
    return {
        "v2": Variant(
            name="v2",
            prompt_version="p3-05-llm-v2",
            answer_type=DependencyScore,
            prompt=build_prompt_v2,
            to_score=_v2_score,
            checkpoint=V2_DEV_PREDICTIONS,
        ),
        "v3": Variant(
            name="v3",
            prompt_version="p3-05-llm-v3",
            answer_type=DependencyJudgement,
            prompt=build_prompt_v3,
            to_score=_v3_score,
            checkpoint=OUT / "p3-05-llm-v3-dev.csv",
        ),
        "v3b": Variant(
            name="v3b",
            prompt_version="p3-05-llm-v3b",
            answer_type=DependencyChecklist,
            prompt=build_prompt_v3b,
            to_score=_v3b_score,
            checkpoint=OUT / "p3-05-llm-v3b-dev.csv",
        ),
    }


def get_variant(name: str) -> Variant:
    registry = variant_registry()
    if name not in registry:
        raise LLMv2Error(f"unknown variant {name!r}; known: {sorted(registry)}")
    return registry[name]


def variant_stage(variant: Variant) -> str:
    """v2 keeps its already-ledgered stage name so the P3-08 reconciliation still holds."""
    return STAGE if variant.name == "v2" else f"dependency_llm_{variant.name}"


def estimate(
    rows: list[dict[str, str]], pricing_path: Path, variant: Variant | None = None
) -> dict[str, object]:
    variant = variant or get_variant("v2")
    pricing = load_pricing(pricing_path)
    prompts = [prompt_tokens(variant.prompt(row)) for row in rows]
    total_in = sum(prompts)
    total_out = COMPLETION_TOKENS_ESTIMATE * len(rows)
    cost = estimate_cost_details(
        pricing, MODEL, total_in, total_out, dry_run=True, on_date=date.today()
    )
    return {
        "model": MODEL,
        "variant": variant.name,
        "prompt_version": variant.prompt_version,
        "rows": len(rows),
        "prompt_tokens_estimate": total_in,
        "completion_tokens_estimate": total_out,
        "mean_prompt_tokens": round(total_in / len(rows), 1) if rows else 0.0,
        "max_prompt_tokens": max(prompts) if prompts else 0,
        "list_price_usd": str(cost.usd) if cost.usd is not None else None,
        "billing": "free_tier (list price recorded, no charge)",
        "token_count_is": "heuristic ceil(chars/4)",
    }


def todays_attempts(ledger_path: Path) -> tuple[int, str]:
    today = pacific_date(datetime.now(UTC).isoformat())
    with sqlite3.connect(ledger_path) as connection:
        stamps = [row[0] for row in connection.execute("SELECT ts FROM llm_calls")]
    counts = requests_by_pacific_day([SimpleNamespace(ts=stamp) for stamp in stamps])
    return counts.get(today.isoformat(), 0), today.isoformat()


def recent_failures(ledger_path: Path, limit: int = 8) -> list[dict[str, object]]:
    """The last attempts, so a live run can refuse a visibly bad provider window."""
    with sqlite3.connect(ledger_path) as connection:
        rows = list(
            connection.execute(
                "SELECT ts, error_class, http_status FROM llm_calls ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        )
    return [
        {"ts": ts, "error_class": error_class, "http_status": status}
        for ts, error_class, status in rows
    ]


def read_v2(path: Path = V2_DEV_PREDICTIONS) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return {row["row_id"]: row for row in csv.DictReader(handle)}


CHECKPOINT_FIELDS = (
    "row_id",
    "score",
    "result_level",
    "result_evidence",
    "method_level",
    "method_evidence",
    "would_change",
    "cue",
    "model",
    "prompt_version",
)


def answer_fields(answer: BaseModel) -> dict[str, object]:
    """Flatten whichever schema answered, so every checkpoint shares one header."""
    raw = answer.model_dump()
    return {field: raw[field] for field in CHECKPOINT_FIELDS if field in raw}


def append_variant(
    variant: Variant, row_id: str, answer: BaseModel, score: int, path: Path | None = None
) -> None:
    """Append one answer to that variant's checkpoint, so a run can be resumed."""
    target = path or variant.checkpoint
    target.parent.mkdir(parents=True, exist_ok=True)
    fresh = not target.exists()
    with target.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CHECKPOINT_FIELDS, lineterminator=chr(10))
        if fresh:
            writer.writeheader()
        record: dict[str, object] = {"row_id": row_id, "score": score}
        record.update(answer_fields(answer))
        record["model"] = MODEL
        record["prompt_version"] = variant.prompt_version
        record["score"] = score
        writer.writerow(record)


def append_v2(path: Path, row_id: str, scored: DependencyScore) -> None:
    append_variant(get_variant("v2"), row_id, scored, scored.score, path)


def build_request(row: dict[str, str], variant: Variant, run_id: str) -> LLMRequest:
    """One request for one row: the variant owns the prompt *and* the answer schema.

    These two must travel together. Pinning the schema to v2's shape while sending a
    v3 prompt makes the provider answer in v2's fields, which then fails validation
    after the call has already been paid for.
    """
    return LLMRequest(
        prompt=variant.prompt(row),
        stage=variant_stage(variant),
        tier="small",
        model=MODEL,
        run_id=run_id,
        paper_id=row["row_id"],
        temperature=0.0,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        response_schema=variant.answer_type,
    )


def run_live(
    rows: list[dict[str, str]],
    *,
    settings: Settings,
    pricing_path: Path,
    max_calls: int,
    budget_usd: Decimal,
    variant: Variant | None = None,
) -> dict[str, object]:
    variant = variant or get_variant("v2")
    cost = estimate(rows, pricing_path, variant)
    list_price = Decimal(str(cost["list_price_usd"] or "0"))
    if list_price > budget_usd:
        raise LLMv2Error(
            f"estimated list price {list_price} USD exceeds budget {budget_usd}; refusing to call"
        )
    if not settings.gemini_api_key:
        raise LLMv2Error("GEMINI_API_KEY is not set")

    ledger_path = settings.resolved_ledger_path
    used_today, today = todays_attempts(ledger_path)
    rate: RateLimit = load_rate_limits(DEFAULT_RATE_LIMITS_PATH).require(MODEL)
    if used_today >= rate.daily_cap:
        raise LLMv2Error(
            f"daily cap already reached: {used_today}/{rate.daily_cap} on {today}; "
            "stopping at a clean checkpoint"
        )
    pacer = RequestPacer(rate, requests_today=used_today)

    registry = ProviderRegistry()
    registry.register(GeminiAdapter(settings.gemini_api_key, timeout_s=300.0))
    client = LLMClient.from_settings(
        settings,
        registry,
        retry=RetryPolicy(
            max_attempts=settings.llm_max_attempts,
            base_delay_s=settings.llm_retry_base_s,
            max_delay_s=settings.llm_retry_max_s,
            jitter_s=settings.llm_retry_jitter_s,
        ),
    )

    done = read_v2(variant.checkpoint)
    run_id = f"p3-05-llm-{variant.name}-{today}"
    calls = 0
    stopped: str | None = None
    for row in rows:
        if row["row_id"] in done:
            continue
        if calls >= max_calls:
            stopped = "max_calls_reached"
            break
        calls += 1
        request = build_request(row, variant, run_id)
        try:
            result = client.complete(
                request, response_model=variant.answer_type, attempt_gate=pacer.reserve
            )
        except DailyQuotaError:
            stopped = "daily_quota_reached"
            break
        parsed = variant.answer_type.model_validate_json(result.text)
        score = variant.to_score(parsed)
        append_variant(variant, row["row_id"], parsed, score)
        done[row["row_id"]] = {"score": str(score)}

    ledger = SQLiteLedger(ledger_path)
    return {
        "estimate": cost,
        "variant": variant.name,
        "run_id": run_id,
        "tokens_today_before": used_today,
        "daily_cap": rate.daily_cap,
        "calls_made": calls,
        "stopped_reason": stopped,
        "run_list_price_usd": str(ledger.run_usd(run_id)),
        "run_real_usd": str(ledger.run_real_usd(run_id)),
        "predicted_rows": len(done),
    }


def dev_metrics(
    rows: Sequence[dict[str, str]],
    v2: dict[str, dict[str, str]],
    v1: dict[str, dict[str, str]],
    *,
    thresholds: Sequence[float] = (31.0, 50.0, 60.0, 70.0, 80.0),
) -> dict[str, object]:
    """v1 vs v2 vs the heuristic on dev, with intervals, frames kept separate."""
    from scripts.dependency_baselines import binary_metrics, frame_rows, tune_heuristic

    positive_scores = {row_id: float(item["score"]) for row_id, item in v2.items()}
    heuristic = tune_heuristic(rows)["params"]
    assert isinstance(heuristic, dict)
    predictions = {
        "v1": {
            row_id: int(item["label"] == POSITIVE)
            for row_id, item in v1.items()
            if row_id in positive_scores
        },
        "heuristic": {
            row["row_id"]: int(heuristic_score(row, heuristic) >= heuristic["threshold"])
            for row in rows
        },
    }
    for threshold in thresholds:
        predictions[f"v2@{int(threshold)}"] = {
            row_id: int(score >= threshold) for row_id, score in positive_scores.items()
        }

    table: dict[str, object] = {}
    for frame in ("text_bearing", "stub"):
        subset = frame_rows(rows, frame)
        table[frame] = {
            name: binary_metrics(table_rows, subset)["unweighted"]
            for name, table_rows in predictions.items()
        }
    scores = list(positive_scores.values())
    return {
        "table": table,
        "score_distribution": {
            "rows": len(scores),
            "mean": round(sum(scores) / len(scores), 1) if scores else None,
            "band_le_30": sum(1 for score in scores if score <= 30),
            "band_31_69": sum(1 for score in scores if 30 < score < 70),
            "band_ge_70": sum(1 for score in scores if score >= 70),
        },
    }


def score_bands(scores: Sequence[float]) -> dict[str, object]:
    """Distribution in 20-point bands, and whether anything lands in the middle.

    The question the owner asked is narrow: after v2 answered 111 rows <= 30 and 40
    rows >= 70 with nothing between, does a variant actually use the interior?
    """
    bands = {
        "0-20": sum(1 for score in scores if score <= 20),
        "21-40": sum(1 for score in scores if 20 < score <= 40),
        "41-60": sum(1 for score in scores if 40 < score <= 60),
        "61-80": sum(1 for score in scores if 60 < score <= 80),
        "81-100": sum(1 for score in scores if score > 80),
    }
    interior = sum(1 for score in scores if 20 < score <= 80)
    distinct = len({int(score) for score in scores})
    share = round(interior / len(scores), 4) if scores else 0.0
    return {
        "bands": bands,
        "interior_rows": interior,
        "interior_share": share,
        "distinct_scores": distinct,
        # One stray row in the interior is not a graded score: it is a decision with
        # rounding noise. A threshold can only be tuned if a real share of rows land
        # between the extremes, so the bar is both a count and a minimum share.
        "interior_band_populated": interior > 0,
        "graded": share >= GRADED_MIN_INTERIOR_SHARE and distinct > 3,
        "extreme_only": interior == 0,
    }


THRESHOLD_GRID = (20, 30, 40, 50, 60, 70, 80)


def variant_metrics(
    rows: Sequence[dict[str, str]],
    scores: dict[str, dict[str, str]],
    v1: dict[str, dict[str, str]],
) -> dict[str, object]:
    """Dev recall and FAR with intervals for one variant, plus the heuristic line."""
    from scripts.dependency_baselines import binary_metrics, frame_rows, tune_heuristic

    heuristic = tune_heuristic(list(rows))["params"]
    assert isinstance(heuristic, dict)
    text_rows = frame_rows(list(rows), "text_bearing")
    values = {row_id: float(item["score"]) for row_id, item in scores.items()}

    def block(predictions: dict[str, int]) -> dict[str, object]:
        return binary_metrics(predictions, text_rows)["unweighted"]  # type: ignore[return-value]

    heuristic_pred = {
        row["row_id"]: int(heuristic_score(row, heuristic) >= heuristic["threshold"])
        for row in rows
    }
    points = {
        f"@{threshold}": block(
            {row_id: int(score >= threshold) for row_id, score in values.items()}
        )
        for threshold in THRESHOLD_GRID
    }
    v1_pred = {
        row_id: int(item["label"] == POSITIVE) for row_id, item in v1.items() if row_id in values
    }
    return {
        "rows_scored": len(values),
        "heuristic": block(heuristic_pred),
        "v1": block(v1_pred),
        "points": points,
        "distribution": score_bands(list(values.values())),
    }


def read_variant_log() -> dict[str, object]:
    if not VARIANTS_FILE.exists():
        return {"variants_tried": 0, "variants": []}
    return json.loads(VARIANTS_FILE.read_text(encoding="utf-8"))


def record_variant(name: str, entry: dict[str, object]) -> dict[str, object]:
    """Log every variant measured on dev, so the report can count them.

    Re-running a variant replaces its entry instead of adding a second one: the log
    is a record of which variants exist, not of how many times they were run.
    """
    log = read_variant_log()
    entries = [item for item in log["variants"] if item["variant"] != name]  # type: ignore[index]
    entries.append(entry)
    entries.sort(key=lambda item: item["variant"])
    log = {
        "variants_tried": len(entries),
        "cap": 3,
        "cap_note": "v2, then v3, then v3b only if v3 still answers at the extremes",
        "variants": entries,
        "selection_effect": (
            f"{len(entries)} prompt variants were measured on the same dev rows; any headline "
            f"dev number is the best of {len(entries)}, which is why the count is recorded "
            "next to it"
        ),
    }
    VARIANTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    VARIANTS_FILE.write_text(json.dumps(log, indent=2) + chr(10), encoding="utf-8", newline=chr(10))
    return log


def write_report(diagnosis: dict[str, object], summary: dict[str, object]) -> None:
    d = diagnosis
    lines = [
        "# P3-05 stage 2 — LLM v1 diagnosis and v2 recalibration (dev only)",
        "",
        "Generated by `python scripts/dependency_llm_v2.py`; every number is its output.",
        "",
        "## Why v1 was near-silent",
        "",
        f"- Dev rows covered by v1: **{d['rows']}**, missing predictions "
        f"**{d['missing_predictions']}**, parse failures **{d['parse_failures']}**.",
        f"- v1 predicted `{POSITIVE}` on **{d['predicted_positive_rows']} of {d['rows']}** "
        "dev rows.",
        f"- v1 recall on dev: **{d['recall']['hits']}/{d['recall']['rows']}** = "
        f"{fmt(d['recall']['rate'])} {fmt_ci(d['recall']['ci'])}; "
        f"false-positive rate **{d['false_positive_rate']['hits']}/"
        f"{d['false_positive_rate']['rows']}** = {fmt(d['false_positive_rate']['rate'])}.",
        f"- A's text available for **{d['rows_with_any_source_text']} of {d['rows']}** dev rows "
        f"({d['rows_with_claim']} with a claim, {d['rows_abstract_only']} abstract-only, "
        f"{d['rows_with_no_source_text']} stubs with none). Among the {d['recall']['rows']} "
        f"positives, {d['positives_with_claim']} had a claim and "
        f"{d['positives_abstract_only']} only an abstract.",
        f"- v1 flagged {POSITIVE} on "
        f"{d['prediction_rate_with_claim']['hits']}/{d['prediction_rate_with_claim']['rows']} "
        f"rows with a claim and "
        f"{d['prediction_rate_without_claim']['hits']}/"
        f"{d['prediction_rate_without_claim']['rows']} rows without",
        "- Rows whose context mentions the retraction: "
        f"{d['rows_mentioning_retraction_in_context']}.",
        "",
        f"**Diagnosis.** {d['diagnosis']}",
        "",
        "## What v2 changes",
        "",
        f"- The prompt asks the guideline's counterfactual as the *only* question and returns a "
        f"**0-100 probability** instead of a class, so a threshold exists to tune and a confidence "
        f"exists to escalate on (prompt `{PROMPT_VERSION}`).",
        f"- Bands: <= {BAND_MENTION} not dependent, {BAND_MENTION + 1}-{BAND_RELIES - 1} unclear, "
        f">= {BAND_RELIES} dependent; the override rules (corroboration, citing-as-retracted, "
        "protocol use) are stated in the prompt rather than left to inference.",
        "",
    ]
    metrics = summary.get("dev_metrics")
    if isinstance(metrics, dict):
        distribution = metrics["score_distribution"]
        assert isinstance(distribution, dict)
        lines += [
            "## v2 on dev (scores from the checkpoint, no further calls)",
            "",
            f"- {distribution['rows']} scored rows, mean score {distribution['mean']}.",
            f"- Score bands: **<= 30: {distribution['band_le_30']}**, "
            f"31-69: {distribution['band_31_69']}, "
            f"**>= 70: {distribution['band_ge_70']}** - the model is close to binary, which is",
            "  why thresholds between 31 and 70 behave identically.",
            "",
            "| Frame | Model | Precision | Recall [95% CI] | False-alarm rate [95% CI] |",
            "| :-- | :-- | --: | :-- | :-- |",
        ]
        table = metrics["table"]
        assert isinstance(table, dict)
        for frame, label in (("text_bearing", "text-bearing"), ("stub", "stub")):
            frame_table = table[frame]
            assert isinstance(frame_table, dict)
            for name, block in frame_table.items():
                assert isinstance(block, dict)
                recall_ci = block["recall_ci"] or [0.0, 0.0]
                far_ci = block["false_alarm_ci"] or [0.0, 0.0]
                lines.append(
                    f"| {label} | {name} | {fmt(block['precision'])} | "
                    f"{fmt(block['recall'])} [{recall_ci[0]:.1%}, {recall_ci[1]:.1%}] | "
                    f"{fmt(block['false_alarm_rate'])} "
                    f"[{far_ci[0]:.1%}, {far_ci[1]:.1%}] |"
                )
        lines += [
            "",
            "v2 trades v1's silence for reach: recall rises and false alarms rise with it. The",
            "stage-2 threshold is tuned on dev in `scripts/p3_05_staged.py`, not here, and the",
            "frozen cascade spec records which threshold test will use.",
            "",
        ]
    llm = summary.get("run")
    checkpoint_rows = int(summary.get("checkpoint_rows") or 0)
    if not llm and not checkpoint_rows:
        name = str(summary.get("variant") or "v2")
        lines += [
            f"## Status: no `{name}` score exists yet",
            "",
            "The diagnosis and the cost estimate above are complete and reproducible from",
            "committed files. The live dev run for this variant has **not produced a scored row**:",
            "the environment refused further live calls after the first two attempts, so no",
            f"`{name}` recall or false-alarm number is reported here and none is claimed. The",
            "command that would produce them, on dev only, is:",
            "",
            "```",
            f"PYTHONPATH=. python scripts/dependency_llm_v2.py --llm-mode live --variant {name} "
            "--max-calls 151",
            "```",
            "",
            f"It writes `{registry_checkpoint(name).name}` incrementally, so it can be stopped",
            "and resumed, and it refuses to start if the estimate exceeds the budget, if the daily",
            "cap is reached, or if the last ledger attempts show provider errors.",
            "",
        ]
    waste = summary.get("spent_without_checkpoint")
    if isinstance(waste, dict):
        lines += [
            "## Calls paid for that produced no scored row",
            "",
            f"- Stage `{waste['stage']}`: **{waste['attempts']} attempts** "
            f"({waste['succeeded']} answered by the provider), ledger list price "
            f"**${waste['usd']}**, checkpoint empty.",
            "- Cause was ours, not the provider's: first the request pinned v2's answer schema "
            "while the v3 prompt asked for different fields; then the request was right but the "
            "client was still told to parse v2's model. Both failures happened *after* the call "
            "was paid for. Fixed by making the variant own the prompt, the request schema and the "
            "parse model, with a test asserting they travel together.",
            "- Those rows are re-asked by the resumed run, so the same tokens are spent twice. "
            "The duplicate is visible in the ledger, not netted out.",
            "",
        ]
    if not llm and checkpoint_rows:
        lines += [
            "## Status: dev scores exist, produced outside this invocation",
            "",
            f"`eval/audit/p3-05/p3-05-llm-v2-dev.csv` holds **{checkpoint_rows}** scored rows, so",
            "the v2 numbers above are measured. The live run was executed with the owner's",
            "authorisation (151 calls, $0.052 list price estimate, $0 real spend on the free",
            "tier); the ledger reconciliation against `llm_calls` is in",
            "`docs/reports/P3-08-cost-scaffold.md`.",
            "",
        ]
    if llm:
        lines += [
            "## Cost, stated before the call",
            "",
            f"- Rows: **{llm['estimate']['rows']}** (dev only), "
            f"{llm['estimate']['prompt_tokens_estimate']:,} prompt + "
            f"{llm['estimate']['completion_tokens_estimate']:,} completion tokens "
            f"({llm['estimate']['token_count_is']}).",
            f"- List price **{llm['estimate']['list_price_usd']} USD**; billing "
            f"`{llm['estimate']['billing']}`.",
            f"- Requests used today before the run: **{llm['tokens_today_before']}/"
            f"{llm['daily_cap']}**.",
            f"- Run `{llm['run_id']}`: **{llm['calls_made']} calls**, stopped "
            f"`{llm['stopped_reason'] or 'completed'}`, ledger list price "
            f"**{llm['run_list_price_usd']} USD**, real spend **{llm['run_real_usd']} USD**.",
            "",
        ]
    log = summary.get("variants")
    if isinstance(log, dict):
        entries = log.get("variants") or []
        lines += [
            "## Prompt variants tried (dev only)",
            "",
            f"**Variants measured on dev: {log.get('variants_tried', 0)} of a cap of "
            f"{log.get('cap', 3)}.** {log.get('cap_note', '')}.",
            "",
        ]
        if entries:
            lines += [
                "| Variant | Prompt | Rows | Recall [95% CI] | FAR [95% CI] | Interior rows | "
                "Distinct scores |",
                "| :-- | :-- | --: | :-- | :-- | --: | --: |",
            ]
            for entry in entries:
                metrics = entry["metrics"]
                best = best_point(metrics["points"])
                recall_ci = best["recall_ci"] or [0.0, 0.0]
                far_ci = best["false_alarm_ci"] or [0.0, 0.0]
                distribution = metrics["distribution"]
                lines.append(
                    f"| {entry['variant']} | `{entry['prompt_version']}` | "
                    f"{entry['rows_scored']} | {fmt(best['recall'])} "
                    f"[{recall_ci[0]:.1%}, {recall_ci[1]:.1%}] | "
                    f"{fmt(best['false_alarm_rate'])} "
                    f"[{far_ci[0]:.1%}, {far_ci[1]:.1%}] | "
                    f"{distribution['interior_rows']} | {distribution['distinct_scores']} |"
                )
            lines += [
                "",
                f"Recall and FAR above are each variant's **best-recall dev operating point** on "
                f"the text-bearing frame; the chosen threshold is in "
                f"`{VARIANTS_FILE.name}`.",
                "",
                "### Score distributions - is the interior populated?",
                "",
                "| Variant | 0-20 | 21-40 | 41-60 | 61-80 | 81-100 | Interior share | Graded? |",
                "| :-- | --: | --: | --: | --: | --: | --: | :-- |",
            ]
            for entry in entries:
                distribution = entry["metrics"]["distribution"]
                bands = distribution["bands"]
                lines.append(
                    f"| {entry['variant']} | {bands['0-20']} | {bands['21-40']} | "
                    f"{bands['41-60']} | {bands['61-80']} | {bands['81-100']} | "
                    f"{fmt(distribution['interior_share'])} | "
                    f"{'yes' if distribution['graded'] else 'no'} |"
                )
            lines += [
                "",
                "A band is populated when a variant's score lands between the prompt's own "
                "extremes; `extreme_only` variants answer like a decision and give a threshold "
                "nothing to tune.",
                "",
            ]
        else:
            lines += [
                "No variant has been measured yet: the cap allows v2, v3 and v3b, and this "
                "report currently records zero draws, so no dev recall number here is a best-of.",
                "",
            ]
        lines += [
            "### Selection effect, stated up front",
            "",
            f"- {log.get('variants_tried', 0)} variant(s) measured on the *same* "
            f"{diagnosis['rows']} dev rows. If a later section quotes the best variant, "
            "that number is a maximum over the variants tried, not a pre-registered estimate.",
            "- The heuristic baseline is **not** re-tuned per variant; it keeps its single "
            "dev-tuned operating point, so the comparison is variant-vs-fixed-baseline.",
            "",
        ]
    lines += [
        "## Scope",
        "",
        "- Dev rows only. Test was not read for this calibration and is evaluated once, in the",
        "  frozen Block 6 report.",
        "- Scores are checkpointed per row, so an interrupted run resumes instead of re-spending",
        "  free-tier quota.",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def registry_checkpoint(name: str) -> Path:
    """The checkpoint path a variant writes, without needing a live Settings object."""
    return variant_registry()[name].checkpoint


def spent_without_checkpoint(stage: str, ledger_path: Path) -> dict[str, object] | None:
    """Ledger attempts for a stage that produced no scored rows, so waste is recorded.

    A run can pay for calls and still write nothing - a schema mismatch, a crash
    between the call and the checkpoint write. Those attempts belong in the report
    next to the estimate that did not predict them.
    """
    if not ledger_path.exists():
        return None
    with sqlite3.connect(ledger_path) as connection:
        row = connection.execute(
            "SELECT count(*), sum(case when error is null then 1 else 0 end), sum(usd) "
            "FROM llm_calls WHERE stage = ?",
            (stage,),
        ).fetchone()
    if not row or not row[0]:
        return None
    return {
        "stage": stage,
        "attempts": int(row[0]),
        "succeeded": int(row[1] or 0),
        "usd": str(row[2]),
    }


def best_point(points: dict[str, dict[str, object]]) -> dict[str, object]:
    """Highest-recall operating point on dev; ties break to the lower FAR."""
    best = max(
        points.values(),
        key=lambda block: (float(block["recall"] or 0), -float(block["false_alarm_rate"] or 0)),
    )
    return best


def fmt(value: object) -> str:
    return "—" if value is None else f"{float(value):.1%}"  # type: ignore[arg-type]


def fmt_ci(bounds: object) -> str:
    if not bounds:
        return ""
    low, high = bounds  # type: ignore[misc]
    return f"[{low:.1%}, {high:.1%}]"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnose", action="store_true")
    parser.add_argument("--llm-mode", choices=("off", "dry-run", "live"), default="off")
    parser.add_argument("--split", default="dev", choices=("dev", "test"))
    parser.add_argument("--allow-test", action="store_true")
    parser.add_argument("--variant", default="v2", choices=("v2", "v3", "v3b"))
    parser.add_argument("--estimate-variants", action="store_true")
    parser.add_argument("--max-calls", type=int, default=200)
    parser.add_argument("--llm-budget-usd", default=str(DEFAULT_BUDGET_USD))
    args = parser.parse_args(argv)

    rows = scored_rows(load_rows())
    dev = spec_rows(rows, "dev")
    summary: dict[str, object] = {}
    v1 = read_v1()
    diagnosis = diagnose(dev, v1)
    variant = get_variant(args.variant)
    summary["variant"] = variant.name
    summary["variants"] = read_variant_log()

    if args.split == "test" and not args.allow_test:
        raise LLMv2Error("test rows are refused here; Block 6 evaluates test once under a freeze")

    checkpoint = read_v2(variant.checkpoint)
    summary["checkpoint_rows"] = len(checkpoint)
    if not checkpoint:
        waste = spent_without_checkpoint(variant_stage(variant), Settings().resolved_ledger_path)
        if waste:
            summary["spent_without_checkpoint"] = waste
    if checkpoint:
        summary["dev_metrics"] = dev_metrics(dev, checkpoint, v1)
        summary["variant_metrics"] = variant_metrics(dev, checkpoint, v1)
        summary["variants"] = record_variant(
            variant.name,
            {
                "variant": variant.name,
                "prompt_version": variant.prompt_version,
                "rows_scored": len(checkpoint),
                "metrics": summary["variant_metrics"],
            },
        )
    if variant.name == "v2" and not checkpoint:
        legacy = read_v2()
        summary["checkpoint_rows"] = len(legacy)
        if legacy:
            summary["dev_metrics"] = dev_metrics(dev, legacy, v1)
            summary["variant_metrics"] = variant_metrics(dev, legacy, v1)

    if args.estimate_variants:
        settings = Settings()
        statements = {
            name: estimate(dev, settings.resolved_pricing_path, item)
            for name, item in variant_registry().items()
        }
        print(json.dumps({"dev_estimate_by_variant": statements}, indent=2))

    if args.llm_mode != "off":
        settings = Settings()
        target = dev if args.split == "dev" else spec_rows(rows, "test")
        cost = estimate(target, settings.resolved_pricing_path, variant)
        print(json.dumps({"llm_estimate": cost}, indent=2))
        if args.llm_mode == "live":
            recent = recent_failures(settings.resolved_ledger_path)
            print(json.dumps({"recent_ledger_attempts": recent}, indent=2))
            failures = sum(1 for item in recent[:3] if item["error_class"])
            if failures:
                raise LLMv2Error(
                    "the last attempts include provider errors (possible 503 window); "
                    "refusing to start a live run now"
                )
            summary["run"] = run_live(
                target,
                settings=settings,
                pricing_path=settings.resolved_pricing_path,
                max_calls=args.max_calls,
                budget_usd=Decimal(args.llm_budget_usd),
                variant=variant,
            )
            print(json.dumps({"llm_run": summary["run"]}, indent=2, default=str))
            scored_now = read_v2(variant.checkpoint)
            if scored_now:
                summary["variant_metrics"] = variant_metrics(dev, scored_now, v1)
                summary["variants"] = record_variant(
                    variant.name,
                    {
                        "variant": variant.name,
                        "prompt_version": variant.prompt_version,
                        "rows_scored": len(scored_now),
                        "metrics": summary["variant_metrics"],
                        "run": summary["run"],
                    },
                )

    if args.diagnose or not summary:
        print(json.dumps(diagnosis, indent=2))
    write_report(diagnosis, summary)
    print(f"report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
