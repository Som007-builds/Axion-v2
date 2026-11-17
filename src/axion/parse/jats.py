"""Deterministic JATS XML parsing: sections, paragraphs, references, contexts.

The parser uses only the standard library. It targets Europe PMC's JATS
rendition but strips XML namespaces before matching, so publisher variations
that keep the same element names still parse.

Citation contexts come from ``<xref ref-type="bibr">`` markers: each marker is
located inside its paragraph text, the sentence containing it becomes the
context, and a short sentence is expanded to its neighbouring sentences.
Unresolved markers and unhandled structural elements are recorded as warnings
rather than silently dropped.
"""

from __future__ import annotations

import gzip
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_SENTENCE_BOUNDARY = re.compile(r"""[.!?]+["')\]]*\s+""")
_YEAR_PATTERN = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")
_MIN_CONTEXT_CHARS = 40
_MAX_CONTEXT_CHARS = 1_200

# Body elements that carry no claim prose and are deliberately not parsed.
_IGNORED_BODY_ELEMENTS = frozenset(
    {
        "ack",
        "boxed-text",
        "chem-struct-wrap",
        "def-list",
        "disp-formula",
        "disp-quote",
        "fig",
        "fig-group",
        "fn-group",
        "glossary",
        "graphic",
        "label",
        "list",
        "media",
        "notes",
        "preformat",
        "ref-list",
        "statement",
        "supplementary-material",
        "table-wrap",
        "table-wrap-group",
    }
)


class JatsParseError(Exception):
    """Raised when a document is not parseable JATS."""


class Paragraph(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    section: tuple[str, ...] = ()
    text: str


class Section(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str | None = None
    path: tuple[str, ...] = ()
    paragraphs: tuple[Paragraph, ...] = ()
    subsections: tuple[Section, ...] = ()


class Reference(BaseModel):
    model_config = ConfigDict(frozen=True)

    ref_id: str
    label: str | None = None
    title: str | None = None
    authors: tuple[str, ...] = ()
    journal: str | None = None
    year: int | None = None
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    citation_text: str | None = None


class CitationContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    context_id: str
    paragraph_index: int
    sentence_index: int
    marker_index: int = 0
    section: tuple[str, ...] = ()
    text: str
    paragraph_text: str
    marker: str
    ref_id: str
    resolved: bool = False
    ref_label: str | None = None


class ParsedPaper(BaseModel):
    model_config = ConfigDict(frozen=True)

    paper_id: str | None = None
    pmcid: str | None = None
    pmid: str | None = None
    doi: str | None = None
    title: str | None = None
    journal: str | None = None
    year: int | None = None
    sections: tuple[Section, ...] = ()
    paragraphs: tuple[Paragraph, ...] = ()
    references: tuple[Reference, ...] = ()
    citation_contexts: tuple[CitationContext, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class PaperCoverage:
    paper_id: str
    sections: int
    paragraphs: int
    references: int
    references_with_doi: int
    references_with_pmid: int
    references_with_title: int
    references_with_year: int
    bibr_markers: int
    contexts: int
    contexts_resolved: int
    contexts_unresolved: int
    warnings: int

    @property
    def has_contexts(self) -> bool:
        return self.contexts > 0

    @property
    def has_references(self) -> bool:
        return self.references > 0


@dataclass(frozen=True)
class CorpusCoverage:
    papers: int
    papers_with_sections: int
    papers_with_contexts: int
    papers_with_references: int
    papers_with_resolved_contexts: int
    sections: int
    paragraphs: int
    references: int
    references_with_doi: int
    references_with_pmid: int
    references_with_title: int
    references_with_year: int
    bibr_markers: int
    contexts: int
    contexts_resolved: int
    warnings: int

    @property
    def percent_papers_with_contexts(self) -> float:
        return 100.0 * self.papers_with_contexts / self.papers if self.papers else 0.0

    @property
    def percent_papers_with_resolved_contexts(self) -> float:
        return 100.0 * self.papers_with_resolved_contexts / self.papers if self.papers else 0.0

    @property
    def percent_contexts_resolved(self) -> float:
        return 100.0 * self.contexts_resolved / self.contexts if self.contexts else 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "papers": self.papers,
            "papers_with_sections": self.papers_with_sections,
            "papers_with_contexts": self.papers_with_contexts,
            "papers_with_references": self.papers_with_references,
            "papers_with_resolved_contexts": self.papers_with_resolved_contexts,
            "percent_papers_with_contexts": round(self.percent_papers_with_contexts, 2),
            "percent_papers_with_resolved_contexts": round(
                self.percent_papers_with_resolved_contexts, 2
            ),
            "percent_contexts_resolved": round(self.percent_contexts_resolved, 2),
            "sections": self.sections,
            "paragraphs": self.paragraphs,
            "references": self.references,
            "references_with_doi": self.references_with_doi,
            "references_with_pmid": self.references_with_pmid,
            "references_with_title": self.references_with_title,
            "references_with_year": self.references_with_year,
            "bibr_markers": self.bibr_markers,
            "contexts": self.contexts,
            "contexts_resolved": self.contexts_resolved,
            "warnings": self.warnings,
        }


@dataclass(frozen=True)
class _Marker:
    start: int
    end: int
    marker: str
    ref_id: str
    index: int = 0


def parse_jats(xml: str, *, paper_id: str | None = None) -> ParsedPaper:
    """Parse one JATS document."""
    header = xml[:4_000].upper()
    if "<!DOCTYPE" in header and "<!ENTITY" in xml.upper():
        # ElementTree expands internal entities; reject documents that declare any.
        raise JatsParseError("JATS documents with internal ENTITY declarations are not accepted")
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise JatsParseError(f"invalid XML: {exc}") from exc

    article_meta = _descendant(root, "article-meta")
    if article_meta is None:
        raise JatsParseError("no article-meta element")

    pmcid = _article_id(article_meta, "pmcid")
    warnings: list[str] = []

    references = _parse_references(root, warnings)
    references_by_id: dict[str, Reference] = {}
    for reference in references:
        if reference.ref_id in references_by_id:
            warnings.append(f"duplicate reference id {reference.ref_id!r}; keeping the first")
            continue
        references_by_id[reference.ref_id] = reference

    builder = _BodyBuilder(references_by_id, warnings)
    sections: list[Section] = []
    abstract = _find(article_meta, "abstract")
    if abstract is not None:
        abstract_section = builder.build_abstract(abstract)
        if abstract_section.paragraphs:
            sections.append(abstract_section)

    body = _find(root, "body")
    if body is not None:
        sections.extend(builder.build_sections(body, ()))
    else:
        warnings.append("no body element")

    paper_key = paper_id or pmcid or "unknown"
    contexts = tuple(
        context.model_copy(update={"context_id": f"{paper_key}:{context.context_id}"})
        for context in builder.contexts
    )

    return ParsedPaper(
        paper_id=paper_id or pmcid,
        pmcid=pmcid,
        pmid=_article_id(article_meta, "pmid"),
        doi=_article_id(article_meta, "doi"),
        title=_text(_find(article_meta, "title-group/article-title")),
        journal=_text(_descendant(root, "journal-title")),
        year=_year(root),
        sections=tuple(sections),
        paragraphs=tuple(builder.paragraphs),
        references=references,
        citation_contexts=contexts,
        warnings=tuple(warnings),
    )


def parse_jats_file(path: Path, *, paper_id: str | None = None) -> ParsedPaper:
    """Parse a plain ``.xml`` or gzip-compressed ``.xml.gz`` JATS file."""
    if path.suffix == ".gz":
        with gzip.open(path, "rb") as handle:
            raw = handle.read()
    else:
        raw = path.read_bytes()
    try:
        xml = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise JatsParseError(f"{path} is not UTF-8") from exc
    return parse_jats(xml, paper_id=paper_id or path.name.split(".")[0])


def paper_coverage(paper: ParsedPaper) -> PaperCoverage:
    """Coverage counts for one parsed paper."""
    resolved = sum(1 for context in paper.citation_contexts if context.resolved)
    return PaperCoverage(
        paper_id=str(paper.paper_id or paper.pmcid or "unknown"),
        sections=_count_sections(paper.sections),
        paragraphs=len(paper.paragraphs),
        references=len(paper.references),
        references_with_doi=sum(1 for ref in paper.references if ref.doi),
        references_with_pmid=sum(1 for ref in paper.references if ref.pmid),
        references_with_title=sum(1 for ref in paper.references if ref.title),
        references_with_year=sum(1 for ref in paper.references if ref.year is not None),
        bibr_markers=len({(c.paragraph_index, c.marker_index) for c in paper.citation_contexts}),
        contexts=len(paper.citation_contexts),
        contexts_resolved=resolved,
        contexts_unresolved=len(paper.citation_contexts) - resolved,
        warnings=len(paper.warnings),
    )


def corpus_coverage(papers: Iterable[ParsedPaper]) -> CorpusCoverage:
    """Aggregate coverage over a set of parsed papers."""
    rows = [paper_coverage(paper) for paper in papers]
    return CorpusCoverage(
        papers=len(rows),
        papers_with_sections=sum(1 for row in rows if row.sections > 0),
        papers_with_contexts=sum(1 for row in rows if row.contexts > 0),
        papers_with_references=sum(1 for row in rows if row.references > 0),
        papers_with_resolved_contexts=sum(1 for row in rows if row.contexts_resolved > 0),
        sections=sum(row.sections for row in rows),
        paragraphs=sum(row.paragraphs for row in rows),
        references=sum(row.references for row in rows),
        references_with_doi=sum(row.references_with_doi for row in rows),
        references_with_pmid=sum(row.references_with_pmid for row in rows),
        references_with_title=sum(row.references_with_title for row in rows),
        references_with_year=sum(row.references_with_year for row in rows),
        bibr_markers=sum(row.bibr_markers for row in rows),
        contexts=sum(row.contexts for row in rows),
        contexts_resolved=sum(row.contexts_resolved for row in rows),
        warnings=sum(row.warnings for row in rows),
    )


class _BodyBuilder:
    def __init__(
        self,
        references_by_id: dict[str, Reference],
        warnings: list[str],
    ) -> None:
        self.paragraphs: list[Paragraph] = []
        self.contexts: list[CitationContext] = []
        self._references_by_id = references_by_id
        self._warnings = warnings
        self._next_index = 0
        self._next_context = 0

    def build_abstract(self, abstract: ET.Element) -> Section:
        title = _text(_find(abstract, "title")) or "Abstract"
        paragraphs: list[Paragraph] = []
        for element in abstract.iter():
            if _local(element.tag) != "p":
                continue
            paragraph = self._paragraph(element, (title,))
            if paragraph is not None:
                paragraphs.append(paragraph)
        return Section(title=title, path=(title,), paragraphs=tuple(paragraphs))

    def build_sections(self, parent: ET.Element, path: tuple[str, ...]) -> list[Section]:
        sections: list[Section] = []
        for child in parent:
            name = _local(child.tag)
            if name == "sec":
                sections.append(self._section(child, path))
            elif name == "p":
                self._paragraph(child, path)
            elif name not in _IGNORED_BODY_ELEMENTS:
                self._warnings.append(f"unhandled body element <{name}>")
        return sections

    def _section(self, element: ET.Element, path: tuple[str, ...]) -> Section:
        title = _text(_find(element, "title"))
        section_path = (*path, title) if title else path
        paragraphs: list[Paragraph] = []
        subsections: list[Section] = []
        for child in element:
            name = _local(child.tag)
            if name == "p":
                paragraph = self._paragraph(child, section_path)
                if paragraph is not None:
                    paragraphs.append(paragraph)
            elif name == "sec":
                subsections.append(self._section(child, section_path))
            elif name not in _IGNORED_BODY_ELEMENTS and name != "title":
                self._warnings.append(f"unhandled section element <{name}>")
        return Section(
            title=title,
            path=section_path,
            paragraphs=tuple(paragraphs),
            subsections=tuple(subsections),
        )

    def _paragraph(self, element: ET.Element, path: tuple[str, ...]) -> Paragraph | None:
        raw_text, markers = _flatten_with_markers(element)
        text = _normalize(raw_text)
        if not text:
            return None
        index = self._next_index
        self._next_index += 1
        paragraph = Paragraph(index=index, section=path, text=text)
        self.paragraphs.append(paragraph)

        sentence_spans = _sentence_spans(raw_text)
        for marker in markers:
            sentence_index = _sentence_index(sentence_spans, marker.start)
            context_text = _context_text(raw_text, sentence_spans, sentence_index, marker)
            reference = self._references_by_id.get(marker.ref_id)
            self.contexts.append(
                CitationContext(
                    context_id=f"p{index}:c{self._next_context}",
                    paragraph_index=index,
                    sentence_index=sentence_index,
                    marker_index=marker.index,
                    section=path,
                    text=context_text,
                    paragraph_text=text,
                    marker=marker.marker,
                    ref_id=marker.ref_id,
                    resolved=reference is not None,
                    ref_label=reference.label if reference is not None else None,
                )
            )
            self._next_context += 1
        return paragraph


def _flatten_with_markers(element: ET.Element) -> tuple[str, list[_Marker]]:
    parts: list[str] = []
    markers: list[_Marker] = []
    length = 0
    next_marker_index = 0

    def add(value: str) -> None:
        nonlocal length
        parts.append(value)
        length += len(value)

    def walk(node: ET.Element) -> None:
        nonlocal length, next_marker_index
        if node.text:
            add(node.text)
        for child in node:
            name = _local(child.tag)
            if (
                name == "xref"
                and child.attrib.get("ref-type") == "bibr"
                and child.attrib.get("rid")
            ):
                start = length
                walk(child)
                end = length
                marker_text = _normalize("".join(parts_of(child)))
                for ref_id in child.attrib["rid"].split():
                    markers.append(
                        _Marker(start, end, marker_text, ref_id, index=next_marker_index)
                    )
                next_marker_index += 1
            else:
                walk(child)
            if child.tail:
                add(child.tail)

    walk(element)
    return "".join(parts), markers


def parts_of(element: ET.Element) -> Iterator[str]:
    """Yield text fragments of an element in document order."""
    if element.text:
        yield element.text
    for child in element:
        yield from parts_of(child)
        if child.tail:
            yield child.tail


def _sentence_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    for match in _SENTENCE_BOUNDARY.finditer(text):
        spans.append((start, match.end()))
        start = match.end()
    spans.append((start, len(text)))
    return spans


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences with the same boundary rule as contexts.

    Public because evaluation aligns claims and student selections to the
    sentence that contains them; the rule must match the parser's.
    """
    return [
        segment
        for segment in (text[start:end].strip() for start, end in _sentence_spans(text))
        if segment
    ]


def sentence_bounds(text: str) -> list[tuple[int, int]]:
    """Sentence character spans, trimmed of surrounding whitespace."""
    bounds: list[tuple[int, int]] = []
    for start, end in _sentence_spans(text):
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if end > start:
            bounds.append((start, end))
    return bounds


def _sentence_index(spans: list[tuple[int, int]], position: int) -> int:
    for index, (start, end) in enumerate(spans):
        if start <= position < end:
            return index
    return max(0, len(spans) - 1)


def _context_text(
    raw_text: str,
    spans: list[tuple[int, int]],
    sentence_index: int,
    marker: _Marker,
) -> str:
    start, end = spans[sentence_index]
    if len(_normalize(raw_text[start:end])) < _MIN_CONTEXT_CHARS or len(spans) == 1:
        start = spans[max(0, sentence_index - 1)][0]
        end = spans[min(len(spans) - 1, sentence_index + 1)][1]
    context = _normalize(raw_text[start:end])
    if len(context) > _MAX_CONTEXT_CHARS:
        # Center an oversized window on the marker so the citation is retained.
        window_start = max(0, marker.start - _MAX_CONTEXT_CHARS // 2)
        window_end = min(len(raw_text), marker.end + _MAX_CONTEXT_CHARS // 2)
        context = _normalize(raw_text[window_start:window_end])[:_MAX_CONTEXT_CHARS]
    return context


def _parse_references(root: ET.Element, warnings: list[str]) -> tuple[Reference, ...]:
    # Europe PMC puts ref-list under back for some publishers and inside a body
    # section for others, so search the whole document.
    ref_lists = [element for element in root.iter() if _local(element.tag) == "ref-list"]
    if not ref_lists:
        warnings.append("no ref-list element")
        return ()

    references: list[Reference] = []
    seen: set[str] = set()
    for ref_list in ref_lists:
        for element in ref_list.iter():
            if _local(element.tag) != "ref":
                continue
            ref_id = element.attrib.get("id")
            if not ref_id:
                warnings.append("reference without an id; skipped")
                continue
            if ref_id in seen:
                warnings.append(f"duplicate reference id {ref_id!r}; keeping the first")
                continue
            seen.add(ref_id)
            citation = _find(element, "element-citation")
            if citation is None:
                citation = _find(element, "mixed-citation")
            source = citation if citation is not None else element
            citation_text = _text(source)
            references.append(
                Reference(
                    ref_id=ref_id,
                    label=_text(_find(element, "label")),
                    title=_first_text(source, ("article-title", "chapter-title", "data-title")),
                    authors=_reference_authors(source),
                    journal=_text(_descendant(source, "journal-title")),
                    year=_first_year(source) or _year_from_text(citation_text),
                    doi=_pub_id(source, "doi"),
                    pmid=_pub_id(source, "pmid"),
                    pmcid=_pub_id(source, "pmcid"),
                    citation_text=citation_text,
                )
            )
    return tuple(references)


def _reference_authors(source: ET.Element) -> tuple[str, ...]:
    authors: list[str] = []
    for element in source.iter():
        name = _local(element.tag)
        if name == "string-name":
            value = _text(element)
            if value:
                authors.append(value)
        elif name == "name":
            surname = _text(_find(element, "surname"))
            given = _text(_find(element, "given-names"))
            value = " ".join(part for part in (given, surname) if part)
            if value:
                authors.append(value)
    return tuple(authors)


def _first_year(source: ET.Element) -> int | None:
    for element in source.iter():
        if _local(element.tag) == "year":
            text = _text(element)
            if text and text[:4].isdigit():
                return int(text[:4])
    return None


def _year_from_text(text: str | None) -> int | None:
    if not text:
        return None
    match = _YEAR_PATTERN.search(text)
    return int(match.group(1)) if match is not None else None


def _pub_id(source: ET.Element, kind: str) -> str | None:
    for element in source.iter():
        if _local(element.tag) == "pub-id" and element.attrib.get("pub-id-type") == kind:
            return _text(element)
    return None


def _count_sections(sections: Iterable[Section]) -> int:
    return sum(1 + _count_sections(section.subsections) for section in sections)


def _article_id(article_meta: ET.Element, kind: str) -> str | None:
    for element in article_meta.iter():
        if _local(element.tag) == "article-id" and element.attrib.get("pub-id-type") == kind:
            return _text(element)
    return None


def _year(root: ET.Element) -> int | None:
    for element in root.iter():
        if _local(element.tag) != "pub-date":
            continue
        year = _first_year(element)
        if year is not None:
            return year
    return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _find(element: ET.Element, path: str) -> ET.Element | None:
    """Namespace-insensitive ``find`` for slash-separated child paths."""
    current: ET.Element | None = element
    for step in path.split("/"):
        if current is None:
            return None
        current = _find_child(current, step)
    return current


def _find_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if _local(child.tag) == name:
            return child
    return None


def _descendant(element: ET.Element, name: str) -> ET.Element | None:
    for child in element.iter():
        if _local(child.tag) == name:
            return child
    return None


def _first_text(element: ET.Element, names: tuple[str, ...]) -> str | None:
    for name in names:
        for child in element.iter():
            if _local(child.tag) == name:
                value = _text(child)
                if value:
                    return value
    return None


def _text(element: ET.Element | None) -> str | None:
    if element is None:
        return None
    value = _normalize("".join(element.itertext()))
    return value or None


def _normalize(text: str) -> str:
    return " ".join(text.split())


__all__ = [
    "CitationContext",
    "CorpusCoverage",
    "JatsParseError",
    "PaperCoverage",
    "Paragraph",
    "ParsedPaper",
    "Reference",
    "Section",
    "corpus_coverage",
    "paper_coverage",
    "parse_jats",
    "parse_jats_file",
]
