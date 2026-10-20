# Data / Sources

## Status
Started

## Purpose

Own source discovery, provider adapters, and capability-level source selection. This module is the boundary between public or vendor APIs and the rest of the data layer.

## Capability Plan

Use the source catalog as the canonical free/free-key capability manifest:

| Capability | Preferred source order | Notes |
| --- | --- | --- |
| Universe and identifiers | SEC EDGAR -> Alpha Vantage -> OpenFIGI | SEC is authority for CIK/ticker mappings; OpenFIGI is identifier hygiene, not evidence. |
| Daily price and volume | Massive -> Stooq -> Alpha Vantage -> Finnhub -> FMP -> Marketstack | Massive is the preferred keyed REST source for U.S. daily aggregates; Stooq is a CSV fallback when its apikey is configured; licensed real-time data is out of MVP. |
| Company profile | SEC EDGAR -> Alpha Vantage -> Finnhub -> FMP | Provider sector/industry taxonomies require later normalization. |
| Financial statements | SEC EDGAR -> Alpha Vantage -> Finnhub -> FMP | SEC XBRL company facts are authority; vendor statements are convenience fallbacks. |
| Valuation | Alpha Vantage -> Finnhub -> FMP | Vendor ratios are raw convenience inputs and must be cached with retrieval time. |
| Filings and filing documents | SEC EDGAR -> Finnhub for metadata mirror only | SEC archive URLs are authority for public filing documents. |
| News | Alpha Vantage -> Finnhub -> FMP | Respect redistribution and report-display terms. |
| Transcripts | Alpha Vantage -> Finnhub | Coverage varies by provider and plan. |
| Analyst estimates | Alpha Vantage -> Finnhub | Missing estimates are explicit missing data, not neutral evidence. |
| Earnings calendar and corporate actions | Alpha Vantage -> Finnhub/FMP where applicable | Dates can change; monitor runs must refresh them. |
| Sector, benchmark, and macro context | FRED and Alpha Vantage, with Nasdaq Data Link as candidate | FRED is authority for macro series; Alpha Vantage topic news may provide bounded sector/theme context. |

## Current Adapters

- `sec_edgar`: CIK/ticker mappings, submissions, company facts, filing metadata, and filing document text.
- SEC filing metadata preserves `acceptanceDateTime` when the upstream value has
  a timezone, and the adapter can fetch only a validated submissions-history
  basename supplied by an outer exact plan.
- SEC filing acquisition reads the current submissions manifest once, parses
  `recent` and at most three manifest-declared history files whose official
  filing ranges overlap the request window, and deduplicates by accession before
  fetching bodies. Relevant history pages are visited newest first; one failed
  page does not discard filings from other pages. A capped or failed overlapping
  scan remains explicit as `history_truncated`/incomplete coverage rather than
  being reported as proof that no historical filing exists.
- Each acquired filing selects its source type independently, in request order,
  from the adapter's supported aliases using the shared
  [source-versus-form predicate](filing_orientation.md). Generic filing aliases
  retain their requested priority; exact aliases must match that filing's actual
  form. A multi-form request must not stamp all bodies with its first type.
  When no requested supported alias matches, do not fetch the body or fabricate
  another source type; leave the missing evidence as a gap. Preserve existing
  requested-form filtering, traversal/document budgets, IDs, acceptance instants
  and original records. This changes future production, not old persisted bytes.
- `massive`: U.S. equity daily OHLCV aggregate bars from the keyed Massive REST API.
- `stooq`: daily historical OHLCV CSV fallback, with `STOOQ_API_KEY` support because the CSV download can require a captcha-issued apikey.
- `alpha_vantage`: listing status, daily prices, overview, statements, earnings, estimates, symbol and topic news sentiment, transcripts, ETF profile, and selected macro endpoints.
- Raw transcript responses remain available through the provider client and
  managed raw cache. Provider earnings dates and fiscal-quarter echoes cannot
  establish when complete conference content was publicly available. Automatic
  transcript acquisition currently has no reviewed public-content proof input
  and must return `historical_data_unavailable` before making provider requests,
  rather than minting PIT documents from `reportedDate`. This is an explicit
  acquisition limitation, not evidence that a conference or its content did not
  exist. Existing local documents, raw responses and unrelated acquisition
  capabilities remain intact. A proof-backed materializer and its normal
  capability controls remain open under the approved
  [transcript availability policy](resolution.md); this guard does not complete
  transcript support or authorize old unreviewed records for a successor.
- Historical company-news backfills may call Alpha Vantage with an exact ticker,
  UTC `time_from`/`time_to`, sort order, and limit. A 1,000-row response is a
  saturation signal, not proof of complete coverage; stored Raw Info contains
  provider title/summary only and never scrapes the linked publisher body.
- `fred`: macro series metadata and vintage-aware observations.
- `openfigi`: optional-key identifier mapping.
- `finnhub`: fallback profile, news, financial metrics, filings mirror, estimates, earnings calendar, and transcripts.

## Runtime State

The source layer owns these runtime state primitives:

- `RawDataCache`: file-backed raw JSON/text cache keyed by source, capability, endpoint, and sanitized request parameters. Credential query parameters such as `apiKey`/`apikey`, `api_key`, `token`, and `access_key` must not be included in cache keys or records. A provider response detector may invalidate exactly one contaminated key; it never clears unrelated valid cache entries or append-only Raw Info.
- `RequestLedger`: append-only JSONL ledger recording `fetched`, `cache_hit`, `cache_invalidated`, `error`, and `quota_deferred` outcomes with timestamps, cache keys, source keys, capabilities, and retry times when known. Cache invalidation is local maintenance and does not count as a network request.
- `SourceQuota` and `SourceBudget`: source-level quota rules and checks. Network fetches and upstream errors count against quota; cache hits and quota deferrals do not.
- `ManagedHttpTransport`: optional transport wrapper that applies the same configured provider-response detector to cache hits and fresh network bodies before either is accepted as successful. A rejected cached body is invalidated by exact key before normal budget/acquisition flow resumes; a rejected network body is never cached. Only validated bodies record `cache_hit` or `fetched`. Request-derived secrets are redacted before transport errors enter the ledger, and a recognized provider quota envelope raises `DataQuotaDeferred` instead of becoming a generic successful response. A provider that does not supply a reliable reset time may set `next_retry_at` to null rather than inventing one.

Raw cache records must be replaced atomically after a complete fsynced write,
and request-ledger rows must be flushed before a caller treats a request outcome
as durable.

The data layer decides whether a request is currently allowed and whether cached data exists. It does not decide how to spend tomorrow's quota. Cold-start and live-run orchestration will prioritize pending jobs and resume them after reset windows.

## Responsibilities

- Keep vendor-specific schemas inside adapters.
- Normalize only low-risk shared records at this layer, such as `SecurityListing`, `PriceBar`, and `FilingMetadata`.
- Preserve provider key, URL, retrieval time, source publication time when available, and raw response cache eligibility.
- Expose capability selection through `source_plan_by_capability()` and `select_source_for_capability()`.
- Raise explicit, secret-redacted data-source errors for missing credentials, rate-limit messages, malformed upstream responses, and unsupported transports.
- Decode common compressed HTTP responses before JSON/CSV parsing, and surface malformed response bodies as explicit data-source errors.
- Keep raw cache and request ledger records source-linked and secret-safe.
- Allow historical backfill orchestration to reuse exact SEC primary-document
  URLs through the managed cache/quota transport; selection and Raw Info
  persistence remain outside the provider adapter.
- Treat `10-K`, `10-Q`, `8-K`, `20-F`, `40-F`, and `6-K` as known SEC operating
  report forms. Generic filing requests may use the form applicable to the
  issuer; an exact-form request never substitutes another member of the family.
- Allow label-free expanded-case acquisition to fetch exact per-CIK SEC
  submissions JSON through the same managed transport. Secondary submissions
  files and primary documents must be derived into new exact plans rather than
  followed as an unbounded crawl.
- Allow the same label-free scope to fetch exact per-CIK SEC Company Facts JSON
  under the `financial_statements` capability. The adapter returns provider raw
  data; accession grouping, historical availability, and Raw Info persistence
  remain in backfill orchestration.

## Invariants

- Provider clients may fetch raw data but must not decide scores, thesis state, or trading action.
- A capability with multiple sources must have a deterministic preference order and fallback list.
- A convenience vendor value cannot override SEC authority data without a later normalization rule.
- Sources that are not formal APIs, such as CSV downloads, must be labeled as such in the catalog caveat.
- No adapter may write credentials to public config, reports, memory, or logs.
- Adapter code must not wait until tomorrow for quota reset; it should return an explicit deferred state through `DataQuotaDeferred`.

## Testing

Use fake transports to verify URL construction, credential lookup, source registration, source selection, rate-limit errors, compressed response decoding, point-in-time filtering, raw cache hits, request ledger entries, quota deferrals, upstream error recording, and normalization of listing, price, and filing metadata.
