"""P3-06 oracle packet: can the detector get better if the *source sentence* is right?

P3-05 measured dependency with the abstract-sentence proxy P3-02 gave it. The P3-06 diagnosis
showed a body sentence matches the citing text clearly better for 68.8% of rows. This builds the
packet that tests whether that matters.

Contents, dev only, text-bearing frame:

- **every text-bearing dev positive** (14 of them) plus **16 seeded, section-stratified negatives**
  = 30 rows;
- a **blind** CSV and labeler for the owner: citing sentence, surrounding paragraph, and the
  source paper's numbered **body** sentences as candidates;
- a **separate manifest** holding the gold labels and the id mapping, which the labeler never sees;
- a **10-row overlap** copy in its own handoff directory for the second labeler.

No model is called, no label is created here, and the frozen test set is not touched.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from axion.parse.jats import parse_jats_file, split_sentences
from scripts.dependency_baselines import POSITIVE, load_rows, scored_rows, spec_rows

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "audit" / "p3-06-oracle"
OVERLAP = ROOT / "eval" / "audit" / "p3-06-oracle-labeler2"
FULLTEXT = ROOT / "data" / "raw" / "europepmc" / "fulltext"
MANIFESTS = (
    ROOT / "eval" / "audit" / "p3-03" / "p3-03-wave1-manifest.csv",
    ROOT / "eval" / "audit" / "p3-03" / "p3-03-wave2-manifest.csv",
)

SEED = 20261120
POSITIVES = 14  # every text-bearing dev positive
NEGATIVES = 16
TOTAL = POSITIVES + NEGATIVES
OVERLAP_SIZE = 10
MAX_CANDIDATES = 40
PREFERRED_SECTIONS = ("result", "finding", "method", "material", "experiment")

BLIND_FIELDS = (
    "opaque_id",
    "source_title",
    "citing_sentence",
    "surrounding_paragraph",
    "candidates_json",
)
MANIFEST_FIELDS = (
    "opaque_id",
    "row_id",
    "gold_label",
    "section",
    "section_bucket",
    "wave",
    "source_pmcid",
    "body_sentences_total",
    "candidates_shown",
    "truncated",
    "no_source_body",
    "overlap",
)


class PacketError(Exception):
    """The packet cannot be built as specified."""


def read_manifests(paths: Sequence[Path] = MANIFESTS) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for path in paths:
        if not path.exists():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                rows[row["row_id"]] = row
    return rows


def section_rank(title: str) -> int:
    lowered = (title or "").lower()
    for rank, needle in enumerate(PREFERRED_SECTIONS):
        if needle in lowered:
            return rank
    return len(PREFERRED_SECTIONS)


def body_sentences(pmcid: str, fulltext: Path = FULLTEXT) -> list[tuple[str, str]]:
    """Body sentences of the source paper as (section title, sentence), abstract excluded."""
    path = fulltext / f"{pmcid}.xml"
    if not path.exists() or not pmcid:
        return []
    paper = parse_jats_file(path, paper_id=pmcid)
    collected: list[tuple[str, str]] = []
    for section in paper.sections:
        if (section.title or "").strip().lower().startswith("abstract"):
            continue
        for paragraph in section.paragraphs:
            collected.extend(
                (section.title or "Unsectionsed", s) for s in split_sentences(paragraph.text)
            )
    return collected


def choose_candidates(
    sentences: Sequence[tuple[str, str]], limit: int = MAX_CANDIDATES
) -> list[str]:
    """Prefer results/methods, keep document order inside a section, cap the reading load."""
    ordered = sorted(
        enumerate(sentences),
        key=lambda item: (section_rank(item[1][0]), item[0]),
    )
    chosen = sorted(index for index, _ in ordered[:limit])
    return [sentences[index][1] for index in chosen]


def stratified_negatives(
    negatives: Sequence[dict[str, str]], count: int, seed: int
) -> list[dict[str, str]]:
    """Seeded allocation across section buckets, largest remainder, then seeded choice."""
    buckets: dict[str, list[dict[str, str]]] = {}
    for row in negatives:
        buckets.setdefault(row["section_bucket"], []).append(row)
    total = len(negatives)
    quotas = {bucket: count * len(group) / total for bucket, group in buckets.items()}
    base = {bucket: int(value) for bucket, value in quotas.items()}
    remainder = count - sum(base.values())
    for bucket in sorted(quotas, key=lambda name: (-(quotas[name] - base[name]), name)):
        if remainder <= 0:
            break
        base[bucket] += 1
        remainder -= 1

    agent = random.Random(seed)
    picked: list[dict[str, str]] = []
    for bucket in sorted(buckets):
        group = sorted(buckets[bucket], key=lambda row: row["row_id"])
        take = min(base.get(bucket, 0), len(group))
        picked.extend(agent.sample(group, take))
    if len(picked) < count:
        leftover = [
            row for row in sorted(negatives, key=lambda row: row["row_id"]) if row not in picked
        ]
        picked.extend(leftover[: count - len(picked)])
    return sorted(picked, key=lambda row: row["row_id"])


def overlap_ids(
    rows: Sequence[dict[str, str]],
    manifests: dict[str, dict[str, str]],
    seed: int,
    testable: set[str] | None = None,
) -> list[str]:
    """Ten rows, seeded, guaranteed to contain at least one positive and one negative."""
    usable = [row for row in rows if testable is None or row["row_id"] in testable]
    positives = [row["row_id"] for row in usable if row["label"] == POSITIVE]
    negatives = [row["row_id"] for row in usable if row["label"] != POSITIVE]
    if not positives or not negatives:
        raise PacketError("the packet must contain positives and negatives for the overlap")
    wanted_pos = min(5, len(positives))
    wanted_neg = OVERLAP_SIZE - wanted_pos
    agent = random.Random(seed + 1)
    chosen = agent.sample(positives, wanted_pos)
    chosen += agent.sample(negatives, min(wanted_neg, len(negatives)))
    return sorted(chosen)


def build(
    rows: Sequence[dict[str, str]], manifests: dict[str, dict[str, str]], *, seed: int = SEED
) -> dict[str, object]:
    text_bearing = [row for row in rows if row["frame"] == "text_bearing"]
    positives = [row for row in text_bearing if row["label"] == POSITIVE]
    negatives = [row for row in text_bearing if row["label"] != POSITIVE]
    if len(positives) != POSITIVES:
        raise PacketError(
            f"expected {POSITIVES} text-bearing dev positives, found {len(positives)}; "
            "the packet is defined against the current dev split"
        )
    # Negatives are drawn only from sources that have body text, because a row with no
    # candidate sentences cannot test the oracle. This is a disclosed selection: negatives
    # here come from fuller source papers than the frame average.
    with_body = [
        row
        for row in negatives
        if body_sentences(manifests.get(row["row_id"], {}).get("source_pmcid", ""))
    ]
    sampled_negatives = stratified_negatives(with_body, NEGATIVES, seed)
    selected = sorted(positives + sampled_negatives, key=lambda row: row["row_id"])

    agent = random.Random(seed + 2)
    order = list(selected)
    agent.shuffle(order)

    blind: list[dict[str, object]] = []
    manifest: list[dict[str, object]] = []
    candidates_by_opaque: dict[str, list[str]] = {}
    for index, row in enumerate(order, start=1):
        opaque = f"O-{index:02d}"
        pmcid = manifests.get(row["row_id"], {}).get("source_pmcid", "")
        sentences = body_sentences(pmcid)
        candidates = choose_candidates(sentences)
        # A few source papers are retracted or withdrawn to the point of having no parseable
        # body. They stay in the packet (every positive must be represented) but are marked,
        # because the oracle cannot replace a proxy with a sentence that does not exist.
        candidates_by_opaque[opaque] = candidates
        blind.append(
            {
                "opaque_id": opaque,
                "source_title": row["source_title"],
                "citing_sentence": row["context_text"],
                "surrounding_paragraph": row.get("paragraph_text", ""),
                "candidates_json": json.dumps(candidates, ensure_ascii=False),
            }
        )
        manifest.append(
            {
                "opaque_id": opaque,
                "row_id": row["row_id"],
                "gold_label": row["label"],
                "section": row["section"],
                "section_bucket": row["section_bucket"],
                "wave": row["wave"],
                "source_pmcid": pmcid,
                "body_sentences_total": len(sentences),
                "candidates_shown": len(candidates),
                "truncated": "true" if len(sentences) > len(candidates) else "false",
                "no_source_body": "true" if not candidates else "false",
            }
        )

    testable = {item["row_id"] for item in manifest if item["no_source_body"] != "true"}
    overlap = overlap_ids(selected, manifests, seed, testable)
    by_row = {item["row_id"]: item for item in manifest}
    for item in manifest:
        item["overlap"] = "true" if item["row_id"] in overlap else "false"

    return {
        "seed": SEED,
        "rows": len(selected),
        "positives": len(positives),
        "negatives": len(sampled_negatives),
        "negatives_by_section": dict(Counter(row["section_bucket"] for row in sampled_negatives)),
        "blind": blind,
        "manifest": manifest,
        "overlap_row_ids": overlap,
        "overlap_opaque": sorted(by_row[row_id]["opaque_id"] for row_id in overlap),
        "candidates_by_opaque": candidates_by_opaque,
        "packet_hash": hashlib.sha256(
            json.dumps([item["row_id"] for item in selected], sort_keys=True).encode("utf-8")
        ).hexdigest()[:16],
    }


def write_csv(path: Path, fields: Sequence[str], rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def blind_rows(
    summary: dict[str, object], opaque_ids: Sequence[str] | None = None
) -> list[dict[str, object]]:
    keep = set(opaque_ids) if opaque_ids is not None else None
    return [
        row
        for row in summary["blind"]  # type: ignore[index]
        if keep is None or row["opaque_id"] in keep
    ]


def labeler_html(
    rows: Sequence[dict[str, object]], *, title: str, storage_key: str, download: str
) -> str:
    payload = json.dumps(list(rows), ensure_ascii=False)
    template = (ROOT / "docs" / "eval" / "link_oracle_labeler_template.html").read_text(
        encoding="utf-8"
    )
    return (
        template.replace("__TITLE__", title)
        .replace("__STORAGE_KEY__", storage_key)
        .replace("__DOWNLOAD__", download)
        .replace("__ROWS_JSON__", payload)
    )


def readme(summary: dict[str, object]) -> str:
    """The packet's instructions, from a template so a rebuild never loses them."""
    template = (ROOT / "docs" / "eval" / "p3_06_oracle_readme_template.md").read_text(
        encoding="utf-8"
    )
    replacements = {
        "__ROWS__": summary["rows"],
        "__POSITIVES__": summary["positives"],
        "__NEGATIVES__": summary["negatives"],
        "__SEED__": summary["seed"],
        "__HASH__": summary["packet_hash"],
    }
    for token, value in replacements.items():
        template = template.replace(token, str(value))
    return template


def write_packet(summary: dict[str, object]) -> dict[str, str]:
    OUT.mkdir(parents=True, exist_ok=True)
    blind_path = OUT / "p3-06-oracle-blind.csv"
    manifest_path = OUT / "p3-06-oracle-manifest.csv"
    labeler_path = OUT / "p3-06-oracle-labeler.html"
    write_csv(blind_path, BLIND_FIELDS, blind_rows(summary))
    write_csv(manifest_path, MANIFEST_FIELDS, summary["manifest"])  # type: ignore[arg-type]
    labeler_path.write_text(
        labeler_html(
            blind_rows(summary),
            title="P3-06 oracle packet — which source sentence does this citation depend on?",
            storage_key="p3-06-oracle-v1",
            download="p3-06-oracle-labelled.csv",
        ),
        encoding="utf-8",
        newline="\n",
    )

    OVERLAP.mkdir(parents=True, exist_ok=True)
    overlap_opaque = summary["overlap_opaque"]
    overlap_blind = OVERLAP / "p3-06-oracle-overlap-blind.csv"
    overlap_labeler = OVERLAP / "p3-06-oracle-overlap-labeler.html"
    write_csv(overlap_blind, BLIND_FIELDS, blind_rows(summary, overlap_opaque))  # type: ignore[arg-type]
    overlap_labeler.write_text(
        labeler_html(
            blind_rows(summary, overlap_opaque),  # type: ignore[arg-type]
            title="P3-06 oracle — second labeler overlap (10 rows)",
            storage_key="p3-06-oracle-overlap-v1",
            download="p3-06-oracle-overlap-labelled.csv",
        ),
        encoding="utf-8",
        newline="\n",
    )

    (OUT / "README.md").write_text(readme(summary), encoding="utf-8", newline=chr(10))
    (OVERLAP / "README.md").write_text(
        "\n".join(
            [
                "# P3-06 oracle — second labeler handoff",
                "",
                f"- **{OVERLAP_SIZE}** rows from the 30-row oracle packet, blind.",
                "- Blind files only: no manifest, no gold labels, no first-labeler output.",
                "- **Open:** `p3-06-oracle-overlap-labeler.html`.",
                "- **Send back:** its CSV export, saved as",
                "  `p3-06-oracle-overlap-labelled.csv` here.",
                "- Record your own labeler id in the tool; do not use the first labeler's id.",
                "",
            ]
        ),
        encoding="utf-8",
        newline="\n",
    )
    return {
        "blind": str(blind_path),
        "manifest": str(manifest_path),
        "labeler": str(labeler_path),
        "overlap_blind": str(overlap_blind),
        "overlap_labeler": str(overlap_labeler),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=SEED)
    args = parser.parse_args(argv)

    rows = spec_rows(scored_rows(load_rows()), "dev")
    summary = build(rows, read_manifests(), seed=args.seed)
    paths = write_packet(summary)
    print(
        json.dumps(
            {
                "rows": summary["rows"],
                "positives": summary["positives"],
                "negatives": summary["negatives"],
                "negatives_by_section": summary["negatives_by_section"],
                "seed": summary["seed"],
                "packet_hash": summary["packet_hash"],
                "overlap_opaque": summary["overlap_opaque"],
                "paths": paths,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
