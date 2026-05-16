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
| Sector, benchmark, and macro context | FRED and Alpha Vantage, with Nasdaq Data Link as candidate | FRED is authority for macro series. |

## Current Adapters

- `sec_edgar`: CIK/ticker mappings, submissions, company facts, filing metadata, and filing document text.
- `massive`: U.S. equity daily OHLCV aggregate bars from the keyed Massive REST API.
- `stooq`: daily historical OHLCV CSV fallback, with `STOOQ_API_KEY` support because the CSV download can require a captcha-issued apikey.
- `alpha_vantage`: listing status, daily prices, overview, statements, earnings, estimates, news sentiment, transcripts, ETF profile, and selected macro endpoints.
- `fred`: macro series metadata and vintage-aware observations.
- `openfigi`: optional-key identifier mapping.
- `finnhub`: fallback profile, news, financial metrics, filings mirror, estimates, earnings calendar, and transcripts.

## Runtime State

The source layer owns these runtime state primitives:

- `RawDataCache`: file-backed raw JSON/text cache keyed by source, capability, endpoint, and sanitized request parameters. Credential query parameters such as `apiKey`/`apikey`, `api_key`, `token`, and `access_key` must not be included in cache keys or records.
- `RequestLedger`: append-only JSONL ledger recording `fetched`, `cache_hit`, `error`, and `quota_deferred` outcomes with timestamps, cache keys, source keys, capabilities, and retry times when known.
- `SourceQuota` and `SourceBudget`: source-level quota rules and checks. Network fetches and upstream errors count against quota; cache hits and quota deferrals do not.
- `ManagedHttpTransport`: optional transport wrapper that applies cache lookup before quota checks, lets callers reject provider-level error payloads before caching, records every outcome, and raises `DataQuotaDeferred` instead of sleeping across reset windows.

The data layer decides whether a request is currently allowed and whether cached data exists. It does not decide how to spend tomorrow's quota. Cold-start and live-run orchestration will prioritize pending jobs and resume them after reset windows.

## Responsibilities

- Keep vendor-specific schemas inside adapters.
- Normalize only low-risk shared records at this layer, such as `SecurityListing`, `PriceBar`, and `FilingMetadata`.
- Preserve provider key, URL, retrieval time, source publication time when available, and raw response cache eligibility.
- Expose capability selection through `source_plan_by_capability()` and `select_source_for_capability()`.
- Raise explicit data-source errors for missing credentials, rate-limit messages, malformed upstream responses, and unsupported transports.
- Decode common compressed HTTP responses before JSON/CSV parsing, and surface malformed response bodies as explicit data-source errors.
- Keep raw cache and request ledger records source-linked and secret-safe.

## Invariants

- Provider clients may fetch raw data but must not decide scores, thesis state, or trading action.
- A capability with multiple sources must have a deterministic preference order and fallback list.
- A convenience vendor value cannot override SEC authority data without a later normalization rule.
- Sources that are not formal APIs, such as CSV downloads, must be labeled as such in the catalog caveat.
- No adapter may write credentials to public config, reports, memory, or logs.
- Adapter code must not wait until tomorrow for quota reset; it should return an explicit deferred state through `DataQuotaDeferred`.

## Testing

Use fake transports to verify URL construction, credential lookup, source registration, source selection, rate-limit errors, compressed response decoding, point-in-time filtering, raw cache hits, request ledger entries, quota deferrals, upstream error recording, and normalization of listing, price, and filing metadata.
