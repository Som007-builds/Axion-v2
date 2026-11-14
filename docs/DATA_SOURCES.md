# Data sources, licences, and terms

**Verification date:** 2026-11-14. This file records what was observed from public, read-only sources. It is not legal advice. Every row is **owner to confirm** before use, redistribution, or release.

| Source | What we use | Access | Licence / terms | Verified on | Redistribution allowed? | Owner to confirm |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| Europe PMC — Open Access subset | JATS/full-text XML and metadata for OA articles | REST API, SOAP, OAI, FTP; OA XML updated weekly, OA PDF monthly | Articles remain copyrighted; made available under a Creative Commons licence, or similar, that generally allows more liberal redistribution and reuse; **the licence statement in each article controls**, and licences are not identical. Non-OA full text is not in this subset. Source: <https://europepmc.org/downloads/openaccess> | 2026-11-14 | Only as the per-article licence permits; no blanket redistribution. Verify each article's licence before caching or releasing full text. | **Owner to confirm** |
| Europe PMC — REST API | Search, metadata, and full-text links/XML for OA content | `https://www.ebi.ac.uk/europepmc/webservices/rest/` | REST page describes access and output formats and links the Privacy Notice. No numeric rate limit was published on the accessible page; no rate-limit headers were observed on one 2026-11-14 request. This does not prove unlimited use. Source: <https://europepmc.org/RestfulWebService> | 2026-11-14 | Do not redistribute API responses as a dataset unless the underlying article licence allows it. | **Owner to confirm** |
| Europe PMC — polite usage / rate limits | Request etiquette for the REST API | HTTP GET with identifying User-Agent | **Unclear:** the REST page we could access does not state a numeric limit; the site terms/copyright pages returned bot-verification blocks during this check. Treat the service as shared infrastructure: cache, throttle, identify the client, and ask the helpdesk before bulk work. | 2026-11-14 | N/A (usage rule, not a content licence) | **Owner to confirm** |
| Crossref — Retraction Watch via REST API | Retraction/update records linked to works | `https://api.crossref.org/v1/works?filter=update-type:retraction`; records appear in `update-to` with `source` = `publisher` or `retraction-watch` | Crossref documentation describes the API path. The `update-to` fields observed on 2026-11-14 were `DOI`, `type`, `label`, `source`, `updated`, `record-id`. Source: <https://www.crossref.org/documentation/retrieve-metadata/retraction-watch/> | 2026-11-14 | **Unclear for the Retraction Watch data**; do not redistribute raw records until the owner confirms. Crossref metadata may have separate terms. | **Owner to confirm** |
| Crossref — Retraction Watch CSV | Full retraction/update database for loading and linking | `git clone https://gitlab.com/crossref/retraction-watch-data`; CSV updated once per working day; the README snapshot was generated 2026-11-12 | **Licence not stated in the repository.** The repo contains `README.md` and `retraction_watch.csv`; there is no `LICENSE` file. The Crossref documentation page footer says *site content* is CC BY 4.0, but that statement does not clearly license the dataset. **Unclear / potentially conflicting; owner must confirm.** Sources: <https://gitlab.com/crossref/retraction-watch-data> and <https://www.crossref.org/documentation/retrieve-metadata/retraction-watch/> | 2026-11-14 | **No by default until confirmed.** Do not release raw CSV or substantial derived text. | **Owner to confirm** |
| Crossref — polite pool / rate limits | Request etiquette for the REST API | HTTPS with `mailto` in the query or User-Agent | Crossref's API documentation asks clients to cache, monitor latency, back off, and identify themselves with a contact email. It states that active limits are advertised in `X-Rate-Limit-Limit` and `X-Rate-Limit-Interval`. A single public request on 2026-11-14 returned `x-rate-limit-limit: 1`, `x-rate-limit-interval: 1s`, `x-concurrency-limit: 1`, `x-api-pool: public-array`. Source: <https://github.com/CrossRef/rest-api-doc> | 2026-11-14 | N/A (usage rule, not a content licence) | **Owner to confirm** |

## Retraction Watch CSV fields

The repository README lists these columns (source: <https://gitlab.com/crossref/retraction-watch-data/-/raw/main/README.md>):

`Record ID`, `Title`, `Subject`, `Institution`, `Journal`, `Publisher`, `Country`, `Author`, `URLS`, `ArticleType`, `RetractionDate`, `RetractionDOI`, `RetractionPubMedID`, `OriginalPaperDate`, `OriginalPaperDOI`, `OriginalPaperPubMedID`, `RetractionNature`, `Reason`, `Paywalled`, `Notes`.

The README notes that lists inside a field are separated by semicolons, that `RetractionNature` can be Retraction, Correction, Expression of concern, or Reinstatement, and that blank/`unavailable`/`0` values occur in DOI/PubMed-ID fields. Use the Retraction Watch field guide for controlled vocabularies: <https://retractionwatch.com/retraction-watch-database-user-guide/>.

## Rules

1. **Per-article licence wins.** Europe PMC's OA subset is not one uniform licence; check the article-level statement before using or redistributing full text.
2. **No raw full text in git.** Cache raw JATS/XML/PDF locally under `data/` (gitignored); commit IDs, manifests, and derived labels only when the terms allow.
3. **Retraction Watch licence is unresolved.** Until the owner confirms, treat the CSV and substantial extracts as non-redistributable.
4. **Polite clients.** Send a real contact email from local `.env`, use HTTPS, cache, throttle, and back off. Do not send API keys or other secrets to data providers.
5. **Record changes.** If a provider publishes new terms, update this file and the verification date; do not silently rely on this snapshot.

## Open questions for the owner

- What is the current licence and redistribution policy for the Retraction Watch CSV? The repository has no `LICENSE`; the Crossref documentation page's CC BY 4.0 footer is about site content, not clearly the dataset.
- Does Europe PMC require a specific rate-limit or bulk-access arrangement beyond polite throttling? The accessible REST page does not publish a number, and the terms page was blocked during verification.
- May Axion release derived labels and citation contexts that quote short spans from OA articles, subject to each article's licence? This affects P5-02.
