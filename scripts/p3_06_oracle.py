"""P3-06 oracle: does a *correct* source sentence help the detector?

The oracle test, planned but not run. Once the owner's labels exist, this replaces the
abstract-sentence proxy with the sentence the owner says the citation actually depends
on and re-runs the frozen v3 detector on the same 30 dev rows.

Three modes, and the default is the one that calls nothing:

``--mode estimate``   no labels needed. Projects the cost of the treatment arm from the
                      candidate sentences that are actually in the packet (shortest,
                      median and longest), so the owner sees the price before deciding.
``--mode dry-run``    needs labels. Builds every real prompt, counts tokens, prints the
                      exact cost. Calls nothing.
``--mode live``       needs labels. Sends the requests through ``LLMClient`` so they land
                      in the cost ledger, then compares per row against the stored v3
                      score and the heuristic.

Pre-registered reading (ADR-0027): positives caught before vs after as raw counts out of
14, the *direction* of the false-alarm rate on the negatives, and the statement that 30
rows can show a direction and not an effect size.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from axion.config.pricing import estimate_cost_details, load_pricing
from axion.config.settings import DEFAULT_RATE_LIMITS_PATH, Settings
from axion.llm.client import LLMClient, RetryPolicy
from axion.llm.errors import LLMError
from axion.llm.gemini import GeminiAdapter
from axion.llm.pacing import RateLimit, RequestPacer, load_rate_limits
from axion.llm.providers import ProviderRegistry
from scripts.dependency_baselines import (
    POSITIVE,
    heuristic_score,
    load_rows,
    scored_rows,
    spec_rows,
    tune_heuristic,
)
from scripts.dependency_llm_v2 import (
    MODEL,
    Variant,
    build_request,
    failures_path_for,
    get_variant,
    ledger_activity,
    prompt_tokens,
    read_failures,
    read_v2,
    recent_failures,
    score_rows,
    todays_attempts,
)

ROOT = Path(__file__).resolve().parents[1]
ORACLE_DIR = ROOT / "eval" / "audit" / "p3-06-oracle"
MANIFEST = ORACLE_DIR / "p3-06-oracle-manifest.csv"
BLIND = ORACLE_DIR / "p3-06-oracle-blind.csv"
LABELS = ORACLE_DIR / "p3-06-oracle-labelled.csv"
V3_SCORES = ROOT / "eval" / "audit" / "p3-05" / "p3-05-llm-v3-dev.csv"
CHECKPOINT = ORACLE_DIR / "p3-06-oracle-v3.csv"
SUMMARY = ORACLE_DIR / "p3-06-oracle-result.json"
REPORT = ROOT / "docs" / "reports" / "P3-06-oracle-result.md"
PRICING = ROOT / "src" / "axion" / "config" / "pricing.yaml"
LEDGER = ROOT / "data" / "ledger.sqlite3"

DAILY_REQUEST_CAP = 450  # gemini-3.5-flash-lite free-tier runner cap (rate_limits.yaml)
STAGE = "dependency_llm_oracle"
POSITIVES = 14
NEGATIVES = 16
THRESHOLD = 30  # v3's dev operating point: 50% recall at 12.2% FAR
COMPLETION_TOKENS_ESTIMATE = 120  # v3 answered with three short fields; 149 rows gave 78.7 mean


class OracleError(Exception):
    """The oracle cannot run as specified."""


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise OracleError(f"missing file: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_packet() -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]]]:
    manifest = {row["opaque_id"]: row for row in read_csv(MANIFEST)}
    blind = {row["opaque_id"]: row for row in read_csv(BLIND)}
    missing = set(manifest) - set(blind)
    if missing:
        raise OracleError(f"manifest rows with no blind row: {sorted(missing)}")
    return manifest, blind


# The packet came back labelled in a form that writes `chosen_candidate` and
# `decision_cue` rather than the page's `selected` and `note`. Both are the owner's
# answers, so both are read; which columns a file uses is recorded, never guessed.
SELECTION_COLUMNS = ("selected", "chosen_candidate")
NONE_MARKERS = ("", "0", "none", "-")


def interpret(row: dict[str, str]) -> tuple[list[str], bool]:
    """Read one label row, whoever wrote it: (sentence numbers as text, said none).

    ``0`` is the "none" answer, confirmed against the eight rows that carry it: two of
    them have no candidates at all, so nothing else it could mean exists.
    """
    column = next((name for name in SELECTION_COLUMNS if name in row), None)
    if column is None:
        raise OracleError(
            f"{row.get('opaque_id', '?')} has no selection column; expected one of "
            f"{SELECTION_COLUMNS}"
        )
    raw = (row.get(column) or "").strip()
    explicit_none = (row.get("none") or "").strip().lower() == "true"
    if explicit_none and raw.lower() not in NONE_MARKERS:
        raise OracleError(f"{row['opaque_id']} says none and also names sentences")
    if raw.lower() in NONE_MARKERS:
        if raw and raw.lower() != "none":
            # "0" and "-" are unambiguous: the packet's numbering starts at 1.
            return [], True
        cue = (row.get("note") or row.get("decision_cue") or "").strip().lower()
        if explicit_none or cue.startswith("none"):
            return [], True
        # An empty cell is not an answer. Only an explicit none, an explicit 0 or a cue
        # that says none counts, so a half-finished export cannot pass as 30 decisions.
        raise OracleError(f"{row['opaque_id']} neither names a sentence nor says none")
    return [part for part in raw.replace(",", ";").split(";") if part.strip()], False


def read_labels(path: Path = LABELS) -> list[dict[str, str]]:
    """The owner's export, validated strictly: nothing is imputed and nothing is dropped."""
    if not path.exists():
        raise OracleError(
            f"no labels yet at {path}. Label the packet, export the CSV from the labeler and "
            "save it there; this script refuses to invent a chosen sentence."
        )
    labels = read_csv(path)
    if not labels:
        raise OracleError(f"{path} is empty")
    seen: set[str] = set()
    for row in labels:
        opaque = (row.get("opaque_id") or "").strip()
        if not opaque:
            raise OracleError(f"{path} has a row with no opaque_id")
        if opaque in seen:
            raise OracleError(f"{path} labels {opaque} twice")
        seen.add(opaque)
        if not (row.get("labeler") or "").strip():
            raise OracleError(f"{opaque} has no labeler id; the export is anonymous")
        numbers, said_none = interpret(row)
        if said_none and numbers:
            raise OracleError(f"{opaque} says none and also names sentences")
        if not numbers and not said_none:
            raise OracleError(f"{opaque} neither names a sentence nor says none")
    return labels


def label_columns(path: Path = LABELS) -> list[str]:
    """The columns the label file actually uses, so a report can say where it came from."""
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return next(csv.reader(handle), [])


def parse_choice(row: dict[str, str], candidates: Sequence[str]) -> list[int]:
    """Turn '3;7' into zero-based indexes, refusing anything out of range."""
    chosen, _ = interpret(row)
    indexes: list[int] = []
    for part in chosen:
        if not part.strip().isdigit():
            raise OracleError(
                f"{row['opaque_id']} selects {part!r}, which is not a sentence number"
            )
        index = int(part) - 1
        if index < 0 or index >= len(candidates):
            raise OracleError(
                f"{row['opaque_id']} selects sentence {part}, but only {len(candidates)} were shown"
            )
        indexes.append(index)
    return sorted(set(indexes))


def oracle_arm(
    manifest: dict[str, dict[str, str]],
    blind: dict[str, dict[str, str]],
    labels: Sequence[dict[str, str]],
) -> dict[str, object]:
    """Split the packet into the treatment arm, the 'none' rows, and the untestable rows."""
    unknown = sorted({row["opaque_id"] for row in labels} - set(manifest))
    if unknown:
        raise OracleError(f"labels name rows that are not in this packet: {unknown}")
    missing = sorted(set(manifest) - {row["opaque_id"] for row in labels})
    if missing:
        raise OracleError(f"{len(missing)} packet rows have no label yet: {missing}")

    by_opaque = {row["opaque_id"]: row for row in labels}
    treatment: list[dict[str, object]] = []
    none_rows: list[dict[str, str]] = []
    untestable: list[dict[str, str]] = []
    for opaque in sorted(manifest):
        meta = manifest[opaque]
        label = by_opaque[opaque]
        if meta["no_source_body"] == "true":
            untestable.append(meta)
            continue
        candidates = json.loads(blind[opaque]["candidates_json"])
        _, said_none = interpret(label)
        if said_none:
            none_rows.append(meta)
            continue
        indexes = parse_choice(label, candidates)
        if not indexes:
            raise OracleError(
                f"{opaque} chose no sentence and did not say none; refusing to send an empty claim"
            )
        treatment.append(
            {
                "opaque_id": opaque,
                "row_id": meta["row_id"],
                "gold_label": meta["gold_label"],
                "sentence": " ".join(candidates[index] for index in indexes),
                "chosen": indexes,
            }
        )
    return {
        "treatment": treatment,
        "none_rows": none_rows,
        "untestable": untestable,
        "labeler": sorted({(row.get("labeler") or "").strip() for row in labels}),
    }


def oracle_rows(
    treatment: Sequence[dict[str, object]], rows: Sequence[dict[str, str]]
) -> list[dict[str, str]]:
    """The same rows, with the proxy claim swapped for the sentence the owner chose.

    Nothing else changes: same prompt, same schema, same model, same threshold. The only
    difference between the before and after numbers is the sentence in the claim block.
    """
    by_row = {row["row_id"]: row for row in rows}
    swapped: list[dict[str, str]] = []
    for item in treatment:
        row = dict(by_row[str(item["row_id"])])
        row["source_claim_text"] = str(item["sentence"])
        swapped.append(row)
    return swapped


def estimate(
    all_rows: Sequence[dict[str, str]],
    blind: dict[str, dict[str, str]],
    *,
    on_date: str | None = None,
) -> dict[str, object]:
    """Bound the cost before labels exist, from the candidate sentences in the packet.

    Three columns, because the price depends on which sentence the owner picks: the first
    candidate, the median-length candidate, and the longest candidate that could be chosen.
    """
    from datetime import date as date_type

    variant = get_variant("v3")
    low: list[int] = []
    mid: list[int] = []
    high: list[int] = []
    for row in all_rows:
        candidates = json.loads(blind[row["opaque_id"]]["candidates_json"])
        if not candidates:
            continue
        by_length = sorted(candidates, key=len)
        picks = ((low, candidates[0]), (mid, by_length[len(by_length) // 2]), (high, by_length[-1]))
        for bucket, pick in picks:
            swapped = dict(row["row"])
            swapped["source_claim_text"] = pick
            bucket.append(prompt_tokens(variant.prompt(swapped)))
    if not low:
        raise OracleError("no candidate sentences to estimate from")
    pricing = load_pricing(PRICING)
    day = date_type.fromisoformat(on_date) if on_date else None

    def cost(prompts: Sequence[int]) -> str | None:
        details = estimate_cost_details(
            pricing,
            MODEL,
            sum(prompts),
            COMPLETION_TOKENS_ESTIMATE * len(prompts),
            dry_run=True,
            on_date=day,
        )
        return format(details.usd, "f") if details.usd is not None else None

    return {
        "rows_in_packet": len(all_rows),
        "requests": len(low),
        "prompt_tokens_if_first_candidate": sum(low),
        "prompt_tokens_if_median_candidate": sum(mid),
        "prompt_tokens_if_longest_candidate": sum(high),
        "mean_prompt_tokens": round(sum(mid) / len(mid), 1),
        "completion_tokens_estimate": COMPLETION_TOKENS_ESTIMATE * len(mid),
        "usd_min": cost(low),
        "usd_median": cost(mid),
        "usd_max": cost(high),
        "billing": "free_tier (list price recorded, no charge)",
        "token_count_is": "heuristic ceil(chars/4)",
        "model": MODEL,
        "prompt_version": variant.prompt_version,
        "caveat": (
            "the exact cost is known only once the labels exist; this bounds it from the "
            "first, median and longest candidate sentence in the packet"
        ),
    }


def quota(ledger_path: Path = LEDGER) -> dict[str, object]:
    if not ledger_path.exists():
        return {"ledger": str(ledger_path), "used_today": None, "daily_cap": DAILY_REQUEST_CAP}
    used, today = todays_attempts(ledger_path)
    failures = recent_failures(ledger_path, limit=6)
    return {
        "pacific_day": today,
        "used_today": used,
        "daily_cap": DAILY_REQUEST_CAP,
        "remaining_today": max(DAILY_REQUEST_CAP - used, 0),
        "recent_failures": failures,
    }


def run_live(
    rows: Sequence[dict[str, str]],
    *,
    variant: Variant,
    max_calls: int,
    settings: Settings | None = None,
) -> tuple[dict[str, int], dict[str, object]]:
    """Send the oracle prompts through ``LLMClient`` so every attempt lands in the ledger.

    Same machinery as the P3-05 runs: ledger, cache, pacing, one retry pass, and a resume
    from the checkpoint. The only thing that differs is the stage name and the claim block.
    """
    settings = settings or Settings()
    if not settings.gemini_api_key:
        raise OracleError("GEMINI_API_KEY is not set")
    ledger_path = settings.resolved_ledger_path
    used_today, today = todays_attempts(ledger_path)
    rate: RateLimit = load_rate_limits(DEFAULT_RATE_LIMITS_PATH).require(MODEL)
    if used_today >= rate.daily_cap:
        raise OracleError(
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
    failures_file = failures_path_for(variant)
    failures: dict[str, dict[str, object]] = dict(read_failures(failures_file))
    run_id = f"{STAGE}-{today}"

    def ask(row: dict[str, str]) -> object:
        request = build_request(row, variant, run_id)
        answer = client.complete(
            request, response_model=variant.answer_type, attempt_gate=pacer.reserve
        )
        return variant.answer_type.model_validate_json(answer.text)

    run = score_rows(
        rows,
        variant=variant,
        ask=ask,  # type: ignore[arg-type]
        done=done,
        failures=failures,
        failures_path=failures_file,
        checkpoint_path=variant.checkpoint,
        max_calls=max_calls,
    )
    scores = {
        row_id: int(record["score"]) for row_id, record in read_v2(variant.checkpoint).items()
    }
    return scores, {"run_id": run_id, "calls_made": run["calls_made"], **run}


def compare(
    treatment: Sequence[dict[str, object]],
    after: dict[str, int],
    before: dict[str, int],
    rows: Sequence[dict[str, str]],
    *,
    threshold: int = THRESHOLD,
) -> dict[str, object]:
    """Per-row and aggregate comparison at one pre-registered threshold."""
    by_row = {row["row_id"]: row for row in rows}
    params = tune_heuristic(list(rows))["params"]
    positives = [item for item in treatment if item["gold_label"] == POSITIVE]
    negatives = [item for item in treatment if item["gold_label"] != POSITIVE]

    def caught(items: Sequence[dict[str, object]], scores: dict[str, int]) -> int:
        return sum(1 for item in items if scores.get(str(item["row_id"]), -1) >= threshold)

    per_row = [
        {
            "row_id": item["row_id"],
            "gold_label": item["gold_label"],
            "before": before.get(str(item["row_id"])),
            "after": after.get(str(item["row_id"])),
            "delta": (
                after[str(item["row_id"])] - before[str(item["row_id"])]
                if str(item["row_id"]) in after and str(item["row_id"]) in before
                else None
            ),
            "heuristic": round(heuristic_score(by_row[str(item["row_id"])], params), 1),
        }
        for item in treatment
    ]
    return {
        "threshold": threshold,
        "positives_total": len(positives),
        "positives_caught_before": caught(positives, before),
        "positives_caught_after": caught(positives, after),
        "negatives_total": len(negatives),
        "negatives_fired_before": caught(negatives, before),
        "negatives_fired_after": caught(negatives, after),
        "scored_before": sum(1 for item in treatment if str(item["row_id"]) in before),
        "scored_after": sum(1 for item in treatment if str(item["row_id"]) in after),
        "per_row": per_row,
        "heuristic_params": params,
        "reading": (
            "raw counts out of the positives present; 30 rows can show a direction and not an "
            "effect size"
        ),
    }


def gate_outcome(stats: dict[str, object]) -> dict[str, object]:
    """Apply the rule pre-committed in ADR-0027 Amendment A, without reinterpreting it."""
    gained = int(stats["positives_caught_after"]) - int(stats["positives_caught_before"])
    extra_alarms = int(stats["negatives_fired_after"]) - int(stats["negatives_fired_before"])
    if gained > 0 and extra_alarms <= 0:
        return {
            "build": True,
            "verdict": "worth building",
            "reason": (
                f"the owner's sentence caught {gained} more positive(s) with no extra false "
                "alarm, which is the condition for proposing the linking stage"
            ),
        }
    return {
        "build": False,
        "verdict": "not built",
        "reason": (
            f"positives caught moved by {gained:+d} and negatives fired by {extra_alarms:+d}; "
            "the rule says no movement means link quality is not the ceiling, so the linker "
            "is not built"
        ),
    }


def write_report(result: dict[str, object], path: Path = REPORT) -> None:
    arm = result["arm"]  # type: ignore[index]
    stats = result["comparison"]  # type: ignore[index]
    ledger = ledger_activity(str(result.get("stage", STAGE)), LEDGER)
    per_row = stats["per_row"]
    identical = [row for row in per_row if row["delta"] == 0]
    moved = [row for row in per_row if row["delta"]]

    def side(score: object) -> bool:
        return score is not None and int(str(score)) >= int(stats["threshold"])

    crossed = [
        row
        for row in per_row
        if row["before"] is not None and side(row["before"]) != side(row["after"])
    ]
    none_positive = [row["row_id"] for row in arm["none_rows"] if row["gold_label"] == POSITIVE]
    gate = gate_outcome(stats)  # type: ignore[arg-type]
    lines = [
        "# P3-06 oracle — does the right source sentence help the detector?",
        "",
        "**Written by `scripts/p3_06_oracle.py` from the owner's labels and the ledger. The",
        "dev-only oracle test pre-registered in ADR-0027, not a gate result.**",
        "",
        "## What was swapped",
        "",
        f"- Packet: **{result['packet_rows']}** rows: {POSITIVES} positives,"
        f"  {NEGATIVES} negatives.",
        f"- Treatment arm (a sentence the owner picked): **{len(arm['treatment'])}** rows.",
        f"- Answered `none`: **{len(arm['none_rows'])}** rows, no supporting sentence.",
        f"- Untestable (source has no body text): **{len(arm['untestable'])}** rows.",
        f"- Labels from: {', '.join(arm['labeler'])}.",
        "",
        "Only the claim block changed. Same prompt, same schema, same model, same threshold.",
        "",
        f"## At threshold {stats['threshold']}",
        "",
        "| | positives caught | negatives fired |",
        "|---|---|---|",
        f"| before (abstract proxy) | {stats['positives_caught_before']} of "
        f"{stats['positives_total']} | {stats['negatives_fired_before']} of "
        f"{stats['negatives_total']} |",
        f"| after (owner's sentence) | {stats['positives_caught_after']} of "
        f"{stats['positives_total']} | {stats['negatives_fired_after']} of "
        f"{stats['negatives_total']} |",
        "",
        f"**{len(crossed)} rows crossed the threshold** in either direction; "
        f"{len(identical)} of {len(per_row)} rows scored exactly the same. The counts above "
        "are net, so a gain and a loss cancel: the crossings are named under *What moved* "
        "instead of being netted away.",
        "",
        "Thirty rows can show a direction and not an effect size; no interval is quoted,",
        "because none would be informative at this n.",
        "",
        f"## What moved: {len(moved)} of {len(per_row)} rows",
        "",
    ]
    if moved:
        crosses = {row["row_id"] for row in crossed}
        lines += ["| row | gold | before | after | delta | crossed |", "|---|---|---|---|---|---|"]
        for row in sorted(moved, key=lambda item: -abs(int(item["delta"]))):
            lines.append(
                f"| {row['row_id']} | {row['gold_label']} | {row['before']} | "
                f"{row['after']} | {int(row['delta']):+d} | "
                f"{'yes' if row['row_id'] in crosses else 'no'} |"
            )
        lines.append("")
    else:
        lines += ["No row moved at all.", ""]
    if none_positive:
        lines += [
            "## A gold positive with no supporting sentence",
            "",
            f"`{'`, `'.join(none_positive)}` was answered `none`: reading the whole body, the",
            "owner found no sentence that citing text depends on. That is a statement about the",
            "gold label, not about the model, and it is left standing rather than re-scored.",
            "",
        ]
    lines += [
        "## The pre-committed gate",
        "",
        f"**{gate['verdict'].capitalize()}.** {gate['reason'][0].upper()}{gate['reason'][1:]}.",
        "",
        "The P3-05 dev-negative (ADR-0026 Amendment C) therefore stands unchanged, and the",
        "frozen test set is untouched.",
        "",
        "## Cost, from the ledger",
        "",
    ]
    if ledger:
        lines += [
            f"- {ledger['attempts']} attempts, {ledger['succeeded']} succeeded, "
            f"{ledger['errors']} errors, {ledger['cache_hits']} cache hits.",
            f"- {ledger['prompt_tokens']} prompt + {ledger['completion_tokens']} completion "
            "tokens.",
            f"- **${ledger['list_price_usd']}** at list price, free tier, no charge.",
            f"- Estimate before the run: ${result['plan']['list_price_usd']} "
            f"for {result['plan']['requests']} requests.",
            "",
        ]
    lines += [
        "## Per row",
        "",
        "| row | gold | before | after | delta | heuristic |",
        "|---|---|---|---|---|---|",
    ]
    for row in per_row:
        lines.append(
            f"| {row['row_id']} | {row['gold_label']} | {row['before']} | {row['after']} | "
            f"{row['delta']} | {row['heuristic']} |"
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("estimate", "dry-run", "live"), default="estimate")
    parser.add_argument("--labels", type=Path, default=LABELS)
    parser.add_argument("--threshold", type=int, default=THRESHOLD)
    parser.add_argument("--max-calls", type=int, default=40)
    parser.add_argument("--checkpoint", type=Path, default=CHECKPOINT)
    args = parser.parse_args(argv)

    manifest, blind = load_packet()
    rows = spec_rows(scored_rows(load_rows()), "dev")

    if args.mode == "estimate":
        numbered = [
            {"opaque_id": opaque, "row": next(r for r in rows if r["row_id"] == meta["row_id"])}
            for opaque, meta in sorted(manifest.items())
        ]
        print(json.dumps({"estimate": estimate(numbered, blind), "quota": quota()}, indent=2))
        return 0

    arm = oracle_arm(manifest, blind, read_labels(args.labels))
    treatment = arm["treatment"]  # type: ignore[index]
    swapped = oracle_rows(treatment, rows)  # type: ignore[arg-type]
    variant = get_variant("v3")
    prompts = [prompt_tokens(variant.prompt(row)) for row in swapped]
    pricing = load_pricing(PRICING)
    details = estimate_cost_details(
        pricing, MODEL, sum(prompts), COMPLETION_TOKENS_ESTIMATE * len(swapped), dry_run=True
    )
    plan = {
        "requests": len(swapped),
        "prompt_tokens": sum(prompts),
        "prompt_tokens_max": max(prompts) if prompts else 0,
        "completion_tokens_estimate": COMPLETION_TOKENS_ESTIMATE * len(swapped),
        "list_price_usd": format(details.usd, "f") if details.usd is not None else None,
        "billing": "free_tier (list price recorded, no charge)",
        "token_count_is": "heuristic ceil(chars/4)",
        "quota": quota(),
    }
    if args.mode == "dry-run":
        print(json.dumps({"arm": arm, "plan": plan}, indent=2, default=str))
        return 0

    if len(swapped) > args.max_calls:
        raise OracleError(
            f"{len(swapped)} requests but --max-calls is {args.max_calls}; raise it deliberately"
        )
    remaining = plan["quota"].get("remaining_today")  # type: ignore[index]
    if isinstance(remaining, int) and remaining < len(swapped):
        raise OracleError(
            f"only {remaining} requests left on the Pacific day; the oracle needs {len(swapped)}"
        )
    before = {row_id: int(record["score"]) for row_id, record in read_v2(V3_SCORES).items()}
    variant = replace(
        get_variant("v3"),
        name="oracle",
        prompt_version="p3-05-llm-v3-oracle",
        checkpoint=args.checkpoint,
    )
    after, run = run_live(swapped, variant=variant, max_calls=args.max_calls)
    result: dict[str, object] = {
        "packet_rows": len(manifest),
        "arm": arm,
        "plan": plan,
        "run": run,
        "comparison": compare(treatment, after, before, rows, threshold=args.threshold),  # type: ignore[arg-type]
        "stage": STAGE,
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result, indent=2, default=str) + chr(10)
    SUMMARY.write_text(payload, encoding="utf-8", newline=chr(10))
    write_report(result)
    print(json.dumps({"written": str(SUMMARY), "report": str(REPORT)}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OracleError, LLMError) as error:
        print(f"refused: {error}", file=sys.stderr)
        sys.exit(2)
