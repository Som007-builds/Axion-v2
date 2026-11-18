"""Draw the P3-03 gold dependency-audit packet (wave 1), deterministically.

The audit needs an unbiased base rate *and* enough positives to estimate
recall, which one sample cannot do at this prevalence. Wave 1 therefore mixes
two frames: a uniform random slice (unbiased, wide) and a cue-enriched sample
(power, biased) with the inclusion probability recorded on every row so later
metrics can be weighted. The dev/test split is assigned by retracted source
paper before any detector exists, and waves draw from the remaining pool so a
wave 2 never invalidates wave 1.

The agent creates no labels here: every label field is written blank.

Usage:
    python scripts/dependency_sample.py
    python scripts/dependency_sample.py --rebuild   # re-parse the corpus cache
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

from axion.eval.audit import wilson_interval
from axion.ingest.corpus import read_cites_csv, read_manifest, read_papers_csv
from axion.link.candidates import build_candidates
from axion.parse.jats import JatsParseError, parse_jats_file

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "reports" / "P1-corpus-manifest.json"
FULLTEXT = ROOT / "data" / "raw" / "europepmc"
WORK = ROOT / "data" / "p3-03"
OUT = ROOT / "eval" / "audit" / "p3-03"
TEMPLATE = ROOT / "docs" / "eval" / "audit_labeler_template.html"
REPORT = ROOT / "docs" / "reports" / "P3-03-wave1-packet.md"
PILOT_CSV = ROOT / "eval" / "audit" / "dependency_pilot_v1_labelled.csv"

SEED = 20261119
WAVE_ID = "wave1"
WAVE_SIZE = 150
UNIFORM_N = 30
ENRICHED_N = 120
SOURCE_CAP = 8  # ceil(5% of a 150-row wave)
OVERLAP_N = 30  # 20% of the wave
OVERLAP_ENRICHED = 24
OVERLAP_UNIFORM = 6
GUIDELINE_VERSION = "P3-v1.1"

CUE_PATTERNS: dict[str, str] = {
    # Cues for "B uses A as an input", not for "B mentions A". A bare digit was
    # rejected: it fires on 99.8% of contexts and would enrich nothing.
    "we_used": (
        r"\bwe\s+(use|used|adopt|adopted|apply|applied|follow|followed|employ|employed"
        r"|obtain|obtained|take|took|select|selected|include|included|derive|derived)"
    ),
    "based_on": (
        r"\b(based on|building on|derived from|following (the|their)"
        r"|according to (the|their)|adapted from|as described (by|in))\b"
    ),
    "numeric_effect": (
        r"\b\d+(\.\d+)?\s*(%|percent|fold|log\d*|times)\b"
        r"|\br\s*=\s*0?\.\d+|\bp\s*[<=]\s*0?\.\d+"
    ),
    "comparison": (
        r"\b(compared (with|to)|in line with|consistent with" r"|in agreement with|likewise)\b"
    ),
    "method_word": (
        r"\b(method|methods|assay|protocol|model|cohort|dataset" r"|software|package|tool)\b"
    ),
    "inference_connector": (
        r"\b(therefore|thus|hence|consequently|accordingly|given that"
        r"|because of (this|these))\b"
    ),
    "prior_finding": (
        r"\b(this finding|these findings|that study|prior work (found|showed)"
        r"|previous stud(y|ies) (found|reported|showed))\b"
    ),
}
NEGATIVE_CUES = {"retraction_marker"}
ALL_CUE_PATTERNS = {
    **CUE_PATTERNS,
    "retraction_marker": r"\b(retract\w*|withdrawn|expression of concern)\b",
}

MANIFEST_COLUMNS = (
    "row_id",
    "ctx_id",
    "citer_pmcid",
    "source_pmcid",
    "section",
    "section_bucket",
    "frame",
    "stratum",
    "inclusion_prob",
    "weight",
    "cue_score",
    "cues",
    "linked",
    "split",
    "overlap",
)
BLIND_COLUMNS = (
    "row_id",
    "citer_pmcid",
    "citer_title",
    "source_pmcid",
    "source_title",
    "source_pmid",
    "source_doi",
    "retraction_record_ids",
    "context_text",
    "paragraph_text",
    "section",
    "marker",
    "linked",
    "source_claim_text",
    "source_abstract",
    "label",
    "note",
    "labeler",
    "date",
    "guideline_version",
)


def _section_bucket(section: str) -> str:
    text = (section or "").lower()
    for key, bucket in (
        ("method", "Methods"),
        ("result", "Results"),
        ("discussion", "Discussion"),
        ("introduction", "Introduction"),
        ("background", "Introduction"),
        ("conclusion", "Conclusion"),
    ):
        if key in text:
            return bucket
    return "Other" if text.strip() else "Unsectioned"


def _cues(text: str) -> tuple[list[str], int]:
    fired = [name for name, pattern in CUE_PATTERNS.items() if re.search(pattern, text, re.I)]
    score = len(fired)
    return fired, score


def _load_bundle(rebuild: bool) -> tuple[list[dict], list[dict], list[dict]]:
    manifest = read_manifest(MANIFEST)
    cache_path = WORK / "candidates.json"
    if cache_path.exists() and not rebuild:
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("config_sha256") == manifest.config_sha256:
            return cached["context_rows"], cached["paper_rows"], cached["claim_rows"]
    papers = read_papers_csv(MANIFEST.parent / Path(manifest.files.papers_csv).name)
    cites = read_cites_csv(MANIFEST.parent / Path(manifest.files.cites_csv).name)
    bundle = build_candidates(
        papers,
        cites,
        cache_dir=FULLTEXT,
        expected_contexts=manifest.counts.contexts_total,
    )
    WORK.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(
        json.dumps(
            {
                "config_sha256": manifest.config_sha256,
                "context_rows": list(bundle.context_rows),
                "paper_rows": list(bundle.paper_rows),
                "claim_rows": list(bundle.source_claim_rows),
            }
        ),
        encoding="utf-8",
    )
    return list(bundle.context_rows), list(bundle.paper_rows), list(bundle.source_claim_rows)


def _abstract_text(pmcid: str, cache_dir: Path, parsed: dict) -> str:
    if pmcid in parsed:
        return parsed[pmcid]
    text = ""
    try:
        paper = parse_jats_file(cache_dir / "fulltext" / f"{pmcid}.xml", paper_id=pmcid)
    except (JatsParseError, OSError):
        paper = None
    if paper is not None:
        for section in paper.sections:
            if "abstract" in (section.title or "").lower():
                joined = " ".join(p.text for p in section.paragraphs)
                text = " ".join(joined.split())[:1200]
                break
    parsed[pmcid] = text
    return text


def _assign_splits(contexts_by_source: dict[str, int], seed: int) -> dict[str, str]:
    """Assign whole source papers to dev/test, balanced by context count.

    Ties break on a seeded hash, so the split is reproducible and independent of
    anything a detector does later.
    """
    order = sorted(
        contexts_by_source,
        key=lambda pmcid: hashlib.sha256(f"{seed}:{pmcid}".encode()).hexdigest(),
    )
    totals = {"dev": 0, "test": 0}
    split: dict[str, str] = {}
    for pmcid in sorted(order, key=lambda p: (-contexts_by_source[p], p)):
        target = "dev" if totals["dev"] <= totals["test"] else "test"
        split[pmcid] = target
        totals[target] += contexts_by_source[pmcid]
    return split


def _uniform(rows: list[dict], n: int, rng: random.Random, cap: int) -> list[dict]:
    pool = list(rows)
    rng.shuffle(pool)
    chosen: list[dict] = []
    per_source: Counter[str] = Counter()
    for row in pool:
        if per_source[row["source_pmcid"]] >= cap:
            continue
        chosen.append(row)
        per_source[row["source_pmcid"]] += 1
        if len(chosen) == n:
            break
    return chosen


def _quotas(sizes: dict[str, int], n: int) -> dict[str, int]:
    total = sum(sizes.values())
    raw = {bucket: n * size / total for bucket, size in sizes.items()}
    quota = {bucket: int(math.floor(value)) for bucket, value in raw.items()}
    remaining = n - sum(quota.values())
    ranked = sorted(raw, key=lambda b: (-(raw[b] - quota[b]), b))
    for bucket in ranked[:remaining]:
        quota[bucket] += 1
    return quota


def _enriched(pool: list[dict], n: int, rng: random.Random, cap: int) -> list[dict]:
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for row in pool:
        by_bucket[row["section_bucket"]].append(row)
    quota = _quotas({b: len(v) for b, v in by_bucket.items()}, n)
    chosen: list[dict] = []
    per_source: Counter[str] = Counter()
    leftovers: list[dict] = []
    for bucket in sorted(by_bucket):
        items = list(by_bucket[bucket])
        rng.shuffle(items)
        need = quota[bucket]
        for row in items:
            if need == 0:
                break
            if per_source[row["source_pmcid"]] >= cap:
                leftovers.append(row)
                continue
            chosen.append(row)
            per_source[row["source_pmcid"]] += 1
            need -= 1
    if len(chosen) < n:
        for row in leftovers:
            if len(chosen) >= n:
                break
            if per_source[row["source_pmcid"]] >= cap:
                continue
            chosen.append(row)
            per_source[row["source_pmcid"]] += 1
    return chosen


def _overlap(enriched: list[dict], uniform: list[dict]) -> list[dict]:
    pick = sorted(
        enriched,
        key=lambda r: (
            -r["cue_score"],
            hashlib.sha256(f"{SEED}:{r['ctx_id']}".encode()).hexdigest(),
        ),
    )[:OVERLAP_ENRICHED]
    step = max(len(uniform) // OVERLAP_UNIFORM, 1)
    picked = pick + uniform[::step][:OVERLAP_UNIFORM]
    return picked


def _write_csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def _labeler_html(
    template: str,
    *,
    title: str,
    subtitle: str,
    set_key: str,
    export_name: str,
    default_labeler: str,
    rows: list[dict],
) -> str:
    packet = {"columns": list(BLIND_COLUMNS), "rows": rows}
    data = json.dumps(packet, ensure_ascii=False).replace("</", "<\\/")
    return (
        template.replace("__TITLE__", title)
        .replace("__SUBTITLE__", subtitle)
        .replace("__SET_KEY__", set_key)
        .replace("__EXPORT_NAME__", export_name)
        .replace("__DEFAULT_LABELER__", default_labeler)
        .replace("__DATA_JSON__", data)
    )


def _pilot_cue_table(contexts: list[dict]) -> list[str]:
    if not PILOT_CSV.exists():
        return ["Pilot cross-tab unavailable (labelled pilot CSV not found)."]
    with PILOT_CSV.open(encoding="utf-8-sig", newline="") as handle:
        pilot = list(csv.DictReader(handle))
    lines = ["| Cue | Pilot rows firing | of which `RELIES_ON` |", "| :-- | --: | --: |"]
    for name in (*CUE_PATTERNS, "retraction_marker"):
        fired = [
            row
            for row in pilot
            if re.search(ALL_CUE_PATTERNS[name], row.get("context_text", ""), re.I)
        ]
        positive = sum(1 for row in fired if row.get("label") == "RELIES_ON")
        lines.append(f"| `{name}` | {len(fired)} | {positive} |")
    return lines


def _power_table() -> list[str]:
    lines = [
        "| RELIES_ON positives | recall 0.80: Wilson interval | recall 0.85: Wilson interval |",
        "| --: | :-- | :-- |",
    ]
    for positives in (10, 15, 20, 30, 40, 60, 100):
        cells = []
        for observed in (0.80, 0.85):
            low, high = wilson_interval(round(observed * positives), positives)
            cells.append(f"{low:.3f}-{high:.3f}")
        lines.append(f"| {positives} | {cells[0]} | {cells[1]} |")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--rebuild", action="store_true", help="re-parse instead of using the cache"
    )
    args = parser.parse_args(argv)

    contexts, papers, claims = _load_bundle(args.rebuild)
    paper_by_id = {row["pmcid"]: row for row in papers}
    claim_text = {row["claim_id"]: row["text"] for row in claims}
    source_ids = sorted({row["source_pmcid"] for row in contexts})
    parsed_abstracts: dict[str, str] = {}

    manifest = read_manifest(MANIFEST)
    corpus_papers = read_papers_csv(MANIFEST.parent / Path(manifest.files.papers_csv).name)
    rw_by_pmcid = {paper.pmcid: ";".join(paper.rw_record_ids) for paper in corpus_papers}

    for row in contexts:
        row["section_bucket"] = _section_bucket(row["section"])
        fired, score = _cues(row["text"])
        row["cues"] = ";".join(fired)
        row["cue_score"] = score
        row["linked"] = "true" if row["source_claim_id"] else "false"

    by_source_counts = Counter(row["source_pmcid"] for row in contexts)
    split = _assign_splits(by_source_counts, SEED)

    uniform = _uniform(contexts, UNIFORM_N, random.Random(SEED + 1), SOURCE_CAP)
    uniform_ids = {row["ctx_id"] for row in uniform}
    enriched_pool = [
        row for row in contexts if row["cue_score"] > 0 and row["ctx_id"] not in uniform_ids
    ]
    enriched = _enriched(enriched_pool, ENRICHED_N, random.Random(SEED + 2), SOURCE_CAP)
    overlap_ids = {row["ctx_id"] for row in _overlap(enriched, uniform)}

    bucket_pool = Counter(row["section_bucket"] for row in contexts)
    bucket_enriched_pool = Counter(row["section_bucket"] for row in enriched_pool)
    bucket_uniform = Counter(row["section_bucket"] for row in uniform)
    bucket_enriched = Counter(row["section_bucket"] for row in enriched)

    wave: list[dict] = []
    for row in uniform + enriched:
        if any(existing["ctx_id"] == row["ctx_id"] for existing in wave):
            continue
        frame = "uniform" if any(row is u for u in uniform) else "enriched"
        bucket = row["section_bucket"]
        if frame == "uniform":
            prob = len(uniform) / len(contexts)
        else:
            prob = bucket_enriched[bucket] / bucket_enriched_pool[bucket]
        wave.append(
            {
                "ctx_id": row["ctx_id"],
                "citer_pmcid": row["citer_pmcid"],
                "source_pmcid": row["source_pmcid"],
                "section": row["section"],
                "section_bucket": bucket,
                "frame": frame,
                "stratum": bucket if frame == "enriched" else "uniform",
                "inclusion_prob": round(prob, 8),
                "weight": round(1 / prob, 4),
                "cue_score": row["cue_score"],
                "cues": row["cues"],
                "linked": row["linked"],
                "split": split[row["source_pmcid"]],
                "overlap": "true" if row["ctx_id"] in overlap_ids else "false",
            }
        )
    if len(wave) != WAVE_SIZE:
        raise SystemExit(
            f"wave is {len(wave)} rows, expected {WAVE_SIZE}: "
            f"uniform {len(uniform)}, enriched {len(enriched)}"
        )
    wave.sort(key=lambda row: (row["split"], row["source_pmcid"], row["ctx_id"]))
    for number, row in enumerate(wave, start=1):
        row["row_id"] = f"P3W1-{number:03d}"

    blind: list[dict] = []
    for row in wave:
        ctx = next(c for c in contexts if c["ctx_id"] == row["ctx_id"])
        citer = paper_by_id.get(ctx["citer_pmcid"], {})
        source = paper_by_id.get(ctx["source_pmcid"], {})
        linked = row["linked"] == "true"
        blind.append(
            {
                "row_id": row["row_id"],
                "citer_pmcid": ctx["citer_pmcid"],
                "citer_title": citer.get("title") or "",
                "source_pmcid": ctx["source_pmcid"],
                "source_title": source.get("title") or "",
                "source_pmid": source.get("pmid") or "",
                "source_doi": source.get("doi") or "",
                "retraction_record_ids": rw_by_pmcid.get(ctx["source_pmcid"], ""),
                "context_text": ctx["text"],
                "paragraph_text": ctx["paragraph_text"],
                "section": ctx["section"],
                "marker": ctx["marker"],
                "linked": row["linked"],
                "source_claim_text": claim_text.get(ctx["source_claim_id"], "") if linked else "",
                "source_abstract": ""
                if linked
                else _abstract_text(ctx["source_pmcid"], FULLTEXT, parsed_abstracts),
                "label": "",
                "note": "",
                "labeler": "",
                "date": "",
                "guideline_version": GUIDELINE_VERSION,
            }
        )

    OUT.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT / f"p3-03-{WAVE_ID}-manifest.csv"
    blind_path = OUT / f"p3-03-{WAVE_ID}-blind.csv"
    overlap_path = OUT / f"p3-03-{WAVE_ID}-overlap-blind.csv"
    _write_csv(manifest_path, MANIFEST_COLUMNS, wave)
    _write_csv(blind_path, BLIND_COLUMNS, blind)
    overlap_rows = [
        row
        for row in blind
        if any(m["row_id"] == row["row_id"] and m["overlap"] == "true" for m in wave)
    ]
    _write_csv(overlap_path, BLIND_COLUMNS, overlap_rows)

    template = TEMPLATE.read_text(encoding="utf-8")
    full_html = _labeler_html(
        template,
        title="P3-03 wave 1 dependency audit",
        subtitle=(
            "Blind review: no model output, weights or strata are shown. "
            "Label each context-source edge."
        ),
        set_key="axion-p3-03-wave1-full",
        export_name="dependency_audit_v1_wave1_labelled.csv",
        default_labeler="Soham",
        rows=blind,
    )
    overlap_html = _labeler_html(
        template,
        title="P3-03 wave 1 second-labeler overlap",
        subtitle=(
            "Blind overlap set for an independent labeler. "
            "Enter your own labeler id before exporting."
        ),
        set_key="axion-p3-03-wave1-overlap",
        export_name="dependency_audit_v1_wave1_overlap_labelled.csv",
        default_labeler="",
        rows=overlap_rows,
    )
    full_path = OUT / "p3-03-wave1-labeler.html"
    overlap_html_path = OUT / "p3-03-wave1-overlap-labeler.html"
    full_path.write_text(full_html, encoding="utf-8", newline="\n")
    overlap_html_path.write_text(overlap_html, encoding="utf-8", newline="\n")

    pilot_rate = 0.10
    pilot_low, pilot_high = wilson_interval(2, 20)
    cue_pilot_total = 0
    cue_pilot_positive = 0
    if PILOT_CSV.exists():
        with PILOT_CSV.open(encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                fired, _ = _cues(row.get("context_text", ""))
                if fired:
                    cue_pilot_total += 1
                    cue_pilot_positive += 1 if row.get("label") == "RELIES_ON" else 0
    # No measured lift yet: if the pilot has no cue-positive row, assume none.
    enriched_rate = cue_pilot_positive / cue_pilot_total if cue_pilot_total else pilot_rate

    expected_uniform = UNIFORM_N * pilot_rate
    expected_enriched = ENRICHED_N * enriched_rate
    split_rows = Counter(row["split"] for row in wave)
    split_sources = {
        name: len({r["source_pmcid"] for r in wave if r["split"] == name})
        for name in ("dev", "test")
    }
    split_contexts = {
        name: sum(count for pmcid, count in by_source_counts.items() if split[pmcid] == name)
        for name in ("dev", "test")
    }
    capped = [
        pmcid
        for pmcid, count in Counter(r["source_pmcid"] for r in wave).items()
        if count >= SOURCE_CAP
    ]
    linked_share = sum(1 for row in wave if row["linked"] == "true") / len(wave)
    unlinked = [row for row in blind if row["linked"] == "false"]
    unlinked_with_abstract = sum(1 for row in unlinked if row["source_abstract"])

    capped_preview = ", ".join(f"`{p}`" for p in sorted(capped)[:6])
    capped_tail = " ..." if len(capped) > 6 else ""
    lines = [
        "# P3-03 wave 1 packet - design and expected yield",
        "",
        "**Status:** packet ready; **no labels created**. Generated by "
        "`python scripts/dependency_sample.py`; every number below is its output.",
        "",
        f"**Seed:** `{SEED}` · **Wave:** {len(wave)} rows · "
        f"**Guideline:** `{GUIDELINE_VERSION}` · "
        f"**Candidate pool:** {len(contexts):,} contexts over {len(source_ids)} source papers.",
        "",
        "## Two frames, on purpose",
        "",
        "| Frame | Rows | Inclusion probability | Weight | Purpose |",
        "| :-- | --: | :-- | --: | :-- |",
        f"| Uniform random | {len(uniform)} | {len(uniform)}/{len(contexts):,} = "
        f"{len(uniform) / len(contexts):.6f} | {len(contexts) / len(uniform):.1f} | "
        "unbiased base rate |",
        f"| Cue-enriched, stratified by section | {len(enriched)} | "
        f"{'per-stratum n/N' if bucket_enriched_pool else 'n/a'} | per row in manifest | "
        "positives for recall |",
        "",
        "Per-source cap: **"
        f"{SOURCE_CAP} rows** (5% of a 150-row wave). Sources hitting the cap: **{len(capped)}**"
        f" ({capped_preview}{capped_tail}).",
        "",
        "## Strata",
        "",
        "| Section bucket | Pool | Cue-positive pool | Uniform drawn | Enriched drawn |",
        "| :-- | --: | --: | --: | --: |",
    ]
    for bucket in sorted(bucket_pool):
        lines.append(
            f"| {bucket} | {bucket_pool[bucket]} | {bucket_enriched_pool.get(bucket, 0)} | "
            f"{bucket_uniform.get(bucket, 0)} | {bucket_enriched.get(bucket, 0)} |"
        )
    lines += [
        "",
        "## Split (by source paper, frozen now)",
        "",
        "| Split | Source papers | Candidate contexts | Wave rows |",
        "| :-- | --: | --: | --: |",
        f"| dev | {split_sources['dev']} | {split_contexts['dev']} | {split_rows['dev']} |",
        f"| test | {split_sources['test']} | {split_contexts['test']} | {split_rows['test']} |",
        "",
        "The assignment covers **all** sources, not just sampled ones, so later waves inherit it",
        "and no context can move split. Nothing is tuned on test.",
        "",
        "## Linked vs unlinked",
        "",
        f"Wave rows with a source-claim pointer: **{linked_share:.1%}** "
        f"({sum(1 for r in wave if r['linked'] == 'true')}/{len(wave)}). Unlinked rows are "
        "kept and show the source abstract instead of a single claim, because dropping them",
        "would truncate a third of the candidate frame and bias prevalence. Claim-linking",
        "accuracy (P3-06) is reported on linked rows only.",
        "",
        f"Of the {len(unlinked)} unlinked rows, {unlinked_with_abstract} show the source abstract",
        f"and {len(unlinked) - unlinked_with_abstract} have no abstract at all: those come from",
        "retracted/withdrawn stub articles that carry a title and no abstract element. They stay",
        "in the set because retraction-notice contexts are the `UNRELATED`/`MENTIONS` edge cases",
        "the audit must cover; the labeler says plainly that no claim or abstract exists.",
        "",
        "## Cue prevalence (all " f"{len(contexts):,} contexts)",
        "",
        "| Cue | Contexts firing | Share |",
        "| :-- | --: | --: |",
    ]
    for name, pattern in ALL_CUE_PATTERNS.items():
        fired = sum(1 for row in contexts if re.search(pattern, row["text"], re.I))
        lines.append(f"| `{name}` | {fired:,} | {fired / len(contexts):.1%} |")
    lines += [
        "",
        "Positive cues are the five above except `retraction_marker`, which is a negative cue kept",
        "so retraction notices are not silently excluded from the enriched frame.",
        "",
        "**The cues are unvalidated.** No cue separates `RELIES_ON` from `MENTIONS` in the 20-row",
        'pilot, so enrichment is a bet that "we used / based on / a numeric effect / an inference',
        "connector\" raises the base rate. Wave 1's uniform frame is the control that measures",
        "whether it did; if the lift is near zero, wave 2 should shift rows to the uniform frame",
        "and treat the cue score as a stratification variable rather than a positive filter.",
        "",
        "### Pilot cross-tab (n=20, calibration only)",
        "",
        *_pilot_cue_table(contexts),
        "",
        "## Expected positives in wave 1 (assumption, not a measurement)",
        "",
        f"- Uniform slice: {UNIFORM_N} x {pilot_rate:.0%} pilot base rate = "
        f"**{expected_uniform:.1f}** (pilot Wilson 95% [{pilot_low:.1%}, {pilot_high:.1%}]"
        f" gives {UNIFORM_N * pilot_low:.1f} to {UNIFORM_N * pilot_high:.1f}).",
        f"- Enriched frame: {ENRICHED_N} x {enriched_rate:.1%} (pilot cue-positive rows that",
        f"  were `RELIES_ON`: {cue_pilot_positive}/{cue_pilot_total}) = "
        f"**{expected_enriched:.1f}**.",
        f"- **Total expected `RELIES_ON` ~{expected_uniform + expected_enriched:.0f}** "
        f"(~{(expected_uniform + expected_enriched) / len(wave):.1%} of the wave).",
        "- The enriched rate rests on a handful of pilot rows; treat it as a planning",
        "  assumption until wave-1 labels replace it.",
        "- Scenario: if enrichment lifts the rate to 15% (an unmeasured assumption), the",
        f"  enriched frame would add ~{ENRICHED_N * 0.15:.0f} and the wave would yield",
        f"  ~{UNIFORM_N * pilot_rate + ENRICHED_N * 0.15:.0f} positives. The pilot's own reading",
        "  (0 of 3 cue-positive rows positive) is the low end, which is why wave 1 is treated as",
        "  a measurement of the cues rather than as a recall estimate.",
        "",
        "## How many positives a recall claim needs",
        "",
        *_power_table(),
        "",
        "Reading: with ~15 positives, an observed recall of 0.85 still has a Wilson lower bound",
        "near 0.55 - it cannot certify the gate's >=0.70. Around **40-60 positives** the interval",
        "stops straddling the gate. Wave 1 is sized for ~25-35; that supports a decision-grade",
        "read, not a certified one, which is why waves 2+ exist.",
        "",
        "## Overlap set for the second labeler",
        "",
        f"**{len(overlap_rows)} rows (20% of the wave)**, {OVERLAP_ENRICHED} cue-enriched + "
        f"{OVERLAP_UNIFORM} uniform, exported as a separate blind packet. Enrichment is what makes "
        "`RELIES_ON` and `UNRELATED` present often enough for kappa to mean anything; kappa",
        "from an enriched overlap is prevalence-specific and is not the corpus kappa. If a class",
        "is still absent after labelling, the owner tops up from the remaining pool (<=10 rows)",
        "rather than reusing these.",
        "",
        "## Labeling time (pilot pace not recorded)",
        "",
        f"{len(wave)} rows at 20 s / 30 s / 45 s per row = "
        f"**{len(wave) * 20 / 60:.0f} / {len(wave) * 30 / 60:.0f} / "
        f"{len(wave) * 45 / 60:.0f} minutes**. The P3-01 pilot did not record a duration, so",
        "this is an arithmetic estimate from a stated assumption, not a measurement; the second",
        f"labeler has {len(overlap_rows)} rows (~{len(overlap_rows) * 30 / 60:.0f} min at 30 s).",
        "",
        "## Files",
        "",
        f"- **Label this:** `{full_path.relative_to(ROOT).as_posix()}` (open in a browser).",
        f"- Second labeler: `{overlap_html_path.relative_to(ROOT).as_posix()}`.",
        f"- Blind packet (same rows, CSV): `{blind_path.relative_to(ROOT).as_posix()}`.",
        f"- Internal manifest (weights, strata, cues, split): "
        f"`{manifest_path.relative_to(ROOT).as_posix()}` — **not** for labelers.",
        "",
        "## Limits",
        "",
        "- The per-source cap makes the enriched design weights approximate; the manifest records",
        "  nominal probabilities, and capped sources are listed above so the effect is checkable.",
        "- The 20-row pilot is edge-case-enriched, so its 10% base rate is a calibration figure.",
        "- Contexts are the P1 in-corpus citer set only; 5,734 eligible citers were truncated by",
        "  the corpus cap, so this frame is a lower bound on the true blast radius.",
        "",
    ]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    summary = {
        "seed": SEED,
        "wave_rows": len(wave),
        "uniform_rows": len(uniform),
        "enriched_rows": len(enriched),
        "overlap_rows": len(overlap_rows),
        "sources": len(source_ids),
        "contexts": len(contexts),
        "split_rows": dict(split_rows),
        "linked_share": round(linked_share, 4),
        "expected_positives": round(expected_uniform + expected_enriched, 2),
    }
    (OUT / "p3-03-wave1-sampling.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
