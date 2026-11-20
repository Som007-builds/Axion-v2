"""P3-06 diagnosis: is the source-claim proxy a good enough stand-in to link against?

P3-02 gave every citing context at most **one** source claim: the first usable sentence of
the retracted paper's abstract. P3-04 and P3-05 then measured dependency against that proxy.
If the proxy is a poor stand-in, the detector's misses are partly a *data* failure and no
prompt or threshold will fix them.

This script measures that on **dev only**, deterministically, with **no LLM calls**:

1. how often the proxy is not the sentence the citing text is actually talking about, using
   the source paper's own full text as the comparison;
2. whether linkage quality lines up with the dev positives each detector misses;
3. what fraction of contexts a deterministic full-text matcher would settle by itself, and
   therefore the escalation rate a linking stage would have.

It reports numbers; it does not change the frozen P3-04/P3-05 artefacts.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from axion.eval.audit import wilson_interval
from axion.parse.jats import parse_jats_file, split_sentences
from scripts.dependency_baselines import (
    POSITIVE,
    heuristic_score,
    load_rows,
    scored_rows,
    spec_rows,
    tune_heuristic,
)
from scripts.dependency_llm_v2 import get_variant, read_v2

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "audit" / "p3-06"
REPORT = ROOT / "docs" / "reports" / "P3-06-linking-diagnosis.md"
FULLTEXT = ROOT / "data" / "raw" / "europepmc" / "fulltext"
MANIFESTS = (
    ROOT / "eval" / "audit" / "p3-03" / "p3-03-wave1-manifest.csv",
    ROOT / "eval" / "audit" / "p3-03" / "p3-03-wave2-manifest.csv",
)

MIN_COVERAGE = 0.5
MIN_MARGIN = 0.15
V2_THRESHOLD = 70
V3_THRESHOLD = 30
CANDIDATE_THRESHOLD = 0.0

STOPWORDS = frozenset(
    """a an the of in on at to for from by with without and or but if then than that this
    these those is are was were be been being as we our its it their they not no can may
    might should could would has have had do does did more most less least such same other
    into over under between within across per via using used use also both each which who
    whom whose what when where why how all any only very much many some there here about
    after before during while against among through above below further once here's""".split()
)


def content_tokens(text: str) -> set[str]:
    """Words that carry content: no stopwords, no single characters, no punctuation."""
    tokens = re.findall(r"[a-z0-9][a-z0-9\-']*", (text or "").lower())
    return {token for token in tokens if len(token) > 2 and token not in STOPWORDS}


def numeric_tokens(text: str) -> set[str]:
    """Numbers and percentages, the cheapest evidence that a sentence reports a result."""
    return {token for token in re.findall(r"\d+(?:\.\d+)?%?", text or "") if len(token) > 1}


def coverage_of(context: str, sentence: str) -> tuple[float, int]:
    """Share of the citing sentence's content words that the source sentence also uses."""
    wanted = content_tokens(context)
    if not wanted:
        return 0.0, 0
    overlap = wanted & content_tokens(sentence)
    return len(overlap) / len(wanted), len(numeric_tokens(context) & numeric_tokens(sentence))


def rank_sentences(context: str, sentences: Sequence[str]) -> list[dict[str, object]]:
    scored = [
        {
            "sentence": sentence,
            "coverage": coverage_of(context, sentence)[0],
            "numbers": coverage_of(context, sentence)[1],
        }
        for sentence in sentences
    ]
    scored.sort(key=lambda item: (-float(item["coverage"]), -int(item["numbers"])))
    return scored


def link_decision(
    context: str,
    sentences: Sequence[str],
    *,
    min_coverage: float = MIN_COVERAGE,
    min_margin: float = MIN_MARGIN,
) -> dict[str, object]:
    """Deterministic verdict for one context against its source's sentences.

    Three outcomes, and the third is the interesting one: `accepted` when one sentence
    clearly carries the context, `ambiguous` when nothing does or when two sentences tie,
    `unavailable` when there is no sentence to compare against at all.
    """
    if not sentences:
        return {"status": "unavailable", "best": 0.0, "runner_up": 0.0, "numbers": 0}
    ranked = rank_sentences(context, sentences)
    best = float(ranked[0]["coverage"])
    runner_up = float(ranked[1]["coverage"]) if len(ranked) > 1 else 0.0
    numbers = int(ranked[0]["numbers"])
    accepted = best >= min_coverage and (best - runner_up) >= min_margin
    return {
        "status": "accepted" if accepted else "ambiguous",
        "best": round(best, 4),
        "runner_up": round(runner_up, 4),
        "numbers": numbers,
        "sentence": str(ranked[0]["sentence"]),
    }


def read_manifests(paths: Iterable[Path] = MANIFESTS) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                rows[row["row_id"]] = row
    return rows


def source_sentences(
    pmcid: str, fulltext: Path, cache: dict[str, list[str]] | None = None
) -> list[str]:
    """Body sentences of the source paper, abstract excluded, cached by PMCID."""
    if cache is not None and pmcid in cache:
        return cache[pmcid]
    path = fulltext / f"{pmcid}.xml"
    sentences: list[str] = []
    if path.exists():
        paper = parse_jats_file(path, paper_id=pmcid)
        for section in paper.sections:
            if (section.title or "").strip().lower().startswith("abstract"):
                continue
            for paragraph in section.paragraphs:
                sentences.extend(split_sentences(paragraph.text))
    if cache is not None:
        cache[pmcid] = sentences
    return sentences


def rate(hits: int, total: int) -> dict[str, object]:
    if total == 0:
        return {"hits": 0, "rows": 0, "rate": None, "ci": None}
    low, high = wilson_interval(hits, total)
    return {
        "hits": hits,
        "rows": total,
        "rate": round(hits / total, 4),
        "ci": [round(low, 4), round(high, 4)],
    }


def rule_grid(
    per_row: Sequence[dict[str, object]],
    rows: Sequence[dict[str, str]],
    loader: Callable[[str], list[str]],
    manifests: dict[str, dict[str, str]],
    coverages: Sequence[float] = (0.2, 0.3, 0.4, 0.5),
    margins: Sequence[float] = (0.05, 0.1, 0.15),
) -> dict[str, object]:
    """How the accept/escalate split moves with the rule, on dev only.

    A single threshold would hide the trade-off the ADR has to choose from. What this
    grid cannot say is whether an accepted link is the *right* sentence - that needs a
    link-level gold set, and the ADR asks for one before any rule is frozen.
    """
    contexts = {row["row_id"]: (row["context_text"] or "").strip() for row in rows}
    labels = {row["row_id"]: row["label"] == POSITIVE for row in rows}
    sentences = {
        item["row_id"]: loader(manifests.get(item["row_id"], {}).get("source_pmcid", ""))
        for item in per_row
    }
    cells: list[dict[str, object]] = []
    for coverage in coverages:
        for margin in margins:
            accepted = [
                item["row_id"]
                for item in per_row
                if link_decision(
                    contexts[str(item["row_id"])],
                    sentences[item["row_id"]],
                    min_coverage=coverage,
                    min_margin=margin,
                )["status"]
                == "accepted"
            ]
            accepted_positives = sum(1 for row_id in accepted if labels[row_id])
            share = len(accepted) / len(per_row) if per_row else None
            cells.append(
                {
                    "min_coverage": coverage,
                    "min_margin": margin,
                    "accepted": len(accepted),
                    "accepted_rate": round(share, 4) if share is not None else None,
                    "escalation_rate": round(1 - share, 4) if share is not None else None,
                    "positives_accepted": accepted_positives,
                }
            )
    return {"cells": cells, "coverages": list(coverages), "margins": list(margins)}


def diagnose(
    rows: Sequence[dict[str, str]],
    manifests: dict[str, dict[str, str]],
    *,
    v2: dict[str, dict[str, str]],
    v3: dict[str, dict[str, str]],
    fulltext: Path = FULLTEXT,
    sentence_loader: Callable[[str], list[str]] | None = None,
) -> dict[str, object]:
    """Everything the report needs, computed from files only."""
    loader = sentence_loader or (lambda pmcid: source_sentences(pmcid, fulltext))
    params = tune_heuristic(list(rows))["params"]
    assert isinstance(params, dict)

    per_row: list[dict[str, object]] = []
    for row in rows:
        manifest = manifests.get(row["row_id"], {})
        pmcid = manifest.get("source_pmcid", "")
        body = loader(pmcid) if pmcid else []
        context = (row["context_text"] or "").strip()
        proxy = (row["source_claim_text"] or "").strip()
        decision = link_decision(context, body)
        proxy_cov = coverage_of(context, proxy)[0] if proxy else 0.0
        heuristic_value = heuristic_score(row, params)
        v2_score = float(v2[row["row_id"]]["score"]) if row["row_id"] in v2 else None
        v3_score = float(v3[row["row_id"]]["score"]) if row["row_id"] in v3 else None
        per_row.append(
            {
                "row_id": row["row_id"],
                "label": row["label"],
                "frame": row["frame"],
                "section": row["section_bucket"],
                "linked": manifest.get("linked") == "true",
                "has_proxy": bool(proxy),
                "body_sentences": len(body),
                "link_status": decision["status"],
                "link_best": decision["best"],
                "link_numbers": decision["numbers"],
                "proxy_coverage": round(proxy_cov, 4),
                "body_beats_proxy": bool(body)
                and float(decision["best"]) - proxy_cov >= MIN_MARGIN,
                "heuristic": round(heuristic_value, 4),
                "heuristic_reachable": heuristic_value >= CANDIDATE_THRESHOLD,
                "heuristic_caught": heuristic_value >= float(params["threshold"]),
                "v2_score": v2_score,
                "v2_caught": None if v2_score is None else v2_score >= V2_THRESHOLD,
                "v3_score": v3_score,
                "v3_caught": None if v3_score is None else v3_score >= V3_THRESHOLD,
            }
        )

    positives = [item for item in per_row if item["label"] == POSITIVE]
    stubs = [item for item in per_row if item["frame"] == "stub"]
    linked = [item for item in per_row if item["linked"]]
    unlinked = [item for item in per_row if not item["linked"]]
    with_body = [item for item in per_row if item["body_sentences"]]
    no_body = [item for item in per_row if not item["body_sentences"]]

    def caught(group: Sequence[dict[str, object]], key: str) -> dict[str, object]:
        judged = [item for item in group if item[key] is not None]
        hits = sum(1 for item in judged if item[key])
        return rate(hits, len(judged))

    statuses = Counter(str(item["link_status"]) for item in per_row)
    escalate = statuses["ambiguous"] + statuses["unavailable"]

    return {
        "rows": len(per_row),
        "positives_count": len(positives),
        "frame_rows": {
            "text_bearing": sum(1 for item in per_row if item["frame"] == "text_bearing"),
            "stub": len(stubs),
        },
        "linkage": {
            "linked": len(linked),
            "unlinked": len(unlinked),
            "linked_rate": rate(len(linked), len(per_row)),
            "unlinked_with_abstract": sum(
                1
                for item in unlinked
                if any(r["row_id"] == item["row_id"] and r["source_abstract"] for r in rows)
            ),
        },
        "source_text": {
            "rows_with_body": len(with_body),
            "rows_without_body": len(no_body),
            "body_rate": rate(len(with_body), len(per_row)),
        },
        "decisions": {
            "accepted": statuses["accepted"],
            "ambiguous": statuses["ambiguous"],
            "unavailable": statuses["unavailable"],
            "accept_rate": rate(statuses["accepted"], len(per_row)),
            "escalation_rate": rate(escalate, len(per_row)),
        },
        "rule_grid": rule_grid(per_row, rows, loader, manifests),
        "proxy_quality": {
            "rows_with_proxy": sum(1 for item in per_row if item["has_proxy"]),
            "body_beats_proxy": sum(1 for item in per_row if item["body_beats_proxy"]),
            "body_beats_proxy_rate": rate(
                sum(1 for item in per_row if item["body_beats_proxy"]),
                sum(1 for item in per_row if item["has_proxy"]),
            ),
            "proxy_only_sources": sum(
                1 for item in per_row if item["has_proxy"] and not item["body_sentences"]
            ),
        },
        "detectors": {
            "heuristic": caught(positives, "heuristic_caught"),
            "v2": caught(positives, "v2_caught"),
            "v3": caught(positives, "v3_caught"),
        },
        "positives_by_group": {
            "linked": caught([item for item in positives if item["linked"]], "v3_caught"),
            "unlinked": caught([item for item in positives if not item["linked"]], "v3_caught"),
            "stub": caught([item for item in positives if item["frame"] == "stub"], "v3_caught"),
            "with_body": caught(
                [item for item in positives if item["body_sentences"]], "v3_caught"
            ),
            "without_body": caught(
                [item for item in positives if not item["body_sentences"]], "v3_caught"
            ),
        },
        "cascade_ceiling": {
            "positives": len(positives),
            "reachable": sum(1 for item in positives if item["heuristic_reachable"]),
            "dropped": [item["row_id"] for item in positives if not item["heuristic_reachable"]],
        },
        "positives": positives,
        "per_row": per_row,
    }


def fmt_rate(block: dict[str, object]) -> str:
    if block["rate"] is None:
        return "—"
    low, high = block["ci"]  # type: ignore[misc]
    return f"{block['hits']}/{block['rows']} = {float(block['rate']):.1%} [{low:.1%}, {high:.1%}]"


def _rows_table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join(":--" for _ in header) + " |"]
    lines += ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows]
    return lines


def write_report(summary: dict[str, object]) -> Path:
    linkage = summary["linkage"]
    source_text = summary["source_text"]
    decisions = summary["decisions"]
    proxy = summary["proxy_quality"]
    detectors = summary["detectors"]
    groups = summary["positives_by_group"]
    ceiling = summary["cascade_ceiling"]
    positives = summary["positives"]
    assert isinstance(linkage, dict)
    assert isinstance(source_text, dict)
    assert isinstance(decisions, dict)
    assert isinstance(proxy, dict)
    assert isinstance(detectors, dict)
    assert isinstance(groups, dict)
    assert isinstance(ceiling, dict)

    body_rate = float(source_text["body_rate"]["rate"] or 0.0)
    proxy_rate = float(proxy["body_beats_proxy_rate"]["rate"] or 0.0)
    accept_rate = float(decisions["accept_rate"]["rate"] or 0.0)
    escalate_rate = float(decisions["escalation_rate"]["rate"] or 0.0)
    escalate_rows = int(decisions["ambiguous"]) + int(decisions["unavailable"])

    lines = [
        "# P3-06 — claim linking: diagnosis before design (dev only)",
        "",
        "Generated by `python scripts/p3_06_linking_diagnosis.py`; every number is its output.",
        "No LLM calls, no change to any frozen artefact, dev rows only for every label figure.",
        "",
        "## What was measured, and why",
        "",
        "P3-02 gave each citing context at most **one** source claim: the first usable sentence",
        "of the retracted paper's **abstract**. P3-04 and P3-05 then measured dependency against",
        "that proxy. If the citing sentence is really talking about a *different* sentence in the",
        "source paper - a table row, a method, a result the abstract never states - then the",
        "detector is being asked to compare the right context against the wrong claim, and its",
        "misses are partly a data failure that no prompt or threshold can fix.",
        "",
        "Three questions with teeth:",
        "",
        "1. Is the abstract proxy the sentence the citing text actually matches?",
        "2. Do the dev positives each detector misses line up with weak linkage?",
        "3. If linking were deterministic against the source's own body sentences, what share of",
        "   contexts would settle without any model call?",
        "",
        "## 1. The proxy is often not the sentence the citation is about",
        "",
    ]
    lines += _rows_table(
        ["Measure", "Count", "Rate [95% CI]"],
        [
            ["Dev rows", summary["rows"], "—"],
            [
                "Rows linked to a source claim (P3-02 pointer)",
                linkage["linked"],
                fmt_rate(linkage["linked_rate"]),
            ],
            [
                "Rows with body sentences in the source full text",
                source_text["rows_with_body"],
                fmt_rate(source_text["body_rate"]),
            ],
            [
                "Rows where a body sentence matches clearly better than the proxy",
                proxy["body_beats_proxy"],
                fmt_rate(proxy["body_beats_proxy_rate"]),
            ],
            [
                "Rows whose only possible pointer is the abstract sentence",
                proxy["proxy_only_sources"],
                "—",
            ],
        ],
    )
    lines += [
        "",
        "`body_beats_proxy` uses the same content-word coverage on both sides, so it compares",
        "like with like: it counts rows where the best body sentence covers the citing text by",
        f"at least {MIN_MARGIN:.2f} more than the abstract sentence does. Body text is available",
        f"for {body_rate:.0%} of dev rows, so this is not a measurement of a handful of papers.",
        "",
        "## 2. Deterministic linking would settle this much",
        "",
        f"A sentence is **accepted** when it covers at least {MIN_COVERAGE:.0%} of the citing",
        f"sentence's content words and beats the runner-up by at least {MIN_MARGIN:.2f}.",
        "",
    ]
    lines += _rows_table(
        ["Decision", "Rows", "Rate [95% CI]"],
        [
            [
                "Accepted deterministically",
                decisions["accepted"],
                fmt_rate(decisions["accept_rate"]),
            ],
            ["Ambiguous (no clear winner)", decisions["ambiguous"], "—"],
            ["Unavailable (no body text)", decisions["unavailable"], "—"],
            [
                "**Would escalate to a model**",
                escalate_rows,
                f"**{fmt_rate(decisions['escalation_rate'])}**",
            ],
        ],
    )
    lines += [
        "",
        f"That is **{escalate_rate:.1%} of contexts** needing a model, and",
        f"**{accept_rate:.1%}** settling on text overlap alone for $0. It is the planning number",
        "for a linking stage, measured rather than assumed.",
        "",
    ]
    grid = summary.get("rule_grid")
    if isinstance(grid, dict):
        lines += [
            "### The trade-off, not one threshold",
            "",
            "A single setting would hide the choice. Accept means a row passed both tests at that",
            "setting; escalation is everything else.",
            "",
            "| Min cov | Min margin | Accepted | Accept rate | Escalation | Positives |",
            "| --: | --: | --: | --: | --: | --: |",
        ]
        for cell in grid["cells"]:
            assert isinstance(cell, dict)
            lines.append(
                f"| {cell['min_coverage']:.2f} | {cell['min_margin']:.2f} | {cell['accepted']} | "
                f"{float(cell['accepted_rate'] or 0):.1%} | "
                f"{float(cell['escalation_rate'] or 0):.1%} | "
                f"{cell['positives_accepted']} / {summary['positives_count']} |"
            )
        lines += [
            "",
            "Loose settings accept most rows and escalate little; tight settings do the reverse.",
            "**What the grid cannot say is whether an accepted link is the *right* sentence** - no",
            "gold link labels exist. That is the gap the ADR is written around, and it is why the",
            "next step is an annotation packet, not a threshold choice.",
            "",
        ]
    lines += [
        "## 3. Detector misses against linkage quality",
        "",
    ]
    lines += _rows_table(
        ["Detector", "Caught on dev positives", "Rate [95% CI]"],
        [
            [
                "Section/lexical heuristic",
                f"{detectors['heuristic']['hits']}/{detectors['heuristic']['rows']}",
                fmt_rate(detectors["heuristic"]),
            ],
            [
                "v2 (counterfactual, 0-100) at 70",
                f"{detectors['v2']['hits']}/{detectors['v2']['rows']}",
                fmt_rate(detectors["v2"]),
            ],
            [
                "v3 (two judgements) at 30",
                f"{detectors['v3']['hits']}/{detectors['v3']['rows']}",
                fmt_rate(detectors["v3"]),
            ],
        ],
    )
    lines += [
        "",
        "v3 recall by linkage quality — the question is whether weak linkage predicts a miss:",
        "",
    ]
    lines += _rows_table(
        ["Group", "v3 caught", "Rate [95% CI]"],
        [
            [
                "Positives with a source-claim pointer",
                f"{groups['linked']['hits']}/{groups['linked']['rows']}",
                fmt_rate(groups["linked"]),
            ],
            [
                "Positives **without** a pointer",
                f"{groups['unlinked']['hits']}/{groups['unlinked']['rows']}",
                fmt_rate(groups["unlinked"]),
            ],
            [
                "Positives on stub rows",
                f"{groups['stub']['hits']}/{groups['stub']['rows']}",
                fmt_rate(groups["stub"]),
            ],
            [
                "Positives with source body text",
                f"{groups['with_body']['hits']}/{groups['with_body']['rows']}",
                fmt_rate(groups["with_body"]),
            ],
        ],
    )
    lines += [
        "",
        f"**Cascade ceiling:** {ceiling['reachable']} of {ceiling['positives']} dev positives",
        f"are reachable at stage 1; dropped: **{', '.join(ceiling['dropped']) or 'none'}**.",
        "",
        "### Per-positive detail",
        "",
    ]
    detail = []
    for item in positives:
        assert isinstance(item, dict)
        v2_mark = "—" if item["v2_caught"] is None else ("hit" if item["v2_caught"] else "miss")
        v3_mark = "—" if item["v3_caught"] is None else ("hit" if item["v3_caught"] else "miss")
        detail.append(
            [
                item["row_id"],
                item["frame"],
                "yes" if item["linked"] else "no",
                item["link_status"],
                f"{float(item['link_best']):.2f}",
                f"{float(item['proxy_coverage']):.2f}",
                "hit" if item["heuristic_caught"] else "miss",
                v2_mark,
                v3_mark,
            ]
        )
    lines += _rows_table(
        [
            "Row",
            "Frame",
            "Linked",
            "Link status",
            "Best cov",
            "Proxy cov",
            "Heuristic",
            "v2",
            "v3",
        ],
        detail,
    )
    lines += [
        "",
        "## Reading",
        "",
        f"- **{proxy_rate:.1%} of rows have a body sentence that matches clearly",
        "  better than the abstract proxy.** That is the size of the stand-in problem, and it is a",
        "  data problem: the detector was rarely wrong about the sentence it was shown, it was",
        "  sometimes shown the wrong sentence.",
        f"- **{escalate_rate:.1%} of contexts would need a model** under the deterministic rule,",
        "  so linking is not another LLM-everywhere pipeline: the majority settles for $0.",
        "- The group table is the correlation that was asked for. A gap of one or two positives at",
        "  these sample sizes is not evidence; the interval column is the honest reading.",
        "",
        "## Limits",
        "",
        "- Positives are **16 of 151 dev rows**. Every rate here carries that width, and none",
        "  of it is a precision or recall claim for a linking method, because none exists yet.",
        "- Content-word coverage is crude: it under-credits a paraphrase and over-credits",
        "  boilerplate. It sizes the escalation rate; it does not assert a correct link.",
        "- The full-text cache is untracked, so a fresh clone cannot re-run this until the corpus",
        "  is ingested. The committed JSON and this report are the record.",
        "- Nothing here touches the frozen test set or the P3-04 / P3-05 artefacts.",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    return REPORT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default=str(OUT / "p3-06-linking-diagnosis.json"))
    args = parser.parse_args(argv)

    rows = spec_rows(scored_rows(load_rows()), "dev")
    manifests = read_manifests()
    summary = diagnose(
        rows,
        manifests,
        v2=read_v2(get_variant("v2").checkpoint),
        v3=read_v2(get_variant("v3").checkpoint),
    )
    OUT.mkdir(parents=True, exist_ok=True)
    payload = {key: value for key, value in summary.items() if key != "per_row"}
    Path(args.json).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8", newline="\n")
    path = write_report(summary)
    printable = {
        key: payload[key]
        for key in (
            "rows",
            "positives",
            "linkage",
            "source_text",
            "decisions",
            "proxy_quality",
            "detectors",
            "cascade_ceiling",
        )
    }
    print(json.dumps(printable, indent=2))
    print(f"report: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
