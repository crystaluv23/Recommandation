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
  re-query, deterministic selection, audit events, and a side-effect-free
  capability check for whether a request has at least one available authorized
  acquisition adapter.

Supported DataGap reasons are `adapter_missing`, `missing_identifier`,
`external_not_authorized`, `historical_data_unavailable`, `quota_deferred`,
`provider_no_data`, `provider_error`, `materialization_failed`, and
`no_matching_documents`.

## Resolution Flow

```text
RawInfoRequest
-> point-in-time local RawInfoStore query
-> local hit: reuse
-> miss: enumerate authorized adapters in deterministic catalog order
-> call one adapter within request ceilings
-> append complete returned RawInfoDocument records
-> immediately repeat the same local query
-> still unresolved: try the next authorized adapter
-> resolved documents or DataGap
```

## Signal Input Boundary

`SignalExecutor.prepare_inputs` is the only Signal-to-Raw-Info preparation
interface. For every selected stable ref it converts the immutable
`SignalSpec.raw_retrieval` declaration into a `RawInfoRequest`, resolves that
request through this module, and returns the complete `RawInfoResolution`.
Execution consumes only the documents referenced by that resolution. Signal
functions and LLM skills never query a provider, mutate Raw Info, or invent a
replacement value.

Before Plan proposals, production evaluation calls the same interface for the
complete frozen Signal Registry. Requests are local-first and deduplicate in
practice through the append-only oracle: the first financial, filing, news, or
market request may acquire data, while later compatible Signals reuse it. At
least 80% of the frozen stable refs must resolve for each evaluation case before
that case is admitted. Falling below that threshold is a shared data-readiness
pause, not Plan fitness and not a sequence of tolerated `unavailable` results.
Individual Signals may still return `unavailable` when an authorized provider
has no point-in-time data or the retrieved document lacks the required fact.

Source-type aliases are semantic at both local lookup and authorization. For
example, an allowlist entry for `sec_company_facts` can satisfy a Signal asking
for `financials`, and `price_daily` can satisfy `market_data`, provided the
provider and capability are also explicitly authorized. Readiness never widens
an allowlist or converts a disabled policy into authorization.

The operator boundary exposes one versioned broad-research authorization
profile for new evolution workspaces. Its wildcard policy authorizes every
historical Raw Info adapter registered by the contract-bound code revision; it
does not enumerate provider, capability, or source-type names. Consequently a
future Signal cannot become unavailable merely because its semantic source
type was omitted from today's authorization list. Local Raw Info of any source
type remains readable under the normal point-in-time query. External retrieval
still requires a registered adapter that declares support for the requested
type; a missing adapter or genuine provider/history gap remains explicit.

The profile freezes wildcard allowlists plus request ceilings into the run
contract even though the operator selects it with the single
`--data-external` flag. Custom restrictive allowlists remain available when
every list and ceiling is supplied together. This convenience never authorizes
current-only facts as historical evidence, future data, outcome labels, Locked
Test, or LLM execution.

Unknown source types remain valid Information Plan content and yield
`adapter_missing`; they do not reject a candidate. Source-data authorization is
separate from LLM authorization. Provider cache/ledger/quota behavior remains
owned by data-source transports and is surfaced as resolution events/gaps.
The resolver's capability check never searches, reserves, acquires, or writes;
it reports only whether the frozen policy and current adapter availability make
external acquisition possible for the exact request. Controllers may use it to
pause before a paid upstream model call when a mandatory downstream data stage
is already known to be impossible. A positive result is capability, not a
promise that the provider has data or will respond successfully.

Adapter declarations must include the canonical source types used by the
stable Signal Library, not only provider-facing aliases. In particular,
`financials` must route to the point-in-time SEC Company Facts adapter and
`market_data` must route to a historical daily-price adapter. Materialized
market-data documents must retain the chronological adjusted-close series in
`metadata.prices`, because deterministic market Signals consume that exact
field. When several authorized price adapters are available, runtime ordering
follows the source catalog: Massive first, Stooq second, and Alpha Vantage last;
news continues to use Alpha Vantage. A provider error, empty response, or
point-in-time result that still does not satisfy the request advances to the
next authorized adapter while budget remains. A final DataGap records the
failed provider attempts; one provider's miss must not suppress a later
authorized fallback.

Within one resolver lifetime, compatible requests for the same provider,
semantic route, company, cutoff, lookback, and document limit reuse the first
bounded acquisition failure. The later Signal records an
`acquisition_failure_reused` event and does not spend another provider request;
different cases, cutoffs, routes, or request bounds remain independent.

A generic SEC `filing` request prefers decision-relevant `10-K`, `10-Q`, and
`8-K` bodies over ownership, conflict-minerals, and other administrative forms.
The filing adapter keeps trying later eligible core filings until it has
materialized the requested count, under a fixed three-object fallback margin;
one inaccessible archive object cannot mask the rest of the bounded filing
set. If every attempted eligible body fails, the request remains a provider
error rather than being represented as an empty filing document.

An Alpha Vantage transcript request pairs the historical transcript endpoint
with the provider's earnings-history metadata. The adapter derives the exact
fiscal `YYYYQn` label from quarterly and annual fiscal-period ends, selects only
quarters whose provider-reported `reportedDate` is before the case cutoff, and
uses the next UTC day as `available_at` because the endpoint supplies a date but
not an intraday publication time. The transcript response must repeat the
requested symbol and quarter and contain substantive turns. The complete
provider JSON is stored as Raw Info; a missing or ambiguous fiscal-period/date
mapping remains unavailable rather than borrowing the case date or current
retrieval time.

Adapter routing may deterministically recover the SEC identifier from a
canonical `company_id` shaped as `cik_##########` when the label-free case
identity does not repeat a separate `cik` field. This recovered value is passed
only to acquisition adapters; it is not added to Basic Info or model context.
An explicit `cik`/`CIK` identity remains authoritative for other company-id
schemes.

## Exact Basic Info Context

Company-scoped news is not trusted merely because a provider associated it with
the requested ticker or the Raw Info document is stored under that company id.
When the case supplies a company name/ticker alias inventory, a news document
must contain at least one strong visible issuer-name or boundary-matched ticker
reference in its title or body. Provider association metadata alone is
insufficient. Non-matching documents remain immutable Raw Info but are excluded
from both Basic Info and Signal resolution, and the resolution events record the
filtered document ids. This check does not apply to directly issuer-routed SEC,
market, facts, or transcript sources.

For Basic Info only, plain-text selected documents are split into 2,000-character
spans with 200-character overlap. Query ranking uses literal case-insensitive token
hit count, then public availability, then document id. For SEC/filing markup, tag
removal and whitespace normalization happen over the complete document before query
ranking and chunk boundaries are chosen; each readable-text window is then mapped
back to a raw start/end range. The persisted `RawInfoContextSpan` remains an exact
literal raw substring, while model projection receives complete removable tags rather
than fragments beginning inside an HTML/XBRL attribute. Model projection also decodes
single-character HTML entities with raw-span lineage, so repeated non-breaking-space
and apostrophe encodings do not consume context as opaque markup. Without a query, documents
rank by public availability descending. A request selects at most ten documents; a
Plan has at most eight requests; one case has a 48,000-character raw-span budget. An
over-budget span is omitted in full, never truncated.

For structured market-data documents, `lookback_days` applies to the dated
observations exposed to Basic Info, not merely to the publication timestamp of
the container document. A broader locally cached price document may satisfy a
narrower request, but context selection must project it to observations inside
the requested `[as_of - lookback_days, as_of]` window before chunking. Market
chunks are grouped only at complete JSON-row boundaries and have no overlap, so
model-view metadata removal never receives a field name in one chunk and its
value in another. This projection preserves literal source offsets and never
rewrites or summarizes the selected rows. It prevents a short recent-market
request from replaying an entire long-horizon document that was previously
acquired for a momentum Signal.

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
strong visible-issuer filtering for provider ticker news, structured
market-observation window projection and row-boundary chunking, local-hit no-acquisition,
same-execution append/re-query, later reuse, every DataGap class, historical
fail-closed behavior, canonical Signal source-type routing, canonical
company-id CIK routing, materialized price metadata, and Signal document
lineage. Also cover fiscal-quarter transcript mapping, provider-reported
availability filtering, ordered multi-provider fallback, fallback budget
accounting, and final aggregate failure after every authorized adapter has been
attempted.
