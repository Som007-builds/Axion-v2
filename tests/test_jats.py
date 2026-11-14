"""Golden and unit tests for the JATS parser."""

from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from axion.parse.jats import (
    JatsParseError,
    corpus_coverage,
    paper_coverage,
    parse_jats,
    parse_jats_file,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "jats"
EXPECTED = json.loads((FIXTURE_DIR / "expected.json").read_text(encoding="utf-8"))
MANIFEST = json.loads((FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))


def _article(
    body: str,
    *,
    references: str | None = "",
    abstract: str = "",
    journal: str = "Test Journal",
) -> str:
    back = "" if references is None else f"<back><ref-list>{references}</ref-list></back>"
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <journal-meta>
      <journal-title-group><journal-title>{journal}</journal-title></journal-title-group>
    </journal-meta>
    <article-meta>
      <article-id pub-id-type="pmcid">PMC1</article-id>
      <article-id pub-id-type="pmid">42</article-id>
      <article-id pub-id-type="doi">10.1/example</article-id>
      <title-group><article-title>Example title</article-title></title-group>
      <pub-date><year>2020</year></pub-date>
      {abstract}
    </article-meta>
  </front>
  <body>{body}</body>
  {back}
</article>"""


_REFERENCES = """
<ref id="b1">
  <label>1</label>
  <element-citation>
    <person-group><name><surname>Smith</surname><given-names>J</given-names></name></person-group>
    <article-title>An earlier paper</article-title>
    <journal-title>Journal of Tests</journal-title>
    <year>2019</year>
    <pub-id pub-id-type="doi">10.1/earlier</pub-id>
    <pub-id pub-id-type="pmid">12345</pub-id>
  </element-citation>
</ref>
<ref id="b2">
  <mixed-citation><named-content content-type="citation-string">Doe A. Legacy reference.
  J Tests. 2011;2:3-4.</named-content></mixed-citation>
</ref>
"""


@pytest.mark.parametrize("pmcid", sorted(EXPECTED))
def test_golden_fixture(pmcid: str) -> None:
    paper = parse_jats_file(FIXTURE_DIR / f"{pmcid}.xml.gz")
    expected = EXPECTED[pmcid]
    coverage = paper_coverage(paper)

    assert paper.pmcid == pmcid
    assert paper.journal == expected["journal"]
    assert paper.year == expected["year"]
    assert coverage.sections == expected["sections"]
    assert coverage.paragraphs == expected["paragraphs"]
    assert coverage.references == expected["references"]
    assert coverage.references_with_doi == expected["references_with_doi"]
    assert coverage.references_with_pmid == expected["references_with_pmid"]
    assert coverage.references_with_title == expected["references_with_title"]
    assert coverage.references_with_year == expected["references_with_year"]
    assert coverage.bibr_markers == expected["bibr_markers"]
    assert coverage.contexts == expected["contexts"]
    assert coverage.contexts_resolved == expected["contexts_resolved"]
    assert list(paper.warnings) == expected["warnings"]
    assert [section.title for section in paper.sections] == expected["top_level_sections"]

    first = paper.citation_contexts[0]
    assert expected["first_context"] == {
        "ref_id": first.ref_id,
        "section": list(first.section),
        "text": first.text,
    }

    first_doi = next((reference for reference in paper.references if reference.doi), None)
    expected_doi = expected["first_reference_with_doi"]
    if expected_doi is None:
        assert first_doi is None
    else:
        assert first_doi is not None
        assert expected_doi == {
            "ref_id": first_doi.ref_id,
            "doi": first_doi.doi,
            "year": first_doi.year,
        }


def test_fixtures_cover_at_least_ten_journals() -> None:
    articles = MANIFEST["articles"]

    assert len(articles) >= 10
    assert len({article["journal"] for article in articles}) >= 10


def test_fixtures_are_cc_by() -> None:
    for article in MANIFEST["articles"]:
        haystack = f"{article['license_url'] or ''} {article['license_text'] or ''}".lower()
        assert (
            "creativecommons.org/licenses/by" in haystack
            or "creative commons attribution" in haystack
        )
        assert "noncommercial" not in haystack
        assert "noderiv" not in haystack


def test_fixture_hashes_match_manifest() -> None:
    for article in MANIFEST["articles"]:
        path = FIXTURE_DIR / f"{article['pmcid']}.xml.gz"
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == article["gz_sha256"]
        raw = gzip.decompress(path.read_bytes())
        assert hashlib.sha256(raw).hexdigest() == article["xml_sha256"]


def test_fixture_coverage_has_contexts_everywhere() -> None:
    papers = [parse_jats_file(path) for path in sorted(FIXTURE_DIR.glob("*.xml.gz"))]
    coverage = corpus_coverage(papers)

    assert coverage.papers == len(EXPECTED)
    assert coverage.percent_papers_with_contexts == 100.0
    assert coverage.contexts == coverage.contexts_resolved


def test_metadata_and_nested_section_paths() -> None:
    paper = parse_jats(
        _article(
            """
            <sec><title>Introduction</title>
              <p>Alpha beta gamma delta.</p>
              <sec><title>Background</title><p>Epsilon zeta eta theta.</p></sec>
            </sec>
            """
        )
    )

    assert paper.pmcid == "PMC1"
    assert paper.pmid == "42"
    assert paper.doi == "10.1/example"
    assert paper.title == "Example title"
    assert paper.journal == "Test Journal"
    assert paper.year == 2020
    assert [paragraph.section for paragraph in paper.paragraphs] == [
        ("Introduction",),
        ("Introduction", "Background"),
    ]
    assert paper.sections[0].subsections[0].title == "Background"
    assert paper.warnings == ()


def test_abstract_is_first_section() -> None:
    paper = parse_jats(
        _article(
            "<sec><title>Body</title><p>Body text.</p></sec>",
            abstract="<abstract><p>Abstract text.</p></abstract>",
        )
    )

    assert paper.sections[0].title == "Abstract"
    assert paper.sections[0].paragraphs[0].text == "Abstract text."
    assert paper.paragraphs[0].section == ("Abstract",)


def test_multiple_rids_share_one_marker_index() -> None:
    paper = parse_jats(
        _article(
            """
            <sec><title>Results</title>
              <p>We observed a large effect in this cohort
                 <xref ref-type="bibr" rid="b1 b2">1,2</xref> and it held.</p>
            </sec>
            """,
            references=_REFERENCES,
        )
    )

    contexts = paper.citation_contexts
    assert len(contexts) == 2
    assert {context.ref_id for context in contexts} == {"b1", "b2"}
    assert contexts[0].marker_index == contexts[1].marker_index
    assert all(context.resolved for context in contexts)
    assert contexts[0].text.startswith("We observed a large effect")
    assert paper_coverage(paper).bibr_markers == 1
    assert paper_coverage(paper).contexts == 2


def test_unresolved_reference_is_flagged() -> None:
    paper = parse_jats(
        _article(
            "<sec><title>Intro</title><p>See this citation "
            '<xref ref-type="bibr" rid="missing">9</xref>.</p></sec>'
        )
    )

    context = paper.citation_contexts[0]
    assert context.resolved is False
    assert context.ref_label is None
    assert paper_coverage(paper).contexts_unresolved == 1


def test_non_bibr_xrefs_are_ignored() -> None:
    paper = parse_jats(
        _article(
            "<sec><title>Intro</title><p>See "
            '<xref ref-type="fig" rid="f1">Figure 1</xref> for details.</p></sec>'
        )
    )

    assert paper.citation_contexts == ()


def test_short_sentence_expands_to_neighbours() -> None:
    paper = parse_jats(
        _article(
            """
            <sec><title>Intro</title>
              <p>As shown <xref ref-type="bibr" rid="b1">1</xref>.
                 This second sentence is much longer and gives the surrounding
                 context needed later.</p>
            </sec>
            """,
            references=_REFERENCES,
        )
    )

    context = paper.citation_contexts[0]
    assert "This second sentence is much longer" in context.text


def test_element_citation_fields() -> None:
    paper = parse_jats(
        _article(
            '<sec><title>Intro</title><p>Text <xref ref-type="bibr" rid="b1">1</xref>.</p></sec>',
            references=_REFERENCES,
        )
    )

    reference = paper.references[0]
    assert reference.label == "1"
    assert reference.title == "An earlier paper"
    assert reference.authors == ("J Smith",)
    assert reference.journal == "Journal of Tests"
    assert reference.year == 2019
    assert reference.doi == "10.1/earlier"
    assert reference.pmid == "12345"


def test_mixed_citation_falls_back_to_year_in_text() -> None:
    paper = parse_jats(
        _article(
            '<sec><title>Intro</title><p>Text <xref ref-type="bibr" rid="b2">2</xref>.</p></sec>',
            references=_REFERENCES,
        )
    )

    reference = paper.references[1]
    assert reference.title is None
    assert reference.doi is None
    assert reference.year == 2011


def test_context_ids_include_paper_override() -> None:
    paper = parse_jats(
        _article(
            '<sec><title>Intro</title><p>Text <xref ref-type="bibr" rid="b1">1</xref>.</p></sec>',
            references=_REFERENCES,
        ),
        paper_id="doc-1",
    )

    assert paper.paper_id == "doc-1"
    assert paper.citation_contexts[0].context_id.startswith("doc-1:")


def test_corpus_coverage_percentages() -> None:
    with_context = parse_jats(
        _article(
            '<sec><title>Intro</title><p>Text <xref ref-type="bibr" rid="b1">1</xref>.</p></sec>',
            references=_REFERENCES,
        )
    )
    without_context = parse_jats(
        _article("<sec><title>Intro</title><p>No citation here.</p></sec>")
    )

    coverage = corpus_coverage([with_context, without_context])

    assert coverage.papers == 2
    assert coverage.papers_with_contexts == 1
    assert coverage.percent_papers_with_contexts == 50.0


def test_entity_declarations_are_rejected() -> None:
    xml = (
        '<?xml version="1.0"?><!DOCTYPE article [<!ENTITY x "y">]>'
        "<article><front><article-meta/></front></article>"
    )

    with pytest.raises(JatsParseError):
        parse_jats(xml)


def test_invalid_xml_is_rejected() -> None:
    with pytest.raises(JatsParseError):
        parse_jats("<article><front>")


def test_missing_article_meta_is_rejected() -> None:
    with pytest.raises(JatsParseError):
        parse_jats("<article><front></front><body/></article>")


def test_missing_ref_list_is_a_warning_not_an_error() -> None:
    paper = parse_jats(
        _article("<sec><title>Intro</title><p>No references.</p></sec>", references=None)
    )

    assert paper.references == ()
    assert "no ref-list element" in paper.warnings


def test_unhandled_body_element_is_recorded() -> None:
    paper = parse_jats(_article("<weird><p>Text.</p></weird>"))

    assert any("unhandled body element <weird>" in warning for warning in paper.warnings)


def test_non_utf8_file_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "bad.xml"
    path.write_bytes(b"<article>\xff</article>")

    with pytest.raises(JatsParseError):
        parse_jats_file(path)
