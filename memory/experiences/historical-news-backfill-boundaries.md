# Historical News Backfill Boundaries

visit_times: 1

## Trigger

Read this before acquiring historical provider news for a case library, changing
the news query window/limit, or interpreting news coverage as complete.

## Lesson

Keep historical news acquisition label-free and separate from experiment
scripts. Query a serialized point-in-time window, persist the provider response
before normalization, and use the article publication timestamp rather than
retrieval time. Store only content the provider actually returned; a
title/summary API response is not a fetched publisher article body.

A provider maximum is an audit boundary. Alpha Vantage returns at most 1,000
matching articles per call and exposes no ordinary offset, so a limit-sized
response must be marked saturated and followed by a separate exact
window-partition plan. It must not be called complete.

## Context

The 2026-08-09 v4 expanded acquisition scope contains 240 issuers across five
dates. Its first Alpha Vantage news plan uses one 365-day-lookback through latest
as-of window per symbol: 240 exact calls, zero initial cache hits, and the
managed free-tier boundary of 5 calls/minute and 25 calls/day. The plan is a
coverage pass; saturated symbols remain approval blockers.

The generic executor requires an exact ticker row in provider
`ticker_sentiment`, preserves UTC `time_published`, rejects out-of-window rows,
deduplicates provider identities, writes append-only Raw Info, detects provider
errors before caching, and resumes after each company.

## How to Apply

1. Derive requests only from the label/split-free acquisition scope.
2. Serialize start, end, sort, and limit into an exact secret-free plan.
3. Use managed cache, request ledger, quota deferral, and an invocation request
   ceiling; never sleep across quota resets.
4. Require exact symbol relevance but keep provider relevance/sentiment as raw
   metadata rather than an acquisition threshold.
5. Set `published_at=available_at` only from a valid provider publication time;
   exclude rows whose time cannot be proven.
6. Mark limit-sized responses saturated and plan narrower windows later.
7. Re-audit actual Raw Info coverage before approving a dataset or claiming an
   information-plan improvement.

## Limits

Alpha Vantage indexing is not guaranteed to cover every material article, and
provider summaries may omit decisive details. This workflow does not replace
SEC filings, transcripts, publisher bodies acquired under appropriate terms, or
historical company-identity validation.
