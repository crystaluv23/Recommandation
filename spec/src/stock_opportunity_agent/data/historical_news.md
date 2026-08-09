# Data / Historical News Backfill

## Status

Started

## Purpose

Acquire bounded point-in-time company-news summaries for a label-free expanded
case scope. This is an acquisition workflow, not an experiment-specific
augmentation and not a claim that provider coverage is exhaustive.

The first provider is Alpha Vantage `NEWS_SENTIMENT`, which supports a ticker,
`time_from`, `time_to`, sort order, and a maximum result limit. The reusable
provider adapter and managed cache/quota transport remain in `data.sources`;
this module owns exact planning, durable progress, normalization, and append-only
Raw Info persistence.

## Exact Plan

The plan is derived only from `expanded-case-acquisition-scope-v1`. It records:

- the exact source artifact identity and canonical plan hash;
- one label-free item per company symbol;
- the common UTC query window, result limit, and sort order;
- the exact non-secret provider parameters; and
- stable company, symbol, and item identifiers.

The default window begins 365 calendar days before the earliest prediction date
and ends at 23:59 UTC on the latest prediction date. The first pass requests up
to 1,000 latest matching articles per company. API credentials never enter the
plan, cache key, progress record, logs, Raw Info metadata, or error messages.

One full-window request per symbol is a quota-conscious coverage pass, not proof
of completeness. A response with exactly the requested limit is marked
`provider_limit_reached`; dataset approval must treat that company as incomplete
until a later exact window-partition plan fills the gap.

## Point-in-Time and Relevance Contract

- `time_published` is parsed as the provider's UTC publication timestamp and is
  used for both `published_at` and `available_at`.
- Missing or malformed publication timestamps are excluded; retrieval time is
  never substituted.
- Articles outside the serialized plan window are excluded even if returned by
  the provider.
- A feed item must contain an exact symbol row in `ticker_sentiment`. Provider
  relevance and sentiment values are preserved as raw metadata, but no
  acquisition-time score threshold is imposed.
- Stored content is only the provider-supplied title and summary. It is marked
  `content_scope=provider_title_summary`; the workflow does not fetch, scrape,
  or imply ownership of the linked publisher article body.

Raw Info ids are derived from provider identity plus content, so exact replay is
idempotent while a corrected provider record becomes a new append-only record.
No historical outcome, split ownership, or post-cutoff result may enter the plan
or metadata.

## Persistence, Quota, and Resume

- Raw responses use `RawDataCache` and a secret-sanitized request key.
- Requests and provider errors use `RequestLedger`; the default Alpha Vantage
  budget remains 5 requests/minute and 25 requests/day.
- The caller supplies a non-negative maximum number of new network requests per
  invocation. Cache hits do not consume it.
- Progress is atomically written after every company. `Ctrl+C` may leave an
  already-cached response or already-appended documents without a completed
  item; replay consumes the cache and idempotently reuses those documents.
- Provider quota exhaustion records `next_retry_at` and returns a resumable
  pause rather than sleeping.
- Provider error payloads are detected before caching so a transient quota or
  error response cannot poison later cache replay.
- CLI execution prints secret-free per-item JSON events and a final summary.

## Non-Goals

- Treating current company profile fields as historical facts;
- fetching article bodies from arbitrary publisher URLs;
- claiming that the provider indexes every relevant article;
- silently filling saturated 1,000-result responses;
- assigning catalysts, labels, scores, or investment conclusions; and
- consuming Discovery, Evolution Validation, or Locked Test case files.

## Testing

Use fake transports to cover deterministic label-free plans, secret-free exact
cache identity, zero-network preview, request ceilings, quota pause, provider
error non-caching, cache replay, atomic progress, timestamp and query-window
filtering, exact ticker relevance, duplicate handling, saturated response
reporting, append-only Raw Info lineage, plan tampering, and progress hash
conflicts.
