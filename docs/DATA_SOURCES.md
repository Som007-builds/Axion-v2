# Data sources, licences, and terms

**Verification date:** 2026-11-14. This file records what was observed from public, read-only sources. It is not legal advice. Rows marked **owner approved** may be used under the conditions listed; all other rows remain **owner to confirm**.

| Source | What we use | Access | Licence / terms | Verified on | Redistribution allowed? | Owner to confirm |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| Europe PMC — Open Access subset | JATS/full-text XML and metadata for OA articles | REST API, SOAP, OAI, FTP; OA XML updated weekly, OA PDF monthly | Articles remain copyrighted; made available under a Creative Commons licence, or similar, that generally allows more liberal redistribution and reuse; **the licence statement in each article controls**, and licences are not identical. Non-OA full text is not in this subset. Source: <https://europepmc.org/downloads/openaccess> | 2026-11-14 | Only as the per-article licence permits; no blanket redistribution. Verify each article's licence before caching or releasing full text. | **Owner to confirm** |
| Europe PMC — REST API | Search, metadata, and full-text links/XML for OA content | `https://www.ebi.ac.uk/europepmc/webservices/rest/` | REST page describes access and output formats and links the Privacy Notice. No numeric rate limit was published on the accessible page; no rate-limit headers were observed on one 2026-11-14 request. This does not prove unlimited use. Source: <https://europepmc.org/RestfulWebService> | 2026-11-14 | Do not redistribute API responses as a dataset unless the underlying article licence allows it. | **Owner to confirm** |
| Europe PMC — polite usage / rate limits | Request etiquette for the REST API | HTTP GET with identifying User-Agent | **Unclear:** the REST page we could access does not state a numeric limit; the site terms/copyright pages returned bot-verification blocks during this check. Treat the service as shared infrastructure: cache, throttle, identify the client, and ask the helpdesk before bulk work. | 2026-11-14 | N/A (usage rule, not a content licence) | **Owner to confirm** |
| Crossref — Retraction Watch via REST API | Retraction/update records linked to works | `https://api.crossref.org/v1/works?filter=update-type:retraction`; per-DOI lookups via `works/{doi}` and `update-to` with `source` = `publisher` or `retraction-watch` | Crossref Metadata Retrieval lists `Open Funder Registry, Retraction Watch database` with licence **CC0** (<https://www.crossref.org/documentation/retrieve-metadata/>, verified 2026-11-14). The retraction page describes the API path; observed `update-to` fields on 2026-11-14 were `DOI`, `type`, `label`, `source`, `updated`, `record-id`. Source: <https://www.crossref.org/documentation/retrieve-metadata/retraction-watch/> | 2026-11-14 | CC0 permits redistribution; project policy still prefers IDs/manifests over raw dumps. Cite Crossref and Retraction Watch. | **Owner approved 2026-11-14** |
| Crossref — Retraction Watch CSV | Full retraction/update database for loading and linking | Bulk snapshot: `git clone https://gitlab.com/crossref/retraction-watch-data` or the pinned raw URL; CSV updated once per working day | Crossref Metadata Retrieval lists the **Retraction Watch database as CC0** (<https://www.crossref.org/documentation/retrieve-metadata/>, verified 2026-11-14). The repository itself has no `LICENSE` file. The owner reported a third-party page claiming “non-commercial research purposes”; that claim is **unofficial**, was not found on the canonical Crossref page, and does not override Crossref's published CC0 statement. | 2026-11-14 | CC0 permits redistribution, but project policy: **never commit the raw CSV**; commit ID-only manifests with snapshot provenance. Cite Crossref and Retraction Watch in outputs. | **Owner approved 2026-11-14** |
| Crossref — polite pool / rate limits | Request etiquette for the REST API | HTTPS with `mailto` in the query or User-Agent | Crossref's API documentation asks clients to cache, monitor latency, back off, and identify themselves with a contact email. It states that active limits are advertised in `X-Rate-Limit-Limit` and `X-Rate-Limit-Interval`. A single public request on 2026-11-14 returned `x-rate-limit-limit: 1`, `x-rate-limit-interval: 1s`, `x-concurrency-limit: 1`, `x-api-pool: public-array`. Source: <https://github.com/CrossRef/rest-api-doc> | 2026-11-14 | N/A (usage rule, not a content licence) | **Owner to confirm** |

## Retraction Watch CSV fields

The repository README lists these columns (source: <https://gitlab.com/crossref/retraction-watch-data/-/raw/main/README.md>):

`Record ID`, `Title`, `Subject`, `Institution`, `Journal`, `Publisher`, `Country`, `Author`, `URLS`, `ArticleType`, `RetractionDate`, `RetractionDOI`, `RetractionPubMedID`, `OriginalPaperDate`, `OriginalPaperDOI`, `OriginalPaperPubMedID`, `RetractionNature`, `Reason`, `Paywalled`, `Notes`.

The README notes that lists inside a field are separated by semicolons, that `RetractionNature` can be Retraction, Correction, Expression of concern, or Reinstatement, and that blank/`unavailable`/`0` values occur in DOI/PubMed-ID fields. Use the Retraction Watch field guide for controlled vocabularies: <https://retractionwatch.com/retraction-watch-database-user-guide/>.

## Retraction Watch acquisition log

| Date | Snapshot commit | Snapshot label | CSV SHA-256 | Rows | Notes |
| :-- | :-- | :-- | :-- | --: | :-- |
| 2026-11-14 | `560ad745cb621e240501422ad485bd81b4590860` | `Retraction Watch data for 2026-11-13` | `4D0509F648EC6DC7F7DE43A2260943ED15C56B239D882D73F468F4F40EF917DD` | 73,822 | Pinned raw URL; downloaded to `data/retraction-watch/` (untracked). No raw CSV committed. |

Crossref REST API is used for per-DOI lookups; the GitLab CSV snapshot is used for bulk loading. Re-download only by pinning a new commit hash and recording it here.

## Rules

1. **Per-article licence wins.** Europe PMC's OA subset is not one uniform licence; check the article-level statement before using or redistributing full text.
2. **No raw full text in git.** Cache raw JATS/XML/PDF locally under `data/` (gitignored); commit IDs, manifests, and derived labels only when the terms allow. **Exception:** `tests/fixtures/jats/` holds a small set of parser fixtures that are **CC BY only**, with attribution, licence, source URL, and hashes in `tests/fixtures/jats/manifest.json`. No NC/ND or unclear-licence full text is committed.
3. **Retraction Watch is CC0 but stays local.** The owner approved use on 2026-11-14. Cite Crossref and Retraction Watch. Do not commit the raw CSV; commit ID-only manifests with snapshot commit, date, and SHA-256.
4. **Polite clients.** Send a real contact email from local `.env`, use HTTPS, cache, throttle, and back off. Do not send API keys or other secrets to data providers.
5. **Record changes.** If a provider publishes new terms, update this file and the verification date; do not silently rely on this snapshot.

## Open questions for the owner

- Does Europe PMC require a specific rate-limit or bulk-access arrangement beyond polite throttling? The accessible REST page does not publish a number, and the terms page was blocked during verification.
- May Axion release derived labels and citation contexts that quote short spans from OA articles, subject to each article's licence? This affects P5-02.
