"""Polite Europe PMC REST client with a deterministic raw cache.

Only the Open Access JATS endpoints used by the project are wrapped: metadata
search and full-text XML by PMCID. The client identifies itself with a
configured contact email, spaces requests by a minimum interval, retries
transient failures with exponential backoff, and never logs response bodies.

The raw cache stores provider responses byte-for-byte under deterministic
names. Full text is written to ``<cache>/fulltext/<PMCID>.xml`` and search
responses to ``<cache>/search/<sha256>.json``, so a repeated call is offline
and reproducible.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from axion.config.settings import Settings

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest"
_USER_AGENT = "RetractionScope/0.1 (https://github.com/Som007-builds/retractionscope)"

_PMCID_PATTERN = re.compile(r"^PMC\d+$")
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


class EuropePmcError(Exception):
    """Base class for Europe PMC client failures."""


class EuropePmcConfigurationError(EuropePmcError):
    """Raised when the client is not configured for polite live requests."""


class EuropePmcNotFoundError(EuropePmcError):
    """Raised when Europe PMC has no record or full text for an identifier."""


class EuropePmcResponseError(EuropePmcError):
    """Raised for an unexpected status or malformed provider response."""


@dataclass(frozen=True)
class TransportResponse:
    status: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


class HttpTransport(Protocol):
    """Minimal GET transport; swapped for a fake in offline tests."""

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_s: float,
    ) -> TransportResponse: ...


class UrllibTransport:
    """Standard-library HTTP transport. HTTP errors are returned, not raised."""

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str],
        timeout_s: float,
    ) -> TransportResponse:
        request = urllib.request.Request(url, headers=dict(headers), method="GET")
        try:
            with urllib.request.urlopen(request, timeout=timeout_s) as response:
                return TransportResponse(
                    status=int(response.status),
                    body=response.read(),
                    headers=dict(response.headers),
                )
        except urllib.error.HTTPError as exc:
            return TransportResponse(
                status=int(exc.code),
                body=exc.read(),
                headers=dict(exc.headers or {}),
            )
        except urllib.error.URLError as exc:
            raise OSError(str(exc.reason)) from exc


@dataclass(frozen=True)
class EuropePmcRecord:
    """One search result, normalized to the fields the corpus needs."""

    pmcid: str | None
    pmid: str | None
    doi: str | None
    title: str | None
    journal_title: str | None
    year: int | None
    is_open_access: bool | None
    has_full_text: bool | None
    cited_by_count: int = 0


@dataclass(frozen=True)
class SearchPage:
    query: str
    records: tuple[EuropePmcRecord, ...]
    hit_count: int
    next_cursor_mark: str | None


@dataclass(frozen=True)
class CitationRecord:
    """One paper citing a target paper, as listed by Europe PMC."""

    source: str
    identifier: str
    title: str | None
    journal_abbreviation: str | None
    pub_year: int | None
    cited_by_count: int


@dataclass(frozen=True)
class CitationPage:
    pmid: str
    records: tuple[CitationRecord, ...]
    hit_count: int


class _ResultItem(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    pmcid: str | None = None
    pmid: str | None = None
    doi: str | None = None
    title: str | None = None
    journal_title: str | None = Field(default=None, alias="journalTitle")
    pub_year: int | None = Field(default=None, alias="pubYear")
    is_open_access: bool | None = Field(default=None, alias="isOpenAccess")
    in_epmc: bool | None = Field(default=None, alias="inEPMC")
    cited_by_count: int = Field(default=0, alias="citedByCount")

    @field_validator("pub_year", mode="before")
    @classmethod
    def _empty_year_to_none(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return int(stripped) if stripped.isdigit() else None
        return value

    @field_validator("is_open_access", "in_epmc", mode="before")
    @classmethod
    def _yes_no_to_bool(cls, value: object) -> object:
        if isinstance(value, str):
            if value.strip().upper() == "Y":
                return True
            if value.strip().upper() == "N":
                return False
            return None
        return value

    def to_record(self) -> EuropePmcRecord:
        return EuropePmcRecord(
            pmcid=self.pmcid,
            pmid=self.pmid,
            doi=self.doi,
            title=self.title,
            journal_title=self.journal_title,
            year=self.pub_year,
            is_open_access=self.is_open_access,
            has_full_text=self.in_epmc,
            cited_by_count=self.cited_by_count,
        )


class _CitationItem(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    source: str
    id: str
    title: str | None = None
    journal_abbreviation: str | None = Field(default=None, alias="journalAbbreviation")
    pub_year: int | None = Field(default=None, alias="pubYear")
    cited_by_count: int = Field(default=0, alias="citedByCount")

    def to_record(self) -> CitationRecord:
        return CitationRecord(
            source=self.source,
            identifier=self.id,
            title=self.title,
            journal_abbreviation=self.journal_abbreviation,
            pub_year=self.pub_year,
            cited_by_count=self.cited_by_count,
        )


class _CitationList(BaseModel):
    model_config = ConfigDict(extra="ignore")

    citation: list[_CitationItem] = Field(default_factory=list)


class _CitationsResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    hit_count: int = Field(default=0, alias="hitCount")
    citation_list: _CitationList | None = Field(default=None, alias="citationList")


class _ResultList(BaseModel):
    model_config = ConfigDict(extra="ignore")

    result: list[_ResultItem] = Field(default_factory=list)


class _SearchResponse(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    hit_count: int = Field(default=0, alias="hitCount")
    next_cursor_mark: str | None = Field(default=None, alias="nextCursorMark")
    result_list: _ResultList | None = Field(default=None, alias="resultList")


class EuropePmcClient:
    """Search and fetch Europe PMC OA content with polite throttling."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        contact_email: str | None,
        base_url: str = DEFAULT_BASE_URL,
        transport: HttpTransport | None = None,
        min_interval_s: float = 1.0,
        timeout_s: float = 30.0,
        max_attempts: int = 3,
        backoff_base_s: float = 1.0,
        backoff_max_s: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if min_interval_s < 0:
            raise ValueError("min_interval_s must be non-negative")
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._cache_dir = cache_dir
        self._contact_email = (contact_email or "").strip()
        self._base_url = base_url.rstrip("/")
        self._transport = transport or UrllibTransport()
        self._min_interval_s = min_interval_s
        self._timeout_s = timeout_s
        self._max_attempts = max_attempts
        self._backoff_base_s = backoff_base_s
        self._backoff_max_s = backoff_max_s
        self._clock = clock
        self._sleep = sleep
        self._last_request_at: float | None = None
        self._throttle_lock = threading.Lock()

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        transport: HttpTransport | None = None,
    ) -> EuropePmcClient:
        """Build a client from application settings."""
        return cls(
            settings.resolved_europepmc_cache_dir,
            contact_email=settings.europepmc_contact_email,
            base_url=settings.europepmc_base_url,
            transport=transport,
            min_interval_s=settings.europepmc_min_interval_s,
            timeout_s=settings.europepmc_timeout_s,
            max_attempts=settings.europepmc_max_attempts,
        )

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    def search(
        self,
        query: str,
        *,
        page_size: int = 25,
        cursor_mark: str = "*",
        force: bool = False,
    ) -> SearchPage:
        """Run one metadata search page and cache the raw JSON response."""
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")

        params: dict[str, str] = {
            "query": query,
            "format": "json",
            "pageSize": str(page_size),
            "cursorMark": cursor_mark,
            "resultType": "core",
        }
        cache_path = self._cache_dir / "search" / f"{_cache_key(params)}.json"
        body = self._read_cache(cache_path) if not force else None
        if body is None:
            url = f"{self._base_url}/search?{urllib.parse.urlencode(params)}"
            body = self._request(url, not_found="search response")
            self._write_cache(cache_path, body)

        parsed = _parse_json(body, cache_path)
        try:
            response = _SearchResponse.model_validate(parsed)
        except Exception as exc:  # pydantic.ValidationError
            raise EuropePmcResponseError(f"unexpected search response shape: {exc}") from exc

        records = tuple(
            item.to_record()
            for item in (response.result_list.result if response.result_list else [])
        )
        return SearchPage(
            query=query,
            records=records,
            hit_count=response.hit_count,
            next_cursor_mark=response.next_cursor_mark,
        )

    def find_by_doi(self, doi: str) -> EuropePmcRecord | None:
        """Resolve one DOI to a Europe PMC record, or ``None`` when absent."""
        normalized = _normalize_doi(doi)
        page = self.search(f'DOI:"{normalized}"', page_size=1)
        for record in page.records:
            if record.doi and _normalize_doi(record.doi) == normalized:
                return record
        return page.records[0] if page.records else None

    def find_by_pmid(self, pmid: str) -> EuropePmcRecord | None:
        """Resolve one MEDLINE id to a Europe PMC record."""
        normalized = _normalize_pmid(pmid)
        page = self.search(f"EXT_ID:{normalized} AND SRC:MED", page_size=1)
        return page.records[0] if page.records else None

    def citations(
        self, pmid: str, *, page: int = 1, page_size: int = 1000, force: bool = False
    ) -> CitationPage:
        """Return one page of papers citing ``pmid``.

        Europe PMC exposes citations by MEDLINE id (``MED/<pmid>/citations``);
        a PMCID path returns 404, so callers must resolve a PMID first.
        """
        normalized = _normalize_pmid(pmid)
        if page < 1:
            raise ValueError("page must be at least 1")
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size must be between 1 and 1000")
        params = {
            "format": "json",
            "page": str(page),
            "pageSize": str(page_size),
        }
        cache_path = self._cache_dir / "citations" / f"MED-{normalized}-p{page}-n{page_size}.json"
        body = self._read_cache(cache_path) if not force else None
        if body is None:
            url = (
                f"{self._base_url}/MED/{normalized}/citations?" f"{urllib.parse.urlencode(params)}"
            )
            body = self._request(url, not_found=f"citations for PMID {normalized}")
            self._write_cache(cache_path, body)

        parsed = _parse_json(body, cache_path)
        try:
            response = _CitationsResponse.model_validate(parsed)
        except Exception as exc:  # pydantic.ValidationError
            raise EuropePmcResponseError(f"unexpected citations response: {exc}") from exc

        records = tuple(
            item.to_record()
            for item in (response.citation_list.citation if response.citation_list else [])
        )
        return CitationPage(pmid=normalized, records=records, hit_count=response.hit_count)

    def fetch_full_text(self, pmcid: str, *, force: bool = False) -> str:
        """Return JATS full text for an OA PMCID, using the raw cache first."""
        normalized = _normalize_pmcid(pmcid)
        cache_path = self._cache_dir / "fulltext" / f"{normalized}.xml"
        cached = self._read_cache(cache_path)
        if cached is not None and not force:
            return _decode_xml(cached, cache_path)

        url = f"{self._base_url}/{normalized}/fullTextXML"
        body = self._request(url, not_found=f"full text for {normalized}")
        text = _decode_xml(body, cache_path)
        self._write_cache(cache_path, body)
        return text

    def _request(self, url: str, *, not_found: str) -> bytes:
        if not self._contact_email:
            raise EuropePmcConfigurationError(
                "set EUROPEPMC_CONTACT_EMAIL before making live Europe PMC requests"
            )

        headers = {
            "User-Agent": f"{_USER_AGENT} mailto:{self._contact_email}",
            "Accept": "application/xml, application/json;q=0.9, */*;q=0.8",
        }
        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            self._throttle()
            try:
                response = self._transport.get(url, headers=headers, timeout_s=self._timeout_s)
            except OSError as exc:
                last_error = exc
                logger.warning(
                    "Europe PMC transport error (attempt %s/%s)",
                    attempt,
                    self._max_attempts,
                )
            else:
                if 200 <= response.status < 300:
                    if not response.body.strip():
                        raise EuropePmcResponseError("Europe PMC returned an empty body")
                    return response.body
                if response.status == 404:
                    raise EuropePmcNotFoundError(f"Europe PMC has no {not_found}")
                if response.status not in _RETRYABLE_STATUS:
                    raise EuropePmcResponseError(
                        f"Europe PMC returned HTTP {response.status} for {not_found}"
                    )
                last_error = EuropePmcResponseError(
                    f"Europe PMC returned HTTP {response.status} for {not_found}"
                )
                logger.warning(
                    "Europe PMC HTTP %s (attempt %s/%s)",
                    response.status,
                    attempt,
                    self._max_attempts,
                )

            if attempt < self._max_attempts:
                self._sleep(self._backoff(attempt))

        raise EuropePmcResponseError(
            f"Europe PMC request failed after {self._max_attempts} attempts: {last_error}"
        )

    def _throttle(self) -> None:
        # The lock keeps the shared request rate polite when callers use a
        # thread pool for high-latency full-text downloads.
        with self._throttle_lock:
            if self._last_request_at is not None and self._min_interval_s > 0:
                elapsed = self._clock() - self._last_request_at
                remaining = self._min_interval_s - elapsed
                if remaining > 0:
                    self._sleep(remaining)
            self._last_request_at = self._clock()

    def _backoff(self, attempt: int) -> float:
        return min(self._backoff_max_s, self._backoff_base_s * (2.0 ** (attempt - 1)))

    def _read_cache(self, path: Path) -> bytes | None:
        try:
            return path.read_bytes()
        except FileNotFoundError:
            return None

    def _write_cache(self, path: Path, body: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(body)
        temporary.replace(path)


def _normalize_pmcid(pmcid: str) -> str:
    normalized = pmcid.strip().upper()
    if not normalized.startswith("PMC"):
        normalized = f"PMC{normalized}"
    if not _PMCID_PATTERN.match(normalized):
        raise ValueError(f"invalid PMCID: {pmcid!r}")
    return normalized


def _normalize_pmid(pmid: str) -> str:
    normalized = pmid.strip()
    if not normalized.isdigit():
        raise ValueError(f"invalid PMID: {pmid!r}")
    return normalized


def _normalize_doi(doi: str) -> str:
    normalized = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix) :]
    if not normalized:
        raise ValueError(f"invalid DOI: {doi!r}")
    return normalized


def _decode_xml(body: bytes, path: Path) -> str:
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EuropePmcResponseError(f"full text is not UTF-8: {path}") from exc
    if "<article" not in text[:4_000]:
        raise EuropePmcResponseError(f"response is not JATS XML: {path}")
    return text


def _cache_key(params: Mapping[str, str]) -> str:
    encoded = json.dumps(dict(sorted(params.items())), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _parse_json(body: bytes, path: Path) -> Any:
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise EuropePmcResponseError(f"invalid JSON from Europe PMC: {path}") from exc
