# Data / Evidence Resolution

## Status

Implemented

## Purpose

Provide one local-first point-in-time boundary between an analyst-style
information need and the global Raw Info oracle. Information Plans and Signals
share acquisition, authorization, quota, lineage, and DataGap behavior; they
differ only in how resolved documents are consumed.

## Records

- `RawInfoRequest`: immutable request id, purpose description, source types,
  optional lookback and literal query, and a maximum document count.
- `RawInfoResolution`: request, resolved document refs, optional exact context
  spans, query/acquisition events, newly appended refs, and an optional gap.
- `BasicInfoBundle`: ordered Basic Info resolutions sent to `H_init`.
- `DataGap`: request-scoped structured failure with reason, source/provider
  context, and a non-secret message.
- `AcquisitionAdapter`: provider boundary returning complete Raw Info documents.
- `EvidenceResolver`: local search, bounded acquisition, append, immediate
  re-query, deterministic selection, and audit events.

Supported DataGap reasons are `adapter_missing`, `missing_identifier`,
`external_not_authorized`, `historical_data_unavailable`, `quota_deferred`,
`provider_no_data`, `provider_error`, `materialization_failed`, and
`no_matching_documents`.

## Resolution Flow

```text
RawInfoRequest
-> point-in-time local RawInfoStore query
-> local hit: reuse
-> miss: choose an authorized adapter within request ceilings
-> append complete returned RawInfoDocument records
-> immediately repeat the same local query
-> resolved documents or DataGap
```

Unknown source types remain valid Information Plan content and yield
`adapter_missing`; they do not reject a candidate. Source-data authorization is
separate from LLM authorization. Provider cache/ledger/quota behavior remains
owned by data-source transports and is surfaced as resolution events/gaps.

Adapter declarations must include the canonical source types used by the
stable Signal Library, not only provider-facing aliases. In particular,
`financials` must route to the point-in-time SEC Company Facts adapter and
`market_data` must route to a historical daily-price adapter. Materialized
market-data documents must retain the chronological adjusted-close series in
`metadata.prices`, because deterministic market Signals consume that exact
field. When several authorized price adapters are available, runtime ordering
follows the source catalog: Massive first, Stooq second, and Alpha Vantage last;
news continues to use Alpha Vantage.

Adapter routing may deterministically recover the SEC identifier from a
canonical `company_id` shaped as `cik_##########` when the label-free case
identity does not repeat a separate `cik` field. This recovered value is passed
only to acquisition adapters; it is not added to Basic Info or model context.
An explicit `cik`/`CIK` identity remains authoritative for other company-id
schemes.

## Exact Basic Info Context

For Basic Info only, selected documents are split into 2,000-character spans
with 200-character overlap. Query ranking uses literal case-insensitive token
hit count, then public availability, then document id. Without a query,
documents rank by public availability descending. A request selects at most ten
documents; a Plan has at most eight requests; one case has a 48,000-character
span budget. An over-budget span is omitted in full, never truncated.

Every span stores document id/hash/availability, start/end offsets, and exact
text. `exact_text` must equal `RawInfoDocument.content[start:end]`. No Basic
Info summary, rewrite, or inferred structured conclusion is generated.

## Point-in-time Safety

`as_of` comes only from the case and cannot be supplied by a Plan. Local and
external results must have `available_at <= as_of`. Current profile endpoints
without historical availability guarantees are not eligible for historical
cases and yield `historical_data_unavailable`.

## Testing

Cover deterministic spans/budgets/ranking, exact-substring validation,
local-hit no-acquisition, same-execution append/re-query, later reuse, every
DataGap class, historical fail-closed behavior, canonical Signal source-type
routing, canonical company-id CIK routing, materialized price metadata, and
Signal document lineage.
