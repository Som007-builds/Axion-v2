"""Offline tests for the P1-09 idempotent corpus loader."""

from __future__ import annotations

from pathlib import Path

import pytest

from axion.ingest.corpus import CorpusCite, CorpusPaper
from axion.store.embeddings import EmbeddingError, HashEmbedder, build_embedder
from axion.store.loader import (
    CLAIMS_COLLECTION,
    CONTEXTS_COLLECTION,
    PAPERS_COLLECTION,
    CorpusLoadError,
    load_corpus,
)
from axion.store.memory import InMemoryGraph, InMemoryVectorStore
from axion.store.schema import SCHEMA_STATEMENTS, SCHEMA_VERSION

SOURCE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <journal-meta>
      <journal-title-group><journal-title>Test Journal</journal-title></journal-title-group>
    </journal-meta>
    <article-meta>
      <article-id pub-id-type="pmcid">PMC1</article-id>
      <article-id pub-id-type="pmid">42</article-id>
      <article-id pub-id-type="doi">10.1000/source</article-id>
      <title-group><article-title>Source Paper</article-title></title-group>
      <pub-date><year>2020</year></pub-date>
    </article-meta>
  </front>
  <body><sec><p>Source paper reported a large effect in the trial cohort.</p></sec></body>
</article>
"""

CITER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<article article-type="research-article">
  <front>
    <journal-meta>
      <journal-title-group><journal-title>Citing Journal</journal-title></journal-title-group>
    </journal-meta>
    <article-meta>
      <article-id pub-id-type="pmcid">PMC2</article-id>
      <article-id pub-id-type="pmid">43</article-id>
      <article-id pub-id-type="doi">10.1000/citer</article-id>
      <title-group><article-title>Citing Paper</article-title></title-group>
      <pub-date><year>2022</year></pub-date>
    </article-meta>
  </front>
  <body><sec><p>Source paper reported a large effect in the trial cohort.
  The effect was robust across sites <xref ref-type="bibr" rid="b1">1</xref>.
  We replicated it.</p></sec></body>
  <back><ref-list><ref id="b1"><label>1</label><element-citation>
    <article-title>Source Paper</article-title>
    <year>2020</year>
    <pub-id pub-id-type="doi">10.1000/source</pub-id>
  </element-citation></ref></ref-list></back>
</article>
"""

PAPERS = [
    CorpusPaper(pmcid="PMC1", pmid="42", doi="10.1000/source", role="source", rw_record_ids=("7",)),
    CorpusPaper(pmcid="PMC2", pmid="43", doi="10.1000/citer", role="citer"),
]
CITES = [CorpusCite(citer_pmcid="PMC2", source_pmcid="PMC1", contexts=1)]


def _cache(tmp_path: Path) -> Path:
    cache = tmp_path / "cache"
    (cache / "fulltext").mkdir(parents=True)
    (cache / "fulltext" / "PMC1.xml").write_text(SOURCE_XML, encoding="utf-8")
    (cache / "fulltext" / "PMC2.xml").write_text(CITER_XML, encoding="utf-8")
    return cache


def test_schema_v2_is_idempotent_cypher() -> None:
    assert SCHEMA_VERSION == 2
    assert all("IF NOT EXISTS" in statement for statement in SCHEMA_STATEMENTS)
    assert any("Paper" in statement and "UNIQUE" in statement for statement in SCHEMA_STATEMENTS)


def test_loader_is_idempotent_and_creates_contexts(tmp_path: Path) -> None:
    graph = InMemoryGraph()
    vectors = InMemoryVectorStore()
    embedder = HashEmbedder()
    cache = _cache(tmp_path)

    first = load_corpus(
        PAPERS,
        CITES,
        graph=graph,
        vectors=vectors,
        embedder=embedder,
        cache_dir=cache,
        run_id="run-1",
    )
    second = load_corpus(
        PAPERS,
        CITES,
        graph=graph,
        vectors=vectors,
        embedder=embedder,
        cache_dir=cache,
        run_id="run-1",
    )

    assert first.graph_counts == second.graph_counts
    assert first.vector_counts == second.vector_counts
    assert first.papers == 2
    assert first.cites == 1
    assert first.contexts == 1
    assert first.notices == 1
    assert first.graph_counts["Paper"] == 2
    assert first.graph_counts["CitationContext"] == 1
    assert first.graph_counts["CITES"] == 1
    assert first.graph_counts["POINTS_TO"] == 1
    assert first.graph_counts["RETRACTED_BY"] == 1
    assert first.vector_counts == {
        PAPERS_COLLECTION: 2,
        CLAIMS_COLLECTION: 0,
        CONTEXTS_COLLECTION: 1,
    }
    assert graph.papers["PMC1"]["title"] == "Source Paper"
    assert graph.papers["PMC2"]["is_citer"] is True
    assert graph.contexts["PMC2:p0:c0"]["source_pmcid"] == "PMC1"


def test_loader_rejects_cites_outside_the_manifest(tmp_path: Path) -> None:
    orphan = [CorpusCite(citer_pmcid="PMC2", source_pmcid="PMC999", contexts=0)]
    with pytest.raises(CorpusLoadError, match="outside the manifest"):
        load_corpus(
            PAPERS,
            orphan,
            graph=InMemoryGraph(),
            vectors=InMemoryVectorStore(),
            embedder=HashEmbedder(),
            cache_dir=_cache(tmp_path),
            run_id="run-1",
        )


def test_loader_rejects_a_cite_to_a_non_source(tmp_path: Path) -> None:
    backwards = [CorpusCite(citer_pmcid="PMC1", source_pmcid="PMC2", contexts=0)]
    with pytest.raises(CorpusLoadError, match="not a source"):
        load_corpus(
            PAPERS,
            backwards,
            graph=InMemoryGraph(),
            vectors=InMemoryVectorStore(),
            embedder=HashEmbedder(),
            cache_dir=_cache(tmp_path),
            run_id="run-1",
        )


def test_loader_fails_clearly_when_full_text_is_missing(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    (cache / "fulltext" / "PMC2.xml").unlink()
    with pytest.raises(CorpusLoadError, match="no cached full text"):
        load_corpus(
            PAPERS,
            CITES,
            graph=InMemoryGraph(),
            vectors=InMemoryVectorStore(),
            embedder=HashEmbedder(),
            cache_dir=cache,
            run_id="run-1",
        )


def test_loader_can_allow_missing_full_text(tmp_path: Path) -> None:
    cache = _cache(tmp_path)
    (cache / "fulltext" / "PMC2.xml").unlink()
    result = load_corpus(
        PAPERS,
        CITES,
        graph=InMemoryGraph(),
        vectors=InMemoryVectorStore(),
        embedder=HashEmbedder(),
        cache_dir=cache,
        run_id="run-1",
        require_fulltext=False,
    )
    assert result.missing_fulltext == 1
    assert result.contexts == 0


def test_hash_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashEmbedder()
    first = embedder.embed(["A claim about malaria", "Another claim"])
    second = embedder.embed(["A claim about malaria", "Another claim"])
    assert first == second
    assert len(first[0]) == 384
    assert abs(sum(value * value for value in first[0]) - 1.0) < 1e-9


def test_unknown_embedder_is_rejected() -> None:
    with pytest.raises(EmbeddingError):
        build_embedder("does-not-exist")
