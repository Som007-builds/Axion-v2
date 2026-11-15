"""Normalization-only evidence-span matching tests."""

from __future__ import annotations

from axion.extract.claims import (
    BaselineDocument,
    BaselineSection,
    Claim,
    ClaimExtraction,
    audit_context,
    categorize_span_reject,
    find_evidence_span,
    normalize_for_match,
    verify_claims,
)


def _document(text: str, *, label: str = "Results") -> BaselineDocument:
    return BaselineDocument(
        paper_id="PMC1",
        paper_title="Paper",
        sections=(BaselineSection(label=label, path=(label,), text=text),),
    )


def _extraction(*spans: str, section: str = "Results") -> ClaimExtraction:
    return ClaimExtraction(
        claims=[
            Claim(claim_text=f"claim {index}", section=section, evidence_span=span)
            for index, span in enumerate(spans)
        ]
    )


def test_non_breaking_hyphen_is_normalized_to_ascii_hyphen() -> None:
    source = "The 5-day course was well tolerated."
    match = find_evidence_span(source, "The 5\u2011day course was well tolerated.")

    assert match is not None
    assert match.text == "The 5-day course was well tolerated."
    assert match.normalized is True


def test_whitespace_runs_and_non_breaking_spaces_are_collapsed() -> None:
    source = "Mortality was\nlower in the treated group."
    match = find_evidence_span(source, "Mortality was\u00a0 lower in the treated group.")

    assert match is not None
    assert match.text == source


def test_quote_variants_are_normalized() -> None:
    source = 'The "primary" outcome improved.'
    match = find_evidence_span(source, "The \u201cprimary\u201d outcome improved.")

    assert match is not None
    assert match.text == source


def test_compatibility_ligature_is_normalized() -> None:
    source = "The final analysis was significant."
    match = find_evidence_span(source, "The \ufb01nal analysis was significant.")

    assert match is not None
    assert match.text == source


def test_line_break_hyphenation_is_joined() -> None:
    source = "Remdesi-\nvir improved recovery."
    match = find_evidence_span(source, "Remdesivir improved recovery.")

    assert match is not None
    assert match.text == source


def test_non_contiguous_merged_span_is_still_rejected() -> None:
    source = "Worsening of comorbidities (OR 0.94), ferritin (OR 1.20)."
    evidence = "Worsening of comorbidities (OR 0.94) were observed."

    assert find_evidence_span(source, evidence) is None
    assert categorize_span_reject(source, evidence) == "partial_or_merged"


def test_case_change_is_not_silently_accepted() -> None:
    source = "remdesivir patients recovered faster."
    evidence = "Remdesivir patients recovered faster."

    assert find_evidence_span(source, evidence) is None
    assert categorize_span_reject(source, evidence) == "case_only"


def test_verify_claims_stores_exact_source_span_after_normalization() -> None:
    document = _document("Serious effects occurred in the ten-day group.")
    valid, failures = verify_claims(
        _extraction("Serious effects occurred in the ten\u2011day group."),
        document,
        paper_id="PMC1",
    )

    assert failures == []
    assert len(valid) == 1
    assert valid[0].evidence_span == "Serious effects occurred in the ten-day group."


def test_verify_claims_can_report_strict_before_normalization() -> None:
    document = _document("Serious effects occurred in the ten-day group.")
    valid, failures = verify_claims(
        _extraction("Serious effects occurred in the ten\u2011day group."),
        document,
        paper_id="PMC1",
        normalize=False,
    )

    assert valid == []
    assert len(failures) == 1
    assert failures[0].category == "normalization_only"
    assert failures[0].evidence_span is not None


def test_verify_claims_records_failure_evidence_and_category() -> None:
    document = _document("Something else entirely.")
    valid, failures = verify_claims(
        _extraction("Not present at all."),
        document,
        paper_id="PMC1",
    )

    assert valid == []
    assert failures[0].evidence_span == "Not present at all."
    assert failures[0].category == "paraphrase_or_absent"


def test_audit_context_finds_normalized_source_span() -> None:
    document = _document(
        "First paragraph.\nSecond paragraph has a ten-day course.\nThird paragraph.",
    )

    before, after = audit_context(
        document,
        section_label="Results",
        evidence_span="Second paragraph has a ten\u2011day course.",
    )

    assert "Second paragraph has a ten-day course." in before
    assert after == "Third paragraph."


def test_normalization_is_stable_for_plain_text() -> None:
    text = "A plain sentence with  two spaces."

    assert normalize_for_match(text) == "A plain sentence with two spaces."
