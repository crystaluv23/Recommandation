# Data / Evidence Resolution

An explicitly reviewed snapshot remains the resolver's sole store, including
requery and exact `load_documents`. Its read-only admission boundary forbids an
enabled acquisition policy even when no external execution flag was supplied;
invalid source input is a typed technical failure, not negative company evidence.
See [reviewed source snapshots](reviewed_snapshot.md).

SEC Company Facts acquisition now emits the existing typed per-accession
`sec_company_facts` products through the shared pure normalizer. The existing
source compatibility family serves `financials` requests without relabeling
filing prose. It validates issuer CIK, excludes date-only facts until next UTC
midnight, retains all supported historical comparison periods and separately
archives the complete raw response. Old aggregate records are not rewritten or
implicitly source-qualified; a corrected product uses the distinct existing
accession/content ID for legacy recipes; new explicitly versioned acquisition
uses a complete-record capture ID. Request lookback remains a publication filter, not an
additional fact-history limit.

## Status

Implemented

## Purpose

Provide one local-first point-in-time boundary between an analyst-style
information need and the global Raw Info oracle. Information Plans and Signals
share acquisition, authorization, quota, lineage, and DataGap behavior; they
differ only in how resolved documents are consumed.

## Records

- `RawInfoRequest`: immutable request id, purpose description, source types,
  optional lookback and literal query, a maximum document count, and optional
  structured completeness requirements: AND-of-OR required source groups,
  minimum distinct source periods, minimum period span, and minimum observation
  count.
- `RawInfoResolution`: request, resolved document refs, optional exact context
  spans, query/acquisition events, newly appended refs, an optional gap, and
  a coverage record that separates eligible/retrieved counts, lexical query
  matches, selection truncation, model-visible context truncation, and whether
  the structured completeness requirements were met. Incomplete coverage reports
  the exact missing requirement instead of treating retrieved partial evidence as
  proof that the request was answered.
  Coverage also distinguishes a query that was not requested from a legacy
  query whose match evaluation was never recorded; neither state is reported
  as a successful match. Resolutions that select context also carry bounded
  readable `omitted_context_markers` previewing ranked-but-unfunded spans.
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
`no_matching_documents`. A non-empty local result that does not satisfy the
request contract uses `required_coverage_incomplete`. A zero-document local
hit for source types no acquisition adapter supports is an empty
point-in-time corpus, not a configuration failure: it reports
`no_matching_documents` so an existential Signal read abstains honestly
(no documents is never a technical error), while `adapter_missing` stays
reserved for requests whose declared contract local documents cannot
satisfy and no route can fetch.

## Resolution Flow

```text
RawInfoRequest
-> point-in-time local RawInfoStore query
-> complete local hit: reuse
-> empty or contract-incomplete hit: enumerate authorized adapters in deterministic catalog order
-> call one adapter within request ceilings
-> append complete returned RawInfoDocument records
-> immediately repeat the same local query
-> still unresolved: try the next authorized adapter
-> complete resolved documents, or partial document refs plus DataGap
```

Capture-version IDs preserve separate source/acquisition provenance in the
oracle and reviewed view. The existing identical-content deduplication below
still runs before request limits, so multiple captures do not become independent
facts, extra source coverage or duplicate measurement inputs. Duplicate IDs stay
auditable; no newest-capture preference or sorting change is introduced. Exact
historical references continue resolving their original IDs, never a replacement.

Before any request limit is applied, the resolver filters the complete PIT
eligible pool and removes byte-identical copies within the same canonical source
family. It ranks the resulting pool by query relevance and then availability;
an older relevant document therefore cannot be displaced by newer irrelevant
documents merely because the selected prefix is bounded. A lexical query match
is reported as retrieval coverage, not as a claim that the request is
semantically answerable.

When required source groups are declared, default selection first keeps the
highest-ranked member of every group and then fills the remaining capacity in
rank order. Completeness is evaluated over the selected immutable documents.
Period dates and observations are extracted only from known structured fields;
publication and availability timestamps never masquerade as research periods.
If local evidence is partial, authorized acquisition continues within the same
frozen budget. Exhaustion returns an unresolved resolution that retains the
partial document refs and explicit coverage diagnostics. Basic Info may expose
literal spans from those partial documents together with the unresolved status;
Signal execution records their fingerprint but does not execute until the
contract is complete.

Deterministic financial callers may use that existing callback to preserve the
actual callable's readable latest/comparable operands before the bounded prefix.
The callable, not the generic resolver, owns tag/period/currency semantics.
PIT/source/lookback filtering and content deduplication still precede selection;
unchanged member and document-limit validation still follows it. A caller that
cannot preserve its full-pool measurement basis within the limit returns an
empty subset, permitting the same authorized-acquisition/unresolved path. This
does not change generic query ranking, add semantic readiness to lexical
coverage, or authorize data acquisition.

`resolve` optionally accepts a pure local `select_documents` callback. It receives
the deterministic ranked pool only after issuer, exact source type, lookback, and
availability filtering, plus the original request. It must return at most the
request's document limit, using unique unchanged members of that pool. Invalid
selection is a local contract error, never a provider error or an acquisition
retry. Before invoking the callback, snapshot each eligible ID and its complete
record using the existing typed canonical JSON hash policy. Give the callback
an isolated deep copy of the candidates, including nested metadata, so selected
or unselected mutation cannot alter backing-store objects. Compare returned
records against the pre-callback snapshots, not live post-callback objects:
JSON true/1 and 1/1.0 are distinct. Unchanged clones are legal; changed IDs,
content or provenance are not. After validation, remap selected IDs to the original
eligible objects, so callback-held aliases cannot mutate subsequent consumers.
This does not impose capture-only metadata/schema rules on legacy documents.
Contract failures retain `_DocumentSelectionError`, never domain unavailability.
The callback must perform no I/O. Without it, existing ranked-prefix selection
is unchanged.

An empty selected pool is an unresolved need. The same selection runs after each
authorized acquisition, so a consumer can require a particular usable input when
that requirement is truly mandatory. Every provider call retains the existing
budget, ordering, append-only, and point-in-time guarantees. Failed acquisition
reuse also binds the literal query; failure for one topic cannot suppress another.
The resolver owns acquisition only; consumer-specific semantic evidence checks
remain in the consumer and never import research into the data package.

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

Specific SEC form names are not interchangeable aliases. A request that names
`10-Q`, `10-K`, `8-K`, `20-F`, `40-F`, or `6-K` may match that exact materialized form, or a generic
`filing`/`sec_filing`/`filing_body` document whose form metadata proves the same
form; it must not be satisfied by a different SEC form merely because both are
members of the filing acquisition family. Generic `filing` requests may still
use the ordinary filing-family route and prefer periodic/current operating
reports across domestic and foreign issuers.

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
The same side-effect-free boundary exposes a stable non-secret unavailability
reason. It distinguishes missing routes, disabled/unauthorized policy, audited
historical unavailability, and known provider-configuration gaps such as
`sec_user_agent_unconfigured`; it never returns a credential or configured
value. Multiple heterogeneous unavailable adapters collapse to
`provider_unavailable` rather than leaking implementation detail.

Adapter declarations must include the canonical source types used by the
stable Signal Library, not only provider-facing aliases. In particular,
`financials` must route to the point-in-time SEC Company Facts adapter and
`market_data` must route to a historical daily-price adapter. Materialized
market-data documents must retain the chronological adjusted-close series in
`metadata.prices`, because deterministic market Signals consume that exact
field. Daily-price acquisition derives its request day from the aware cutoff
converted to UTC: start is UTC day minus lookback, and end is UTC day minus
one. Equivalent aware instants select the same dates; no other adapter or
fiscal-period date contract changes. When several authorized price adapters are available, runtime ordering
follows the source catalog: Massive first, Stooq second, and Alpha Vantage last;
news continues to use Alpha Vantage. A provider error, empty response, or
point-in-time result that still does not satisfy the request advances to the
next authorized adapter while budget remains. A final DataGap records the
failed provider attempts; one provider's miss must not suppress a later
authorized fallback.

Within one resolver lifetime, compatible requests for the same provider,
semantic route, company, cutoff, lookback, and document limit may reuse a
bounded acquisition failure together with its retryability and optional reset
time. A quota failure is reused before its known reset; an unknown reset remains
pending until explicit resolver recovery. Once a known reset has passed, the
same request may try again inside the unchanged frozen acquisition budget.
Unknown provider errors are not memoized as permanent semantic failures. The
later Signal records an `acquisition_failure_reused` event without spending a
provider request; different cases, cutoffs, routes, or request bounds remain
independent. Quota classification uses the typed `DataQuotaDeferred` boundary,
not an exception class-name string.

A generic SEC `filing` request prefers decision-relevant `10-K`, `10-Q`, `8-K`,
`20-F`, `40-F`, and `6-K` bodies over ownership, conflict-minerals, and other administrative forms.
The filing adapter keeps trying later eligible core filings until it has
materialized the requested count, under a fixed three-object fallback margin;
one inaccessible archive object cannot mask the rest of the bounded filing
set. If every attempted eligible body fails, the request remains a provider
error rather than being represented as an empty filing document.
The adapter also follows at most three overlapping, manifest-declared SEC
submissions history files. If relevant pages remain unscanned or fail and no
required body is obtained, the request is `required_coverage_incomplete`, not a
claim that historical data does not exist; successful bodies retain the same
scan-incomplete audit diagnostic.

Historical transcript availability follows the user-approved public-content
policy (2026-10-19). Earnings `reportedDate` and provider quarter echoes are
retrieval clues, never proof of full conference-content availability or of the
issuer's true fiscal period. Require reviewed first-party evidence identifying
the issuer, fiscal period and complete publicly accessible content. A verified
full replay/transcript publication instant may supply the exact time. If only
the actual conference date is established, require evidence that the conference
ended and that its complete content was public before the next UTC midnight;
only then use that midnight conservatively. A scheduled start announcement,
provider retrieval time, case cutoff or a URL alone cannot establish this.
Unknown completion, UTC boundary, availability or fiscal mapping leaves only
that record unavailable; other verified sources remain eligible. Corrections
must use new document IDs, original hash/evidence lineage and an explicit
successor manifest exclusion of superseded records; retain all originals and
completed-run inputs. The automatic historical transcript adapter has no
reviewed public-content proof input. It must reject acquisition with the
existing `historical_data_unavailable` gap before provider calls; it must not
use the earnings calendar, provider quarter, retrieval time or cutoff as a
substitute clock. The provider raw-client/cache interface and local-first
resolution remain available, without rewriting or newly endorsing old local
documents. This closes only the unsafe automatic producer. Proof-backed
materialization, reviewed successor exclusions and a substantive transcript
capability positive control remain required before transcript support closes.

Adapter routing may deterministically recover the SEC identifier from a
canonical `company_id` shaped as `cik_##########` when the label-free case
identity does not repeat a separate `cik` field. The same routing step
enriches identity with `ticker`/`symbol` derived from local point-in-time
market documents when the case identity does not already carry them, so
third-party adapters that route by ticker work for any case regardless of
what identity the calling pipeline supplies. These recovered values are
passed only to acquisition adapters; they are not added to Basic Info or
model context. An explicit `cik`/`CIK` or `ticker`/`symbol` identity
remains authoritative for other company-id schemes.

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

For legacy provider payloads stored as complete JSON, "visible title or body"
means the provider's title and summary/body fields, not routing metadata or a
secondary `ticker_sentiment` row embedded elsewhere in the JSON. A secondary
ticker association therefore cannot turn an article about another issuer into
company evidence.

For Basic Info only, plain-text selected documents are split into 2,000-character
spans with 200-character overlap. Query ranking scores each window with a
per-token hit count capped at three occurrences, weighted by inverse document
frequency across the request's candidate windows: tokens present in most
windows (risk/business/management in filings) are down-weighted while rare
tokens are up-weighted, so lexical boilerplate cannot out-score substantive
language merely by repetition. Ranking then orders by weighted score, public
availability, then document id. Windows almost entirely covered (at least 60%
of the candidate's range) by an already-selected window of the same document
are skipped as near-duplicates; the fixed 200-character overlap stays
selectable. The earliest window (document head) of every document that
contributes any selected span is pinned deterministically ahead of that
document's remaining windows and is exempt from near-duplicate suppression,
because event-driven filings carry their substance up front. For SEC/filing markup, tag removal and whitespace normalization
happen over the complete document before query ranking and chunk boundaries
are chosen; each readable-text window is then mapped back to a raw start/end
range. The persisted `RawInfoContextSpan` remains an exact literal raw
substring; markup spans additionally carry `visible_chars`, the normalized
window length, and every visibility budget (per-request, cross-request
Basic Info, and model projection) bills `visible_chars` instead of the raw
length so HTML padding cannot consume readable-content budget. Model
projection also decodes single-character HTML entities with raw-span lineage,
so repeated non-breaking-space and apostrophe encodings do not consume
context as opaque markup. Without a query, documents rank by public
availability descending. A request selects at most ten documents; a Plan has
at most eight requests; one case has a 48,000-character readable-span budget.
An over-budget span is omitted in full, never truncated. Every resolution
with ranked-but-unfunded spans discloses bounded readable
`omitted_context_markers` (up to six resolver-side previews, extended to
eight by projection-side previews in the Basic Info model view), so omitted
content stays discoverable instead of silently vanishing behind a resolved
status. Context allocation is request-fair rather than a sequential drain:
after every request has been resolved, the resolver retains one
highest-ranked eligible span for each resolved request, then assigns the
remaining budget in request order. Since one span bills at most 2,000
readable characters and a Plan has at most eight requests, every resolved
non-empty request can expose at least one span without raising the existing
48,000-character ceiling. This prevents an earlier long transcript from
silently starving a later financial or filing request while preserving Plan
request order and per-request ranking.

For structured market-data documents, `lookback_days` applies to the dated
observations exposed to Basic Info, not merely to the publication timestamp of
the container document. A broader locally cached price document may satisfy a
narrower request, but context selection must project it to observations inside
the requested `[UTC_day(as_of) - lookback_days, UTC_day(as_of)]` closed
window before chunking. Convert the aware instant to UTC before extracting
the day; retain this reader's inclusive upper boundary (acquisition and price
computations have their own strictly-before-day contracts). Market
chunks are grouped only at complete JSON-row boundaries and have no overlap, so
model-view metadata removal never receives a field name in one chunk and its
value in another. This projection preserves literal source offsets and never
rewrites or summarizes the selected rows. It prevents a short recent-market
request from replaying an entire long-horizon document that was previously
acquired for a momentum Signal.

Every span stores document id/hash/availability, start/end offsets, and exact
text. `exact_text` must equal `RawInfoDocument.content[start:end]`. No Basic
Info summary, rewrite, or inferred structured conclusion is generated.

Research-role views may additionally recognize the existing SEC Company Facts
JSON structure and expose concept/label/unit plus complete selected fact-record
spans. This is a presentation projection over already resolved immutable Raw
Info, not a new acquisition schema. Each citable record remains one contiguous
raw span with verified offsets; distinct filings for the same period do not
count as two comparison periods, and future-filed records are omitted.

## Capability Backlog

The ordinary backlog uses `capability-gap-report-v3`. A pure resolution-layer
extractor reads admitted source trajectories' `final_state.next_information_needs`,
normalizes only for stable hashing and exact deduplication, and retains every
original need, source ref, committed source round, source fingerprint, and actual
terminal reason. `no_signal_match`, budget exhaustion, and round/call limits stay
distinct. Formal entries come from completed-checkpoint Plan records; staged
attempts may only add separately identified technical diagnostics.

Data gaps become resolved only when a later admitted resolution for the same
request actually succeeds. Merely registering or naming a compatible source is
not evidence of resolution. Signal result execution failures are reported in a
separate technical list and never counted as domain capability observations.

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


Production news acquisition connects the existing catalog order Alpha Vantage
then Finnhub. Finnhub uses the requested issuer and historical date window;
materialization rejects invalid timestamps, out-of-window items and unrelated
symbols, retains the provider's literal article record and URL, and never treats
an empty response as negative company evidence. It uses the same managed cache,
request ledger, authorization and per-cycle acquisition ceilings. A successful
empty fallback remains provider_no_data under the existing ordered fallback
semantics; the earlier provider quota event remains in the audit.

### Shared hidden markup boundary (2026-10-01)

Readable filing windows exclude source-owned nonvisible ranges before budget and
head selection. See [markup](markup.md). Research projection and the Raw Info
library reuse this rule with exact original raw offsets; hidden XBRL taxonomy
headers cannot consume the readable body allowance. This does not infer external
CSS visibility or guarantee financial-topic coverage.

## Compiled operating orientation

The versioned operating-report action uses a fixed internal query and a pure
annual/interim ordering shared with acquisition before its body-fetch ceiling.
Default count two prefers available annual plus latest interim; count one
prefers annual background when present, else interim. Its OR completeness group
is exact 10-K/10-Q/20-F/40-F, not an annual requirement. Generic 8-K/6-K/amendment
material remains readable; it does not by form alone clear that requirement.
Exact matching uses authoritative form metadata (or exact typed source form),
not a title mention or substring. Conflicting form declarations fail exact
qualification; amendments do not silently stand in for original forms.
All ordinary generic filing requests keep their current ordering. Periodic
availability and retrieved counts do not declare business facts fully visible;
projection budgets, source gaps and omitted markers remain authoritative.
