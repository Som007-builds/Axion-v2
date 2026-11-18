"""Draw P3-03 wave 2: 150 uniform rows from the pool left after wave 1 (ADR-0024).

Wave 2 exists because wave 1's cue-enriched frame did not beat its uniform slice,
so the cues are not used here at all. This draws uniformly from the remaining
5,967 contexts with equal inclusion probability, applies the same 8-rows-per-source
cap as ADR-0023, and inherits the frozen source-level dev/test split. Wave 1 is
not touched. No labels are created and no overlap file is written.

Usage:
    python scripts/dependency_wave2.py
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # running as `python scripts/dependency_wave2.py`
    sys.path.insert(0, str(ROOT))

from scripts.dependency_sample import (  # noqa: E402
    BLIND_COLUMNS,
    FULLTEXT,
    GUIDELINE_VERSION,
    MANIFEST_COLUMNS,
    OUT,
    SEED,
    SOURCE_CAP,
    TEMPLATE,
    _abstract_text,
    _assign_splits,
    _cues,
    _labeler_html,
    _load_bundle,
    _section_bucket,
    _uniform,
    _write_csv,
)

WAVE = "wave2"
WAVE2_SIZE = 150
WAVE2_SEED = SEED + 101  # a distinct stream, so wave 1 does not move
WAVE1_MANIFEST = OUT / "p3-03-wave1-manifest.csv"
REPORT = ROOT / "docs" / "reports" / "P3-03-wave2-packet.md"


class WaveError(Exception):
    """Wave 2 cannot be drawn from the committed state."""


def wave1_context_ids(path: Path = WAVE1_MANIFEST) -> set[str]:
    """Row ids already used by wave 1, read from its committed manifest."""
    if not path.exists():
        raise WaveError(f"wave 1 manifest not found: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["ctx_id"] for row in csv.DictReader(handle)}


def draw_wave2(
    contexts: list[dict],
    used: set[str],
    *,
    size: int = WAVE2_SIZE,
    seed: int = WAVE2_SEED,
    cap: int = SOURCE_CAP,
) -> tuple[list[dict], int]:
    """Uniform draw from the unused pool, capped per source. Returns rows and pool size."""
    pool = [row for row in contexts if row["ctx_id"] not in used]
    if len(pool) < size:
        raise WaveError(f"only {len(pool)} contexts remain; wave 2 needs {size}")
    return _uniform(pool, size, random.Random(seed), cap), len(pool)


def build_rows(
    chosen: list[dict], splits: dict[str, str], pool_size: int, *, size: int = WAVE2_SIZE
) -> list[dict]:
    """Manifest rows with the nominal uniform inclusion probability and weight."""
    probability = size / pool_size
    rows: list[dict] = []
    for row in chosen:
        rows.append(
            {
                "ctx_id": row["ctx_id"],
                "citer_pmcid": row["citer_pmcid"],
                "source_pmcid": row["source_pmcid"],
                "section": row["section"],
                "section_bucket": row["section_bucket"],
                "frame": "uniform",
                "stratum": "uniform",
                "inclusion_prob": round(probability, 8),
                "weight": round(1 / probability, 4),
                "cue_score": row["cue_score"],
                "cues": row["cues"],
                "linked": row["linked"],
                "split": splits[row["source_pmcid"]],
                "overlap": "false",
            }
        )
    rows.sort(key=lambda item: (item["split"], item["source_pmcid"], item["ctx_id"]))
    for number, row in enumerate(rows, start=1):
        row["row_id"] = f"P3W2-{number:03d}"
    return rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild", action="store_true", help="re-parse instead of using the cache"
    )
    args = parser.parse_args(argv)

    contexts, papers, claims = _load_bundle(args.rebuild)
    paper_by_id = {row["pmcid"]: row for row in papers}
    claim_text = {row["claim_id"]: row["text"] for row in claims}
    for row in contexts:
        row["section_bucket"] = _section_bucket(row["section"])
        fired, score = _cues(row["text"])
        row["cues"] = ";".join(fired)
        row["cue_score"] = score
        row["linked"] = "true" if row["source_claim_id"] else "false"

    used = wave1_context_ids()
    if len(used) != 150:
        raise WaveError(f"wave 1 manifest lists {len(used)} contexts, expected 150")
    chosen, pool_size = draw_wave2(contexts, used)
    splits = _assign_splits(Counter(row["source_pmcid"] for row in contexts), SEED)
    rows = build_rows(chosen, splits, pool_size)

    by_id = {row["ctx_id"]: row for row in contexts}
    parsed_abstracts: dict[str, str] = {}
    blind: list[dict] = []
    for row in rows:
        ctx = by_id[row["ctx_id"]]
        citer = paper_by_id.get(ctx["citer_pmcid"], {})
        source = paper_by_id.get(ctx["source_pmcid"], {})
        linked = row["linked"] == "true"
        abstract = "" if linked else _abstract_text(ctx["source_pmcid"], FULLTEXT, parsed_abstracts)
        row["text_bearing"] = "true" if (linked or abstract) else "false"
        blind.append(
            {
                "row_id": row["row_id"],
                "citer_pmcid": ctx["citer_pmcid"],
                "citer_title": citer.get("title") or "",
                "source_pmcid": ctx["source_pmcid"],
                "source_title": source.get("title") or "",
                "source_pmid": source.get("pmid") or "",
                "source_doi": source.get("doi") or "",
                "retraction_record_ids": "",
                "context_text": ctx["text"],
                "paragraph_text": ctx["paragraph_text"],
                "section": ctx["section"],
                "marker": ctx["marker"],
                "linked": row["linked"],
                "source_claim_text": claim_text.get(ctx["source_claim_id"], "") if linked else "",
                "source_abstract": abstract,
                "label": "",
                "note": "",
                "labeler": "",
                "date": "",
                "guideline_version": GUIDELINE_VERSION,
            }
        )

    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / f"p3-03-{WAVE}-manifest.csv"
    blind_path = OUT / f"p3-03-{WAVE}-blind.csv"
    labeler_path = OUT / f"p3-03-{WAVE}-labeler.html"
    _write_csv(manifest_path, MANIFEST_COLUMNS, rows)
    _write_csv(blind_path, BLIND_COLUMNS, blind)
    labeler_path.write_text(
        _labeler_html(
            TEMPLATE.read_text(encoding="utf-8"),
            title="P3-03 wave 2 dependency audit",
            subtitle=(
                "Blind review: no model output, weights, strata or split are shown. "
                "Label each context-source edge."
            ),
            set_key="axion-p3-03-wave2",
            export_name="dependency_audit_v1_wave2_labelled.csv",
            default_labeler="Soham",
            rows=blind,
        ),
        encoding="utf-8",
        newline="\n",
    )

    split_rows = Counter(row["split"] for row in rows)
    split_sources = {
        name: len({row["source_pmcid"] for row in rows if row["split"] == name})
        for name in ("dev", "test")
    }
    pool_by_source = Counter(row["source_pmcid"] for row in contexts if row["ctx_id"] not in used)
    drawn_by_source = Counter(row["source_pmcid"] for row in rows)
    truncated = sorted(
        source
        for source, count in drawn_by_source.items()
        if count >= SOURCE_CAP and pool_by_source[source] > count
    )
    linked_share = sum(1 for row in rows if row["linked"] == "true") / len(rows)
    stubs = sum(1 for row in rows if row["text_bearing"] == "false")
    probability = WAVE2_SIZE / pool_size
    summary = {
        "wave": WAVE,
        "seed": WAVE2_SEED,
        "rows": len(rows),
        "pool": pool_size,
        "inclusion_prob": round(probability, 8),
        "weight": round(1 / probability, 4),
        "source_cap": SOURCE_CAP,
        "capped_sources": len(truncated),
        "split_rows": dict(split_rows),
        "split_sources": split_sources,
        "linked_share": round(linked_share, 4),
        "stub_rows": stubs,
        "text_bearing_rows": len(rows) - stubs,
        "shared_contexts_with_wave1": len({row["ctx_id"] for row in rows} & used),
    }
    (OUT / f"p3-03-{WAVE}-sampling.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines = [
        "# P3-03 wave 2 packet - uniform-only top-up (ADR-0024)",
        "",
        "**Status:** packet ready; **no labels created**. Generated by "
        "`python scripts/dependency_wave2.py`; every number below is its output.",
        "",
        f"**Seed:** `{WAVE2_SEED}` · **Rows:** {len(rows)} · "
        f"**Guideline:** `{GUIDELINE_VERSION}` · "
        f"**Pool:** {pool_size:,} contexts left after wave 1.",
        "",
        "## Sampling rule and weights",
        "",
        f"- Uniform at random from the remaining pool, **equal inclusion probability** "
        f"π = {WAVE2_SIZE}/{pool_size:,} = **{probability:.6f}**, "
        f"weight **{1 / probability:.2f}**.",
        "- **No cue filter and no cue stratum** (ADR-0024): wave 1 showed no measured cue lift.",
        f"- **Cap {SOURCE_CAP} rows per source**, the same handling ADR-0023 applies to its "
        "uniform frame.",
        f"  Sources truncated by the cap: **{len(truncated)}**"
        + (f" ({', '.join(f'`{p}`' for p in truncated)})." if truncated else "."),
        "  Truncation makes the nominal weights approximate for those sources; they are listed so",
        "  the effect is checkable, exactly as ADR-0023 §2 records.",
        f"- **Split inherited, not redrawn:** the frozen source-level assignment gives "
        f"**{split_rows['dev']} dev / {split_rows['test']} test rows** over "
        f"**{split_sources['dev']} / {split_sources['test']}** source papers.",
        f"- Contexts shared with wave 1: **{summary['shared_contexts_with_wave1']}** (must be 0).",
        "",
        "## Composition",
        "",
        f"- Rows with a source-claim pointer: **{linked_share:.1%}**.",
        f"- Title-only stub rows (no abstract, no claim): **{stubs}**; these stay in the gold set",
        "  and are reported as a separate stratum (ADR-0023 Amendment B), not as negatives.",
        "",
        "## Target, and the stop rule (ADR-0024 §5)",
        "",
        "- Wave 2 aims to add ~35 positives at the measured 23.3%, taking the total to ~60.",
        "- After wave 2 the metrics script reports positives per split, the updated weighted",
        "  base rate with a Wilson interval, and the extra rows still needed for the",
        "  0.80-observed-recall case (77 positives). A shortfall is reported; no wave 3 starts",
        "  without a new owner decision.",
        "",
        "## Files",
        "",
        f"- **Label this:** `{labeler_path.relative_to(ROOT).as_posix()}` (open in a browser).",
        f"- Blind CSV (same rows, blank labels): `{blind_path.relative_to(ROOT).as_posix()}`.",
        f"- Manifest (weights, strata, split): `{manifest_path.relative_to(ROOT).as_posix()}`",
        "  - not for labelers.",
        "- **No overlap file is built yet**; it is built from the returned export under ADR-0023",
        "  Amendment C.",
        "",
        "## Limits",
        "",
        "- Counts are conditioned on the P1 citer set; 5,734 eligible citers were truncated by the",
        "  corpus cap, so rates from this packet understate the true blast radius.",
        "- Expected labeling time is arithmetic at 20-45 s/row: 50-112 minutes for 150 rows.",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
