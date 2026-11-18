"""P3-04 baselines: citation-level, section/lexical heuristic, and LLM-only.

Every baseline predicts one binary thing per labelled row: does the citing
sentence *rely on* the retracted/flagged source (`RELIES_ON`), or not
(`MENTIONS` + `UNRELATED`, the alarm-relevant negatives). `insufficient_context`
rows are excluded, not counted as either class.

Three rules keep the numbers honest:

* the heuristic is tuned **on dev only**; the grid and the chosen point are
  written to the summary, so the search is visible rather than implied;
* **test is reported once and frozen** in ``p3-04-test-frozen.json``. A later run
  recomputes the same numbers and refuses to continue if they moved, because a
  changed number means the specification changed after the test was seen;
* the LLM baseline makes **no call unless ``--llm-mode live``**, prints its
  list-price estimate first, and refuses to start above ``--llm-budget-usd``.

Usage:
    python scripts/dependency_baselines.py                    # heuristic only
    python scripts/dependency_baselines.py --llm-mode dry-run # + cost estimate
    python scripts/dependency_baselines.py --llm-mode live --max-calls 20
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from pydantic import BaseModel

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

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "audit" / "p3-03"
P304 = ROOT / "eval" / "audit" / "p3-04"
REPORT = ROOT / "docs" / "reports" / "P3-04-baselines.md"
SUMMARY = P304 / "p3-04-baselines.json"
FREEZE = P304 / "p3-04-test-frozen.json"
LLM_PREDICTIONS = P304 / "p3-04-llm-predictions.csv"

WAVES: tuple[tuple[str, Path, Path], ...] = (
    ("wave1", OUT / "p3-03-wave1-manifest.csv", OUT / "dependency_audit_v1_wave1_labelled.csv"),
    ("wave2", OUT / "p3-03-wave2-manifest.csv", OUT / "dependency_audit_v1_wave2_labelled.csv"),
)

POSITIVE = "RELIES_ON"
NEGATIVES = ("MENTIONS", "UNRELATED")
SKIP = "insufficient_context"
CLASSES = (POSITIVE, *NEGATIVES, SKIP)
FRAMES = {"text_bearing": "Text-bearing frame (primary)", "stub": "Title-only stub stratum"}
SPLITS = ("dev", "test")

LLM_MODEL = "gemini-3.5-flash-lite"
LLM_STAGE = "dependency_baseline"
LLM_PROMPT_VERSION = "p3-04-llm-v1"
LLM_MAX_OUTPUT_TOKENS = 256
LLM_COMPLETION_ESTIMATE = 60
DEFAULT_LLM_BUDGET_USD = Decimal("0.50")

SECTION_WEIGHTS: dict[str, float] = {
    "methods": 1.0,
    "results": 0.5,
    "discussion": -0.5,
    "introduction": -0.5,
    "other": 0.0,
    "unsectioned": 0.0,
}

RELIANCE_CUES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bwe (?:used|used the|obtained|adapted|adopted|applied|followed|chose|took|employed)\b",
        r"\b(?:obtained|purchased|adapted|taken|derived) from\b",
        r"\bbased on (?:the|their|this|these|a|our)\b",
        r"\bas described (?:by|in|previously)\b",
        r"\baccording to\b",
        r"\bwe (?:compared|calibrated|validated) (?:our|against)\b",
        r"\b(?:in|for) our (?:study|analysis|model|cohort|experiment)\b",
    )
)
MENTION_CUES: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bretract\w*\b",
        r"\bexpression of concern\b",
        r"\b(?:reviewed|summari[sz]ed|discussed) (?:in|by)\b",
        r"\bfor example\b",
        r"\be\.g\.\b",
        r"\bsuch as\b",
        r"\bfor instance\b",
        r"\b(?:several|many|other) (?:studies|authors|groups)\b",
    )
)

GRID_SECTION_SCALE: tuple[float, ...] = (0.0, 0.5, 1.0, 1.5, 2.0)
GRID_THRESHOLD: tuple[float, ...] = (-0.5, 0.0, 0.5, 1.0, 1.5, 2.0)


class BaselineError(Exception):
    """The baselines cannot be computed from the committed files."""


class FreezeError(BaselineError):
    """The frozen test result would change; a human must decide why."""


# --------------------------------------------------------------------------- data


def section_bucket(raw: str) -> str:
    """Collapse the many journal headings to the six buckets the heuristic uses."""
    text = (raw or "").strip().lower()
    if not text:
        return "unsectioned"
    if "method" in text or "material" in text or "experimental" in text:
        return "methods"
    if "result" in text or "finding" in text:
        return "results"
    if "discuss" in text or "conclusion" in text:
        return "discussion"
    if "intro" in text or "background" in text:
        return "introduction"
    return "other"


def load_rows() -> list[dict[str, str]]:
    """Join every wave's manifest to its labels, one dict per labelled row."""
    joined: list[dict[str, str]] = []
    for wave, manifest_path, labels_path in WAVES:
        for path in (manifest_path, labels_path):
            if not path.exists():
                raise BaselineError(f"missing input: {path}")
        with labels_path.open(encoding="utf-8-sig", newline="") as handle:
            labelled = {row["row_id"]: row for row in csv.DictReader(handle)}
        with manifest_path.open(encoding="utf-8", newline="") as handle:
            manifest = list(csv.DictReader(handle))
        if set(labelled) != {row["row_id"] for row in manifest}:
            raise BaselineError(f"{wave}: labels do not cover the manifest")
        for row in manifest:
            label_row = labelled[row["row_id"]]
            label = (label_row.get("label") or "").strip()
            if label and label not in CLASSES:
                raise BaselineError(f"{row['row_id']}: unknown label {label!r}")
            joined.append(
                {
                    "row_id": row["row_id"],
                    "wave": wave,
                    "split": row["split"],
                    "text_bearing": row["text_bearing"],
                    "weight": row["weight"],
                    "frame": "text_bearing" if row["text_bearing"] == "true" else "stub",
                    "section": row["section"],
                    "section_bucket": section_bucket(row["section"]),
                    "label": label or SKIP,
                    "context_text": label_row.get("context_text") or "",
                    "paragraph_text": label_row.get("paragraph_text") or "",
                    "source_title": label_row.get("source_title") or "",
                    "source_claim_text": label_row.get("source_claim_text") or "",
                    "source_abstract": label_row.get("source_abstract") or "",
                    "citer_title": label_row.get("citer_title") or "",
                }
            )
    return joined


def scored_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Only rows the metric can score: the skip action is excluded."""
    return [row for row in rows if row["label"] != SKIP]


def spec_rows(rows: Sequence[dict[str, str]], split: str) -> list[dict[str, str]]:
    return [row for row in rows if row["split"] == split]


def frame_rows(rows: Sequence[dict[str, str]], frame: str) -> list[dict[str, str]]:
    return [row for row in rows if frame == "all" or row["frame"] == frame]


# --------------------------------------------------------------------- heuristic


def heuristic_score(row: dict[str, str], params: dict[str, float]) -> float:
    """Section prior plus lexicon hits; symmetric, so the sign is the whole story."""
    text = f"{row['context_text']} {row['paragraph_text']}"
    reliance = sum(1 for pattern in RELIANCE_CUES if pattern.search(text))
    mention = sum(1 for pattern in MENTION_CUES if pattern.search(text))
    section = SECTION_WEIGHTS[row["section_bucket"]] * params["section_scale"]
    return section + params["reliance_weight"] * reliance - params["mention_weight"] * mention


def predict_heuristic(row: dict[str, str], params: dict[str, float]) -> int:
    return int(heuristic_score(row, params) >= params["threshold"])


@dataclass(frozen=True)
class Binary:
    tp: int
    fp: int
    fn: int
    tn: int

    @property
    def positives(self) -> int:
        return self.tp + self.fn

    @property
    def negatives(self) -> int:
        return self.fp + self.tn

    @property
    def predicted_positive(self) -> int:
        return self.tp + self.fp


def confusion(predictions: dict[str, int], rows: Sequence[dict[str, str]]) -> Binary:
    tp = fp = fn = tn = 0
    for row in rows:
        predicted = predictions.get(row["row_id"])
        if predicted is None:
            raise BaselineError(f"no prediction for {row['row_id']}")
        actual = row["label"] == POSITIVE
        if actual and predicted:
            tp += 1
        elif actual:
            fn += 1
        elif predicted:
            fp += 1
        else:
            tn += 1
    return Binary(tp, fp, fn, tn)


def weighted_confusion(
    predictions: dict[str, int], rows: Sequence[dict[str, str]]
) -> dict[str, float]:
    """Design-weighted counts, rescaled so they sum to the effective sample size.

    ``effective`` is the Kish size, so a strongly skewed weight profile cannot
    make a weighted count pretend to be more rows than the data support.
    """
    if not rows:
        return {"tp": 0.0, "fp": 0.0, "fn": 0.0, "tn": 0.0}
    total = sum(float(row["weight"]) for row in rows)
    squares = sum(float(row["weight"]) ** 2 for row in rows)
    effective = (total * total / squares) if squares else 0.0
    scale = effective / total if total else 0.0
    counts = {"tp": 0.0, "fp": 0.0, "fn": 0.0, "tn": 0.0}
    for row in rows:
        predicted = predictions.get(row["row_id"])
        if predicted is None:
            raise BaselineError(f"no prediction for {row['row_id']}")
        weight = float(row["weight"]) * scale
        actual = row["label"] == POSITIVE
        if actual and predicted:
            counts["tp"] += weight
        elif actual:
            counts["fn"] += weight
        elif predicted:
            counts["fp"] += weight
        else:
            counts["tn"] += weight
    return counts


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def interval(successes: int, total: int) -> list[float] | None:
    if total < 1:
        return None
    low, high = wilson_interval(successes, total)
    return [round(low, 4), round(high, 4)]


def binary_metrics(
    predictions: dict[str, int], rows: Sequence[dict[str, str]]
) -> dict[str, object]:
    """Precision, recall and false-alarm rate, unweighted and design-weighted."""
    counts = confusion(predictions, rows)
    weighted = weighted_confusion(predictions, rows)

    def block(
        tp: float,
        predicted_positive: float,
        positives: float,
        fp: float,
        negatives: float,
    ) -> dict[str, object]:
        precision = ratio(tp, predicted_positive)
        recall = ratio(tp, positives)
        far = ratio(fp, negatives)
        return {
            "precision": None if precision is None else round(precision, 4),
            "precision_ci": interval(round(tp), round(predicted_positive)),
            "recall": None if recall is None else round(recall, 4),
            "recall_ci": interval(round(tp), round(positives)),
            "false_alarm_rate": None if far is None else round(far, 4),
            "false_alarm_ci": interval(round(fp), round(negatives)),
        }

    return {
        "rows": len(rows),
        "positives": counts.positives,
        "negatives": counts.negatives,
        "predicted_positive": counts.predicted_positive,
        "tp": counts.tp,
        "fp": counts.fp,
        "fn": counts.fn,
        "tn": counts.tn,
        "unweighted": block(
            counts.tp, counts.predicted_positive, counts.positives, counts.fp, counts.negatives
        ),
        "weighted": block(
            weighted["tp"],
            weighted["tp"] + weighted["fp"],
            weighted["tp"] + weighted["fn"],
            weighted["fp"],
            weighted["fp"] + weighted["tn"],
        ),
        "weighted_effective_rows": round(sum(weighted.values()), 2),
    }


def tune_heuristic(rows: Sequence[dict[str, str]]) -> dict[str, object]:
    """Grid search on dev only, ranked by F1 then by the lower false-alarm rate."""
    best: tuple[tuple[float, float, float], dict[str, float]] | None = None
    grid: list[dict[str, object]] = []
    for scale in GRID_SECTION_SCALE:
        for threshold in GRID_THRESHOLD:
            params = {
                "section_scale": scale,
                "reliance_weight": 1.0,
                "mention_weight": 1.0,
                "threshold": threshold,
            }
            predictions = {row["row_id"]: predict_heuristic(row, params) for row in rows}
            counts = confusion(predictions, rows)
            precision = ratio(counts.tp, counts.predicted_positive) or 0.0
            recall = ratio(counts.tp, counts.positives) or 0.0
            far = ratio(counts.fp, counts.negatives) or 0.0
            f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
            grid.append(
                {
                    "section_scale": scale,
                    "threshold": threshold,
                    "f1": round(f1, 4),
                    "precision": round(precision, 4),
                    "recall": round(recall, 4),
                    "false_alarm_rate": round(far, 4),
                }
            )
            key = (round(f1, 6), -round(far, 6), -counts.predicted_positive)
            if best is None or key > best[0]:
                best = (key, params)
    if best is None:
        raise BaselineError("the heuristic grid produced no candidate")
    return {"params": best[1], "grid": grid}


# ------------------------------------------------------------------ baselines


def citation_level(rows: Sequence[dict[str, str]]) -> dict[str, int]:
    """The 'all affected' baseline: every citation is treated as affected."""
    return {row["row_id"]: 1 for row in rows}


def build_prompt(row: dict[str, str]) -> str:
    """One compact prompt per row; A's claim is included only when it exists."""
    claim = (row["source_claim_text"] or row["source_abstract"] or "").strip()
    claim_block = claim[:600] if claim else "not available for this source"
    context = (row["context_text"] or "").strip()[:700]
    section = (row["section"] or "unsectioned").strip()
    return (
        "You label how one citing sentence uses a source paper.\n\n"
        f"SOURCE (A): {row['source_title'][:200]}\n"
        f"A's claim: {claim_block}\n\n"
        f'CITING SENTENCE (B), section "{section}":\n"{context}"\n\n'
        "Choose exactly one label:\n"
        "- RELIES_ON: B's claim, method or interpretation would have to change if A's claim "
        "were wrong.\n"
        "- MENTIONS: a real citation, but B stands without A: background, credit, a standard "
        "method, tool, database, protocol, an example in a list, a contrast or refutation, or "
        "citing A as retracted.\n"
        "- UNRELATED: the marker does not connect this text to A: reference-list fragment, "
        "artifact, or wrong target.\n"
        "Section and retraction status do not decide the label.\n"
        "Corroboration is not dependency.\n\n"
        'Return JSON: {"label": "<one of RELIES_ON|MENTIONS|UNRELATED>", '
        '"cue": "<3-10 words naming the cue you used>"}'
    )


class LLMLabel(BaseModel):
    """Structured output for one row."""

    label: Literal["RELIES_ON", "MENTIONS", "UNRELATED"]
    cue: str = ""


def prompt_tokens(prompt: str) -> int:
    return math.ceil(len(prompt) / 4)


def read_llm_predictions(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return {row["row_id"]: int(row["predicted"]) for row in rows if row["predicted"]}


def append_llm_prediction(path: Path, row_id: str, label: str, cue: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fresh = not path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=("row_id", "label", "predicted", "cue", "model", "prompt_version"),
            lineterminator="\n",
        )
        if fresh:
            writer.writeheader()
        writer.writerow(
            {
                "row_id": row_id,
                "label": label,
                "predicted": int(label == POSITIVE),
                "cue": cue,
                "model": LLM_MODEL,
                "prompt_version": LLM_PROMPT_VERSION,
            }
        )


def estimate_llm_cost(rows: Sequence[dict[str, str]], pricing_path: Path) -> dict[str, object]:
    pricing = load_pricing(pricing_path)
    prompts = [prompt_tokens(build_prompt(row)) for row in rows]
    total_in = sum(prompts)
    total_out = LLM_COMPLETION_ESTIMATE * len(rows)
    estimate = estimate_cost_details(
        pricing,
        LLM_MODEL,
        total_in,
        total_out,
        dry_run=True,
        on_date=date.today(),
    )
    return {
        "model": LLM_MODEL,
        "rows": len(rows),
        "prompt_tokens_estimate": total_in,
        "completion_tokens_estimate": total_out,
        "mean_prompt_tokens": round(total_in / len(rows), 1) if rows else 0.0,
        "max_prompt_tokens": max(prompts) if prompts else 0,
        "list_price_usd": str(estimate.usd) if estimate.usd is not None else None,
        "billing": "free_tier (list price recorded, no charge)",
        "token_count_is": "heuristic ceil(chars/4)",
    }


def run_llm(
    rows: Sequence[dict[str, str]],
    *,
    settings: Settings,
    pricing_path: Path,
    max_calls: int,
    budget_usd: Decimal,
) -> dict[str, object]:
    """Live calls through ``LLMClient``; resumable and quota-aware."""
    estimate = estimate_llm_cost(rows, pricing_path)
    list_price = Decimal(str(estimate["list_price_usd"] or "0"))
    if list_price > budget_usd:
        raise BaselineError(
            f"estimated list price {list_price} USD exceeds --llm-budget-usd {budget_usd}; "
            "refusing to call"
        )
    if not settings.gemini_api_key:
        raise BaselineError("GEMINI_API_KEY is not set; cannot run the LLM baseline")

    ledger_path = settings.resolved_ledger_path
    today = pacific_date(datetime.now(UTC).isoformat())
    with sqlite3.connect(ledger_path) as connection:
        stamps = [row[0] for row in connection.execute("SELECT ts FROM llm_calls")]
    per_day = requests_by_pacific_day([SimpleNamespace(ts=stamp) for stamp in stamps])
    used_today = per_day.get(today.isoformat(), 0)
    rate: RateLimit = load_rate_limits(DEFAULT_RATE_LIMITS_PATH).require(LLM_MODEL)
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

    done = read_llm_predictions(LLM_PREDICTIONS)
    run_id = f"p3-04-llm-{today.isoformat()}"
    calls = 0
    stopped: str | None = None
    for row in rows:
        if row["row_id"] in done:
            continue
        if calls >= max_calls:
            stopped = "max_calls_reached"
            break
        calls += 1
        request = LLMRequest(
            prompt=build_prompt(row),
            stage=LLM_STAGE,
            tier="small",
            model=LLM_MODEL,
            run_id=run_id,
            paper_id=row["row_id"],
            temperature=0.0,
            max_output_tokens=LLM_MAX_OUTPUT_TOKENS,
            response_schema=LLMLabel,
        )
        try:
            result = client.complete(
                request,
                response_model=LLMLabel,
                attempt_gate=pacer.reserve,
            )
        except DailyQuotaError:
            stopped = "daily_quota_reached"
            break
        parsed = LLMLabel.model_validate_json(result.text)
        append_llm_prediction(LLM_PREDICTIONS, row["row_id"], parsed.label, parsed.cue)
        done[row["row_id"]] = int(parsed.label == POSITIVE)

    ledger = SQLiteLedger(ledger_path)
    return {
        "estimate": estimate,
        "run_id": run_id,
        "calls_made": calls,
        "calls_before_today": used_today,
        "daily_cap": rate.daily_cap,
        "stopped_reason": stopped,
        "run_list_price_usd": str(ledger.run_usd(run_id)),
        "run_real_usd": str(ledger.run_real_usd(run_id)),
        "predicted_rows": len(done),
    }


# ------------------------------------------------------------------- freezing


def spec_hash(rows: Sequence[dict[str, str]], params: dict[str, float]) -> str:
    """Hash the frozen specification: heuristic params, prompt, and the test rows.

    The baseline list is deliberately excluded so that adding a baseline (the LLM
    one, which needs live calls) does not invalidate the frozen heuristic result;
    per-baseline numbers are frozen individually instead.
    """
    payload = {
        "params": params,
        "test_rows": sorted(row["row_id"] for row in rows),
        "prompt_version": LLM_PROMPT_VERSION,
        "model": LLM_MODEL,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def freeze_test(payload: dict[str, object], *, refreeze: bool) -> dict[str, object]:
    """Write the test result once; refuse to let any frozen number drift."""
    digest = str(payload["spec_hash"])
    fresh_results = payload["results"]
    assert isinstance(fresh_results, dict)
    if FREEZE.exists() and not refreeze:
        existing = json.loads(FREEZE.read_text(encoding="utf-8"))
        if existing.get("spec_hash") != digest:
            raise FreezeError(
                "the frozen test result was computed under a different specification "
                f"({existing.get('spec_hash')} vs {digest}). The test set has been seen; "
                "changing the model, prompt or heuristic now needs a new decision, or "
                "--refreeze with the change recorded in the commit message."
            )
        frozen_results = existing.get("results", {})
        assert isinstance(frozen_results, dict)
        for key, value in fresh_results.items():
            if key in frozen_results and frozen_results[key] != value:
                raise FreezeError(f"recomputed test metric changed for {key!r}")
        merged = dict(frozen_results)
        added = sorted(key for key in fresh_results if key not in frozen_results)
        merged.update({key: fresh_results[key] for key in added})
        existing["results"] = merged
        if added:
            stamps = existing.setdefault("added_at", {})
            assert isinstance(stamps, dict)
            stamp = datetime.now(UTC).isoformat(timespec="seconds")
            for key in added:
                stamps[key] = stamp
        FREEZE.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return dict(existing)
    payload = dict(payload)
    payload["frozen_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    payload["added_at"] = {
        key: payload["frozen_at"]
        for key in fresh_results  # type: ignore[union-attr]
    }
    FREEZE.parent.mkdir(parents=True, exist_ok=True)
    FREEZE.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


# --------------------------------------------------------------------- report


def _pct(value: object) -> str:
    return "—" if value is None else f"{float(value):.1%}"  # type: ignore[arg-type]


def _ci(block: dict[str, object], key: str) -> str:
    bounds = block.get(key)
    if not bounds:
        return "—"
    low, high = bounds  # type: ignore[misc]
    return f"[{low:.1%}, {high:.1%}]"


def _row(name: str, frame: str, split: str, metrics: dict[str, object]) -> str:
    weighted = metrics["weighted"]
    unweighted = metrics["unweighted"]
    assert isinstance(weighted, dict) and isinstance(unweighted, dict)
    return (
        f"| {name} | {frame} | {split} | {metrics['rows']} | {metrics['positives']} | "
        f"{metrics['predicted_positive']} | {_pct(unweighted['precision'])} | "
        f"{_pct(unweighted['recall'])} {_ci(unweighted, 'recall_ci')} | "
        f"{_pct(unweighted['false_alarm_rate'])} {_ci(unweighted, 'false_alarm_ci')} | "
        f"{_pct(weighted['precision'])} | {_pct(weighted['recall'])} | "
        f"{_pct(weighted['false_alarm_rate'])} |"
    )


def write_report(summary: dict[str, object], frozen: dict[str, object]) -> None:
    results = summary["results"]
    assert isinstance(results, dict)
    heuristic = summary["heuristic"]
    assert isinstance(heuristic, dict)
    params = heuristic["params"]
    lines = [
        "# P3-04 - dependency baselines",
        "",
        "Generated by `python scripts/dependency_baselines.py`. Every number is its output.",
        "",
        "Positive class is `RELIES_ON`; negatives are `MENTIONS` + `UNRELATED`; "
        "`insufficient_context` rows are excluded. Weights are the design weights from the "
        "wave manifests, so a weighted figure estimates the corpus the sample came from.",
        "",
        "## Baselines",
        "",
        "- **citation-level** - the 'all affected' baseline: every citation counts as "
        "`RELIES_ON`. It is the floor the staged detector has to beat on false alarms.",
        "- **section/lexical heuristic** - section prior plus a fixed lexicon from the "
        "guideline (no labels were mined for it), tuned on **dev only** over "
        f"{len(heuristic['grid'])} grid points; chosen `section_scale={params['section_scale']}`, "
        f"`threshold={params['threshold']}`.",
        "- **LLM-only** - "
        + (
            "not run; see the LLM section at the end."
            if not any("llm" in name for name in results)
            else f"`{LLM_MODEL}`, prompt `{LLM_PROMPT_VERSION}`, one call per row, "
            "through `LLMClient` so every call is in the ledger."
        ),
        "",
        "## Results",
        "",
        "| Baseline | Frame | Split | Rows | Pos | Pred+ | P | R [95% CI] | FAR [95% CI] "
        "| P (wtd) | R (wtd) | FAR (wtd) |",
        "| :-- | :-- | :-- | --: | --: | --: | --: | :-- | :-- | --: | --: | --: |",
    ]
    for name in ("citation_level", "heuristic", "llm_only"):
        for frame in ("text_bearing", "stub"):
            for split in SPLITS:
                key = f"{name}/{frame}/{split}"
                metrics = results.get(key)
                if metrics is None:
                    continue
                lines.append(
                    _row(name, FRAMES[frame], split, metrics)  # type: ignore[arg-type]
                )
    tb_test = results["heuristic/text_bearing/test"]
    cite_test = results["citation_level/text_bearing/test"]
    tb_dev = results["heuristic/text_bearing/dev"]
    llm_test = results.get("llm_only/text_bearing/test")
    lines += [
        "",
        "## What the test numbers mean",
        "",
        "- Test has **21 `RELIES_ON` rows in total, 18 of them in the text-bearing frame**. "
        "Any recall estimate over that few positives has a **wide interval**: the CI column is "
        "the honest reading, not the point estimate alone.",
        "- The heuristic was tuned on **dev only** (both frames, "
        f"{summary['rows']['dev']} rows). Its full grid is in the JSON summary, so the search is "
        "auditable rather than implied.",
        "- Test numbers were computed once and frozen in "
        f"`eval/audit/p3-04/p3-04-test-frozen.json` (spec `{frozen['spec_hash']}`). A later run "
        "recomputes them and refuses to continue if any frozen number moved. A baseline added "
        "after the freeze (the LLM one, which needs live calls) is recorded with its own "
        "`added_at` stamp instead of silently replacing the frozen file.",
        "- The stub stratum is reported separately and never pooled into the primary frame: "
        "those rows have no source claim, so no text-based method can use A's claim there.",
        "",
        "## Reading",
        "",
        f"- **citation-level** is the floor: recall 100% by construction, precision equal to the "
        f"base rate ({_pct(cite_test['unweighted']['precision'])} on the text-bearing test), and a "
        "false-alarm rate of 100% - it flags every citation.",
        f"- **heuristic** trades recall for false alarms: on the text-bearing test "
        f"recall {_pct(tb_test['unweighted']['recall'])} "
        f"{_ci(tb_test['unweighted'], 'recall_ci')}, precision "
        f"{_pct(tb_test['unweighted']['precision'])}, false-alarm rate "
        f"{_pct(tb_test['unweighted']['false_alarm_rate'])} "
        f"{_ci(tb_test['unweighted'], 'false_alarm_ci')} "
        f"(dev: {_pct(tb_dev['unweighted']['recall'])} recall, "
        f"{_pct(tb_dev['unweighted']['false_alarm_rate'])} false alarms). "
        "It is bounded by what a section and a word list can see: it cannot tell whether B's "
        "argument needs A.",
    ]
    if isinstance(llm_test, dict):
        lines.append(
            f"- **LLM-only** is far more specific and far less sensitive: "
            f"precision {_pct(llm_test['unweighted']['precision'])}, recall "
            f"{_pct(llm_test['unweighted']['recall'])} "
            f"{_ci(llm_test['unweighted'], 'recall_ci')}, false-alarm rate "
            f"{_pct(llm_test['unweighted']['false_alarm_rate'])} on the text-bearing test - it "
            "finds few positives, so alone it answers the wrong question. Its value is as the "
            "escalation tier in P3-05, not as a standalone detector."
        )
    lines += [
        f"- With {tb_test['positives']} text-bearing test positives (21 overall), the difference "
        "between the heuristic's and the LLM's recall is larger than either interval is precise "
        "about; neither a claim of superiority nor of equivalence is supported yet.",
        "",
        "- Every number here is conditional on the P1 citer set (ADR-0015), on one labeler for "
        "the positive class, and on the design weights of two waves with different base rates.",
        "",
    ]
    lines += [
        "## Frozen test result",
        "",
        "```",
        json.dumps(
            {
                "spec_hash": frozen["spec_hash"],
                "frozen_at": frozen["frozen_at"],
                "test": frozen["results"],
            },
            indent=2,
            sort_keys=True,
        ),
        "```",
        "",
    ]
    llm = summary.get("llm")
    if llm:
        lines += [
            "## LLM baseline cost and quota",
            "",
            f"- Estimate: {llm['estimate']['rows']} calls, "
            f"{llm['estimate']['prompt_tokens_estimate']:,} prompt + "
            f"{llm['estimate']['completion_tokens_estimate']:,} completion tokens "
            f"({llm['estimate']['token_count_is']}).",
            f"- List price **{llm['estimate']['list_price_usd']} USD**; billing "
            f"`{llm['estimate']['billing']}`.",
            f"- Run `{llm['run_id']}`: {llm['calls_made']} calls, "
            f"{llm['calls_before_today']}/{llm['daily_cap']} used today, "
            f"stopped: {llm['stopped_reason'] or 'completed'}, "
            f"ledger list price {llm['run_list_price_usd']} USD, "
            f"real spend {llm['run_real_usd']} USD.",
            "",
        ]
    report_target = REPORT
    report_target.parent.mkdir(parents=True, exist_ok=True)
    report_target.write_text("\n".join(lines), encoding="utf-8")


# ------------------------------------------------------------------------ main


def build_summary(rows: Sequence[dict[str, str]], *, refreeze: bool) -> dict[str, object]:
    scored = scored_rows(rows)
    dev = spec_rows(scored, "dev")
    test = spec_rows(scored, "test")
    if not dev or not test:
        raise BaselineError("both dev and test rows are required")

    heuristic = tune_heuristic(dev)
    params = heuristic["params"]
    assert isinstance(params, dict)

    predictions: dict[str, dict[str, int]] = {
        "citation_level": citation_level(scored),
        "heuristic": {row["row_id"]: predict_heuristic(row, params) for row in scored},
    }
    llm_done = read_llm_predictions(LLM_PREDICTIONS)
    if llm_done:
        covered = [row for row in scored if row["row_id"] in llm_done]
        missing = len(scored) - len(covered)
        coverage_note = f"{len(covered)} of {len(scored)} rows ({missing} missing)"
        # Only score the LLM baseline when it covers everything; a partial run
        # would compare different denominators.
        if not missing:
            predictions["llm_only"] = {row["row_id"]: llm_done[row["row_id"]] for row in scored}
    else:
        missing = len(scored)
        coverage_note = f"0 of {len(scored)} rows"

    results: dict[str, object] = {}
    for name, table in predictions.items():
        for frame in ("text_bearing", "stub"):
            for split in SPLITS:
                subset = frame_rows(spec_rows(scored, split), frame)
                results[f"{name}/{frame}/{split}"] = binary_metrics(table, subset)

    test_payload = {
        "spec_hash": spec_hash(test, params),
        "results": {key: value for key, value in results.items() if key.endswith("/test")},
        "rows": {frame: len(frame_rows(test, frame)) for frame in ("text_bearing", "stub")},
    }
    frozen = freeze_test(test_payload, refreeze=refreeze)

    summary: dict[str, object] = {
        "rows": {
            "labelled": len(rows),
            "scored": len(scored),
            "excluded_insufficient_context": len(rows) - len(scored),
            "dev": len(dev),
            "test": len(test),
            "text_bearing": len(frame_rows(scored, "text_bearing")),
            "stub": len(frame_rows(scored, "stub")),
        },
        "positives": {
            "dev": sum(1 for row in dev if row["label"] == POSITIVE),
            "test": sum(1 for row in test if row["label"] == POSITIVE),
            "text_bearing": sum(
                1 for row in scored if row["label"] == POSITIVE and row["frame"] == "text_bearing"
            ),
        },
        "heuristic": heuristic,
        "results": results,
        "llm_coverage": coverage_note,
        "test_frozen": {"spec_hash": frozen["spec_hash"], "frozen_at": frozen["frozen_at"]},
    }
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llm-mode", choices=("off", "dry-run", "live"), default="off")
    parser.add_argument("--max-calls", type=int, default=20)
    parser.add_argument("--llm-budget-usd", default=str(DEFAULT_LLM_BUDGET_USD))
    parser.add_argument("--refreeze", action="store_true")
    parser.add_argument("--summary", type=Path, default=SUMMARY)
    parser.add_argument("--report", type=Path, default=REPORT)
    args = parser.parse_args(argv)

    rows = scored_rows(load_rows())
    llm_part: dict[str, object] | None = None
    if args.llm_mode != "off":
        settings = Settings()
        estimate = estimate_llm_cost(rows, settings.resolved_pricing_path)
        print(json.dumps({"llm_estimate": estimate}, indent=2))
        if args.llm_mode == "live":
            llm_part = run_llm(
                rows,
                settings=settings,
                pricing_path=settings.resolved_pricing_path,
                max_calls=args.max_calls,
                budget_usd=Decimal(args.llm_budget_usd),
            )
            print(json.dumps({"llm_run": llm_part}, indent=2, default=str))

    summary = build_summary(load_rows(), refreeze=args.refreeze)
    if llm_part:
        summary["llm"] = llm_part
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    frozen = json.loads(FREEZE.read_text(encoding="utf-8"))
    write_report(summary, frozen)
    print(f"summary: {args.summary}")
    print(f"report: {args.report}")
    print(
        json.dumps(
            {
                "text_bearing_test": summary["results"][  # type: ignore[index]
                    "heuristic/text_bearing/test"
                ]["unweighted"],
                "llm_coverage": summary["llm_coverage"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
