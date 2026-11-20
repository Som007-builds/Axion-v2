"""Tests for the P3-06 oracle packet and the oracle planner.

The point of these tests is that the packet stays blind and stays fixed: the same seed
must produce the same rows, the blind file must not carry a label, the manifest must be
separable, and the oracle must refuse to run without a complete, named label file.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from scripts import p3_06_link_oracle_packet as packet
from scripts import p3_06_oracle as oracle


def write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return path


def fake_row(row_id: str, label: str, bucket: str = "results") -> dict[str, str]:
    return {
        "row_id": row_id,
        "label": label,
        "frame": "text_bearing",
        "section_bucket": bucket,
        "wave": "wave1",
        "section": "Results",
        "source_title": f"source {row_id}",
        "context_text": f"citing sentence for {row_id}",
        "paragraph_text": f"paragraph for {row_id}",
    }


def test_choose_candidates_prefers_results_and_keeps_document_order() -> None:
    sentences = [
        ("Introduction", "intro one"),
        ("Introduction", "intro two"),
        ("Results", "result one"),
        ("Results", "result two"),
        ("Methods", "method one"),
    ]
    chosen = packet.choose_candidates(sentences, limit=3)
    assert chosen == ["result one", "result two", "method one"]


def test_choose_candidates_truncates_to_the_limit() -> None:
    sentences = [("Results", f"r{i}") for i in range(50)]
    assert len(packet.choose_candidates(sentences, limit=40)) == 40


def test_stratified_negatives_are_seeded_and_spread() -> None:
    negatives = [fake_row(f"N{index:03d}", "MENTIONS", "results") for index in range(30)]
    negatives += [fake_row(f"M{index:03d}", "MENTIONS", "introduction") for index in range(30)]
    first = packet.stratified_negatives(negatives, 16, seed=7)
    again = packet.stratified_negatives(negatives, 16, seed=7)
    other = packet.stratified_negatives(negatives, 16, seed=8)
    assert [row["row_id"] for row in first] == [row["row_id"] for row in again]
    assert [row["row_id"] for row in first] != [row["row_id"] for row in other]
    buckets = {row["section_bucket"] for row in first}
    assert buckets == {"results", "introduction"}
    assert len(first) == 16


def build_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    rows = [fake_row(f"P{index:02d}", "RELIES_ON") for index in range(packet.POSITIVES)]
    rows += [fake_row(f"N{index:03d}", "MENTIONS", "introduction") for index in range(20)]
    rows += [fake_row(f"R{index:03d}", "MENTIONS", "results") for index in range(20)]
    rows.append({**fake_row("STUB01", "MENTIONS"), "frame": "stub"})

    monkeypatch.setattr(
        packet,
        "body_sentences",
        lambda pmcid, fulltext=None: [
            ("Results", f"body {pmcid} one"),
            ("Methods", f"body {pmcid} two"),
        ],
    )
    manifests = {row["row_id"]: {"source_pmcid": f"PMC{index}"} for index, row in enumerate(rows)}
    return packet.build(rows, manifests, seed=packet.SEED)


def test_build_keeps_every_positive_and_blinds_the_label(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = build_fixture(tmp_path, monkeypatch)
    manifest = summary["manifest"]
    assert summary["rows"] == packet.TOTAL
    assert summary["positives"] == packet.POSITIVES
    assert summary["negatives"] == packet.NEGATIVES
    assert all(row["gold_label"] in {"RELIES_ON", "MENTIONS"} for row in manifest)
    assert sum(1 for row in manifest if row["gold_label"] == "RELIES_ON") == packet.POSITIVES

    blind = summary["blind"]
    assert len(blind) == packet.TOTAL
    for row in blind:
        assert set(row) == set(packet.BLIND_FIELDS)
        serialised = json.dumps(row)
        assert "RELIES_ON" not in serialised
        assert "MENTIONS" not in serialised
        assert "gold" not in serialised


def test_build_is_deterministic(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    first = build_fixture(tmp_path, monkeypatch)
    second = build_fixture(tmp_path, monkeypatch)
    assert first["packet_hash"] == second["packet_hash"]
    assert [row["row_id"] for row in first["manifest"]] == [
        row["row_id"] for row in second["manifest"]
    ]


def test_overlap_contains_both_classes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    summary = build_fixture(tmp_path, monkeypatch)
    overlap = set(summary["overlap_row_ids"])
    assert len(overlap) == packet.OVERLAP_SIZE
    labels = {row["gold_label"] for row in summary["manifest"] if row["row_id"] in overlap}
    assert labels == {"RELIES_ON", "MENTIONS"}
    assert set(summary["overlap_opaque"]) == {
        row["opaque_id"] for row in summary["manifest"] if row["row_id"] in overlap
    }


def test_write_packet_separates_the_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    summary = build_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(packet, "OUT", tmp_path / "main")
    monkeypatch.setattr(packet, "OVERLAP", tmp_path / "overlap")
    paths = packet.write_packet(summary)

    blind_text = Path(paths["blind"]).read_text(encoding="utf-8")
    assert "RELIES_ON" not in blind_text
    assert "gold_label" not in blind_text
    for field in packet.BLIND_FIELDS:
        assert field in blind_text

    manifest_text = Path(paths["manifest"]).read_text(encoding="utf-8")
    assert "gold_label" in manifest_text
    assert "overlap" in manifest_text

    overlap_dir = tmp_path / "overlap"
    names = {path.name for path in overlap_dir.iterdir()}
    assert "p3-06-oracle-overlap-blind.csv" in names
    assert not any("manifest" in name for name in names)
    labeler = (overlap_dir / "p3-06-oracle-overlap-labeler.html").read_text(encoding="utf-8")
    assert "RELIES_ON" not in labeler


def test_oracle_refuses_without_labels(tmp_path: Path) -> None:
    with pytest.raises(oracle.OracleError, match="no labels yet"):
        oracle.read_labels(tmp_path / "missing.csv")


def test_oracle_refuses_anonymous_or_inconsistent_labels(tmp_path: Path) -> None:
    fields = ["opaque_id", "selected", "none", "note", "labeler", "date"]
    anonymous = write_csv(
        tmp_path / "a.csv", fields, [{"opaque_id": "O-01", "selected": "1", "labeler": ""}]
    )
    with pytest.raises(oracle.OracleError, match="no labeler id"):
        oracle.read_labels(anonymous)

    contradictory = write_csv(
        tmp_path / "b.csv",
        fields,
        [{"opaque_id": "O-01", "selected": "1", "none": "true", "labeler": "Soham"}],
    )
    with pytest.raises(oracle.OracleError, match="says none and also names"):
        oracle.read_labels(contradictory)

    silent = write_csv(
        tmp_path / "c.csv", fields, [{"opaque_id": "O-01", "none": "false", "labeler": "Soham"}]
    )
    with pytest.raises(oracle.OracleError, match="neither names a sentence nor says none"):
        oracle.read_labels(silent)


def test_parse_choice_rejects_out_of_range() -> None:
    candidates = ["a", "b", "c"]
    assert oracle.parse_choice({"opaque_id": "O-01", "selected": "3;1"}, candidates) == [0, 2]
    with pytest.raises(oracle.OracleError, match="only 3 were shown"):
        oracle.parse_choice({"opaque_id": "O-01", "selected": "4"}, candidates)
    with pytest.raises(oracle.OracleError, match="not a sentence number"):
        oracle.parse_choice({"opaque_id": "O-01", "selected": "two"}, candidates)


def test_oracle_arm_splits_treatment_none_and_untestable() -> None:
    manifest = {
        "O-01": {
            "opaque_id": "O-01",
            "row_id": "R1",
            "gold_label": "RELIES_ON",
            "no_source_body": "false",
        },
        "O-02": {
            "opaque_id": "O-02",
            "row_id": "R2",
            "gold_label": "MENTIONS",
            "no_source_body": "false",
        },
        "O-03": {
            "opaque_id": "O-03",
            "row_id": "R3",
            "gold_label": "RELIES_ON",
            "no_source_body": "true",
        },
    }
    blind = {key: {"candidates_json": json.dumps(["first", "second"])} for key in manifest}
    labels = [
        {"opaque_id": "O-01", "selected": "2", "none": "false", "labeler": "Soham"},
        {"opaque_id": "O-02", "selected": "", "none": "true", "labeler": "Soham"},
        {"opaque_id": "O-03", "selected": "", "none": "true", "labeler": "Soham"},
    ]
    arm = oracle.oracle_arm(manifest, blind, labels)
    assert [item["row_id"] for item in arm["treatment"]] == ["R1"]
    assert arm["treatment"][0]["sentence"] == "second"
    assert [row["row_id"] for row in arm["none_rows"]] == ["R2"]
    assert [row["row_id"] for row in arm["untestable"]] == ["R3"]
    assert arm["labeler"] == ["Soham"]


def test_oracle_arm_refuses_incomplete_or_unknown_labels() -> None:
    manifest = {
        "O-01": {
            "opaque_id": "O-01",
            "row_id": "R1",
            "gold_label": "RELIES_ON",
            "no_source_body": "false",
        }
    }
    blind = {"O-01": {"candidates_json": json.dumps(["only"])}}
    with pytest.raises(oracle.OracleError, match="not in this packet"):
        oracle.oracle_arm(
            manifest, blind, [{"opaque_id": "O-99", "selected": "1", "labeler": "Soham"}]
        )
    with pytest.raises(oracle.OracleError, match="have no label yet"):
        oracle.oracle_arm(manifest, blind, [])


def test_oracle_rows_swap_only_the_claim_block() -> None:
    rows = [
        {
            "row_id": "R1",
            "source_claim_text": "proxy sentence",
            "source_abstract": "the abstract",
            "context_text": "B cites A",
            "source_title": "title",
            "section": "Results",
        }
    ]
    swapped = oracle.oracle_rows([{"row_id": "R1", "sentence": "the chosen one"}], rows)
    assert swapped[0]["source_claim_text"] == "the chosen one"
    assert swapped[0]["source_abstract"] == "the abstract"
    assert swapped[0]["context_text"] == "B cites A"


def test_compare_counts_before_and_after_at_threshold() -> None:
    rows = [
        {**fake_row("R1", "RELIES_ON"), "reliance_terms": 5, "mention_terms": 0},
        {**fake_row("R2", "RELIES_ON"), "reliance_terms": 5, "mention_terms": 0},
        {**fake_row("R3", "MENTIONS"), "reliance_terms": 0, "mention_terms": 3},
    ]
    treatment = [
        {"row_id": "R1", "gold_label": "RELIES_ON"},
        {"row_id": "R2", "gold_label": "RELIES_ON"},
        {"row_id": "R3", "gold_label": "MENTIONS"},
    ]
    stats = oracle.compare(
        treatment,
        after={"R1": 70, "R2": 20, "R3": 90},
        before={"R1": 30, "R2": 20, "R3": 10},
        rows=rows,
        threshold=30,
    )
    assert stats["positives_total"] == 2
    assert stats["positives_caught_before"] == 1
    assert stats["positives_caught_after"] == 1
    assert stats["negatives_fired_before"] == 0
    assert stats["negatives_fired_after"] == 1
    assert [row["delta"] for row in stats["per_row"]] == [40, 0, 80]
    assert "direction" in stats["reading"]


def test_estimate_bounds_cost_from_the_packet() -> None:
    rows = [
        {
            "opaque_id": "O-01",
            "row": {
                "row_id": "R1",
                "source_claim_text": "proxy",
                "context_text": "B cites A",
                "source_title": "title",
                "section": "Results",
            },
        }
    ]
    blind = {"O-01": {"candidates_json": json.dumps(["short", "a much longer one"])}}
    stats = oracle.estimate(rows, blind)
    assert stats["requests"] == 1
    longest = stats["prompt_tokens_if_longest_candidate"]
    assert longest >= stats["prompt_tokens_if_first_candidate"]
    assert stats["usd_min"] is not None
    assert "free_tier" in stats["billing"]


def test_labeler_template_actually_mounts_the_cards() -> None:
    """The first build made 30 cards and appended none of them: a blank page.

    The page still reported "0 / 30 answered", because the counters ran on the data and
    not on the DOM, so nothing looked wrong until a human opened it.
    """
    from scripts.p3_06_link_oracle_packet import ROOT

    template = (ROOT / "docs" / "eval" / "link_oracle_labeler_template.html").read_text(
        encoding="utf-8"
    )
    assert "host.appendChild(card);" in template
    assert template.count("card.appendChild(") >= 5
    assert "render();" in template


def test_the_two_labelers_export_different_filenames() -> None:
    """Both pages exported p3-06-oracle-labelled.csv, so a 10-row overlap export
    looked like a broken 30-row one and quietly replaced it in Downloads."""
    from scripts.p3_06_link_oracle_packet import ROOT

    template = (ROOT / "docs" / "eval" / "link_oracle_labeler_template.html").read_text(
        encoding="utf-8"
    )
    assert "__DOWNLOAD__" in template


def test_interpret_reads_the_owners_column_names() -> None:
    """The packet came back as chosen_candidate/decision_cue, so 0 means none.

    Zero was confirmed against the eight rows that carry it: two of them have no
    candidates at all, so "sentence zero" cannot be what it means.
    """
    assert oracle.interpret({"opaque_id": "O-01", "chosen_candidate": "24"}) == (["24"], False)
    assert oracle.interpret({"opaque_id": "O-09", "chosen_candidate": "0"}) == ([], True)
    assert oracle.interpret({"opaque_id": "O-05", "chosen_candidate": "3,7"}) == (["3", "7"], False)
    assert oracle.interpret({"opaque_id": "O-02", "selected": "3;7"}) == (["3", "7"], False)
    assert oracle.interpret({"opaque_id": "O-03", "selected": "", "none": "true"}) == ([], True)


def test_interpret_refuses_a_blank_that_is_not_a_none_answer() -> None:
    with pytest.raises(oracle.OracleError, match="neither names a sentence nor says none"):
        oracle.interpret(
            {"opaque_id": "O-04", "chosen_candidate": "", "decision_cue": "the first result"}
        )
    with pytest.raises(oracle.OracleError, match="no selection column"):
        oracle.interpret({"opaque_id": "O-05", "answer": "3"})


def test_read_labels_accepts_the_owners_file_and_counts_both_answers(tmp_path: Path) -> None:
    fields = [
        "opaque_id",
        "candidates_json",
        "chosen_candidate",
        "labeler",
        "decision_cue",
    ]
    path = write_csv(
        tmp_path / "labels.csv",
        fields,
        [
            {"opaque_id": "O-01", "chosen_candidate": "24", "labeler": "s", "decision_cue": "a"},
            {"opaque_id": "O-09", "chosen_candidate": "0", "labeler": "s", "decision_cue": "none"},
            {"opaque_id": "O-25", "chosen_candidate": "0", "labeler": "s", "decision_cue": "none"},
        ],
    )
    labels = oracle.read_labels(path)
    assert len(labels) == 3
    answered = [oracle.interpret(row) for row in labels]
    assert answered[0] == (["24"], False)
    assert answered[1] == ([], True)
    assert oracle.label_columns(path) == fields


def test_oracle_arm_skips_a_none_answer_instead_of_sending_an_empty_claim() -> None:
    """Six rows answered 0. Counting only `none=true` put them in the treatment arm with
    an empty claim block: 6 paid requests asking about nothing, and the answers would have
    been compared as if they were the oracle."""
    manifest = {
        "O-01": {"opaque_id": "O-01", "row_id": "R1", "gold_label": "RELIES_ON", "body": "f"},
        "O-02": {"opaque_id": "O-02", "row_id": "R2", "gold_label": "MENTIONS", "body": "f"},
    }
    blind = {key: {"candidates_json": json.dumps(["first", "second"])} for key in manifest}
    labels = [
        {"opaque_id": "O-01", "chosen_candidate": "2", "labeler": "s", "decision_cue": "a"},
        {"opaque_id": "O-02", "chosen_candidate": "0", "labeler": "s", "decision_cue": "none: x"},
    ]
    for row in manifest.values():
        row["no_source_body"] = "false"
    arm = oracle.oracle_arm(manifest, blind, labels)
    assert [item["row_id"] for item in arm["treatment"]] == ["R1"]
    assert [row["row_id"] for row in arm["none_rows"]] == ["R2"]
