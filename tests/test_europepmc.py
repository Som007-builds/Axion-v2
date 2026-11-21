"""Offline tests for the Europe PMC client (network test is opt-in)."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from axion.config.settings import Settings
from axion.ingest.europepmc import (
    EuropePmcClient,
    EuropePmcConfigurationError,
    EuropePmcNotFoundError,
    EuropePmcResponseError,
    TransportResponse,
)

_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<article article-type="research-article"><front><article-title>Test</article-title>'
    '</front><body><p>Hello <xref ref-type="bibr" rid="b1">1</xref>.</p></body></article>'
)

_SEARCH_JSON = {
    "hitCount": 2,
    "nextCursorMark": "AoE=",
    "resultList": {
        "result": [
            {
                "pmcid": "PMC123",
                "pmid": "111",
                "doi": "10.1/one",
                "title": "One",
                "journalTitle": "Journal A",
                "pubYear": "2021",
                "isOpenAccess": "Y",
                "inEPMC": "Y",
            },
            {
                "pmcid": None,
                "pmid": "222",
                "doi": None,
                "title": "Two",
                "pubYear": "",
                "isOpenAccess": "N",
                "inEPMC": "N",
            },
        ]
    },
}


@dataclass
class FakeTransport:
    responses: list[TransportResponse | Exception] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    headers: list[Mapping[str, str]] = field(default_factory=list)

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_s: float,
    ) -> TransportResponse:
        self.calls.append(url)
        self.headers.append(headers)
        if not self.responses:
            raise AssertionError("unexpected network request")
        outcome = self.responses.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _client(
    tmp_path: Path,
    transport: FakeTransport,
    *,
    contact_email: str | None = "person@example.org",
    clock: FakeClock | None = None,
    min_interval_s: float = 0.0,
    max_attempts: int = 3,
) -> EuropePmcClient:
    fake_clock = clock or FakeClock()
    return EuropePmcClient(
        tmp_path / "cache",
        contact_email=contact_email,
        base_url="https://example.test/rest",
        transport=transport,
        min_interval_s=min_interval_s,
        timeout_s=5.0,
        max_attempts=max_attempts,
        backoff_base_s=1.0,
        backoff_max_s=10.0,
        clock=fake_clock,
        sleep=fake_clock.sleep,
    )


def _response(payload: object, status: int = 200) -> TransportResponse:
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    return TransportResponse(status=status, body=body)


def test_search_parses_records_and_caches(tmp_path: Path) -> None:
    transport = FakeTransport([_response(_SEARCH_JSON)])
    client = _client(tmp_path, transport)

    page = client.search("TITLE_ABS:retraction", page_size=10)

    assert page.hit_count == 2
    assert page.next_cursor_mark == "AoE="
    first, second = page.records
    assert first.pmcid == "PMC123"
    assert first.year == 2021
    assert first.is_open_access is True
    assert first.has_full_text is True
    assert second.pmcid is None
    assert second.year is None
    assert second.is_open_access is False
    assert len(transport.calls) == 1
    assert "pageSize=10" in transport.calls[0]
    assert "cursorMark=%2A" in transport.calls[0]
    assert list((tmp_path / "cache" / "search").glob("*.json"))


def test_search_second_call_reads_cache(tmp_path: Path) -> None:
    transport = FakeTransport([_response(_SEARCH_JSON)])
    client = _client(tmp_path, transport)

    client.search("TITLE_ABS:retraction")
    page = client.search("TITLE_ABS:retraction")

    assert page.hit_count == 2
    assert len(transport.calls) == 1


def test_fetch_full_text_normalizes_and_caches(tmp_path: Path) -> None:
    transport = FakeTransport([_response(_XML.encode("utf-8"))])
    client = _client(tmp_path, transport)

    text = client.fetch_full_text("3257301")

    assert "<article" in text
    assert transport.calls[0].endswith("/PMC3257301/fullTextXML")
    assert (tmp_path / "cache" / "fulltext" / "PMC3257301.xml").exists()


def test_cached_full_text_needs_no_network_or_email(tmp_path: Path) -> None:
    transport = FakeTransport([_response(_XML.encode("utf-8"))])
    first = _client(tmp_path, transport)
    first.fetch_full_text("PMC3257301")

    offline_transport = FakeTransport([])
    offline = _client(tmp_path, offline_transport, contact_email=None)

    text = offline.fetch_full_text("PMC3257301")

    assert "<article" in text
    assert offline_transport.calls == []


def test_retry_with_backoff_then_success(tmp_path: Path) -> None:
    clock = FakeClock()
    transport = FakeTransport(
        [
            TransportResponse(status=503, body=b""),
            TransportResponse(status=429, body=b""),
            _response(_XML.encode("utf-8")),
        ]
    )
    client = _client(tmp_path, transport, clock=clock, max_attempts=3)

    text = client.fetch_full_text("PMC1")

    assert "<article" in text
    assert len(transport.calls) == 3
    assert clock.sleeps == [1.0, 2.0]


def test_retry_exhaustion_raises(tmp_path: Path) -> None:
    clock = FakeClock()
    transport = FakeTransport([TransportResponse(status=503, body=b"") for _ in range(3)])
    client = _client(tmp_path, transport, clock=clock, max_attempts=3)

    with pytest.raises(EuropePmcResponseError):
        client.fetch_full_text("PMC1")

    assert len(transport.calls) == 3


def test_transport_error_is_retried(tmp_path: Path) -> None:
    clock = FakeClock()
    transport = FakeTransport([OSError("connection reset"), _response(_XML.encode("utf-8"))])
    client = _client(tmp_path, transport, clock=clock)

    assert "<article" in client.fetch_full_text("PMC1")
    assert len(transport.calls) == 2


def test_404_is_not_retried(tmp_path: Path) -> None:
    transport = FakeTransport([TransportResponse(status=404, body=b"")])
    client = _client(tmp_path, transport)

    with pytest.raises(EuropePmcNotFoundError):
        client.fetch_full_text("PMC999999999")

    assert len(transport.calls) == 1


def test_non_retryable_status_raises(tmp_path: Path) -> None:
    transport = FakeTransport([TransportResponse(status=403, body=b"")])
    client = _client(tmp_path, transport)

    with pytest.raises(EuropePmcResponseError):
        client.search("anything")

    assert len(transport.calls) == 1


def test_requests_are_spaced_by_min_interval(tmp_path: Path) -> None:
    clock = FakeClock()
    transport = FakeTransport([_response(_SEARCH_JSON), _response(_SEARCH_JSON)])
    client = _client(tmp_path, transport, clock=clock, min_interval_s=1.0)

    client.search("query one")
    client.search("query two")

    assert clock.sleeps == [1.0]


def test_live_request_requires_contact_email(tmp_path: Path) -> None:
    transport = FakeTransport([])
    client = _client(tmp_path, transport, contact_email=None)

    with pytest.raises(EuropePmcConfigurationError):
        client.fetch_full_text("PMC1")

    assert transport.calls == []


def test_user_agent_identifies_client_and_contact(tmp_path: Path) -> None:
    transport = FakeTransport([_response(_XML.encode("utf-8"))])
    client = _client(tmp_path, transport)

    client.fetch_full_text("PMC1")

    agent = transport.headers[0]["User-Agent"]
    assert agent.startswith("RetractionScope/")
    assert "mailto:person@example.org" in agent


def test_invalid_pmcid_is_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path, FakeTransport([]))

    with pytest.raises(ValueError):
        client.fetch_full_text("../../etc/passwd")


def test_non_jats_response_is_rejected(tmp_path: Path) -> None:
    transport = FakeTransport([_response(b"<html>not jats</html>")])
    client = _client(tmp_path, transport)

    with pytest.raises(EuropePmcResponseError):
        client.fetch_full_text("PMC1")


def test_empty_query_is_rejected(tmp_path: Path) -> None:
    client = _client(tmp_path, FakeTransport([]))

    with pytest.raises(ValueError):
        client.search("  ")


def test_settings_resolve_cache_dir(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        data_dir=tmp_path,
        europepmc_contact_email="person@example.org",
    )

    assert settings.resolved_europepmc_cache_dir == tmp_path / "raw" / "europepmc"

    custom = Settings(_env_file=None, europepmc_cache_dir=tmp_path / "custom")
    assert custom.resolved_europepmc_cache_dir == tmp_path / "custom"


def test_find_by_doi_returns_matching_record(tmp_path: Path) -> None:
    transport = FakeTransport([TransportResponse(200, json.dumps(_SEARCH_JSON).encode())])
    client = _client(tmp_path, transport)
    record = client.find_by_doi("https://doi.org/10.1/ONE")
    assert record is not None
    assert record.pmcid == "PMC123"
    assert record.cited_by_count == 0
    assert "DOI%3A%2210.1%2Fone%22" in transport.calls[0]


def test_find_by_pmid_and_cited_by_count(tmp_path: Path) -> None:
    payload = {
        "hitCount": 1,
        "resultList": {"result": [{"pmid": "222", "doi": "10.1/two", "citedByCount": 7}]},
    }
    transport = FakeTransport([TransportResponse(200, json.dumps(payload).encode())])
    client = _client(tmp_path, transport)
    record = client.find_by_pmid("222")
    assert record is not None
    assert record.cited_by_count == 7
    assert "EXT_ID%3A222" in transport.calls[0]
    assert "SRC%3AMED" in transport.calls[0]


def test_citations_parse_and_cache(tmp_path: Path) -> None:
    payload = {
        "hitCount": 2,
        "citationList": {
            "citation": [
                {
                    "source": "MED",
                    "id": "333",
                    "title": "Citing paper",
                    "journalAbbreviation": "J Test",
                    "pubYear": 2024,
                    "citedByCount": 3,
                },
                {"source": "PPR", "id": "PPR1", "title": "Preprint"},
            ]
        },
    }
    transport = FakeTransport([TransportResponse(200, json.dumps(payload).encode())])
    client = _client(tmp_path, transport)
    page = client.citations("444")
    assert page.pmid == "444"
    assert page.hit_count == 2
    assert page.records[0].identifier == "333"
    assert page.records[0].journal_abbreviation == "J Test"
    assert page.records[1].source == "PPR"

    offline = _client(tmp_path, FakeTransport([]))
    assert offline.citations("444").hit_count == 2


def test_citations_validation_and_not_found(tmp_path: Path) -> None:
    client = _client(tmp_path, FakeTransport([]))
    with pytest.raises(ValueError, match="invalid PMID"):
        client.citations("PMC123")
    with pytest.raises(ValueError, match="page must be"):
        client.citations("123", page=0)
    with pytest.raises(ValueError, match="page_size"):
        client.citations("123", page_size=1001)

    not_found = _client(tmp_path / "nf", FakeTransport([TransportResponse(404, b"{}")]))
    with pytest.raises(EuropePmcNotFoundError):
        not_found.citations("123")


@pytest.mark.network
@pytest.mark.skipif(
    os.getenv("AXION_RUN_NETWORK") != "1",
    reason="network checks are opt-in; set AXION_RUN_NETWORK=1",
)
def test_known_pmcid_fetches_then_serves_from_cache(tmp_path: Path) -> None:
    settings = Settings()
    if not settings.europepmc_contact_email:
        pytest.skip("EUROPEPMC_CONTACT_EMAIL is not configured")

    client = EuropePmcClient(
        tmp_path / "cache",
        contact_email=settings.europepmc_contact_email,
        base_url=settings.europepmc_base_url,
        min_interval_s=settings.europepmc_min_interval_s,
        timeout_s=settings.europepmc_timeout_s,
        max_attempts=settings.europepmc_max_attempts,
    )
    text = client.fetch_full_text("PMC3257301")
    assert "<article" in text

    offline = EuropePmcClient(
        tmp_path / "cache",
        contact_email=None,
        transport=FakeTransport([]),
    )
    assert "<article" in offline.fetch_full_text("PMC3257301")
