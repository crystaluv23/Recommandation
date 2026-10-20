# Data / Historical Backfill

## Status

Started

## Purpose

Repair incomplete point-in-time source coverage without mutating an existing
Raw Info document or allowing an experiment agent to change provider code. The
first supported job upgrades legacy SEC filing excerpts to complete primary
document bodies through a bounded, resumable, source-linked workflow.

This module owns acquisition orchestration only. SEC URL construction and HTTP
behavior remain in `data.sources`; immutable storage remains in `data.raw_info`.

## Workflow

```text
historical cases + legacy document artifact
-> local coverage audit
-> exact label-free SEC request plan
-> human-readable zero-network preview
-> bounded cached provider execution
-> append complete bodies as new Raw Info documents
-> durable per-item progress and coverage report
```

The plan contains source-artifact hashes, exact SEC archive URLs, stable item
ids, symbols/company ids, filing forms, public dates, legacy content lengths,
and a canonical plan hash. It contains no historical outcome label, future
return, or Locked Test ownership.

For an expanded case proposal, acquisition begins from the separate label-free
`acquisition_scope.json`, not from selected/split case artifacts. The first
discovery stage writes an exact SEC submissions plan containing one
`https://data.sec.gov/submissions/CIK##########.json` request per available CIK,
plus an explicit list of companies whose CIK is missing. Its executor stores
raw JSON only in the managed cache and records durable per-CIK progress. It does
not yet fetch primary documents or write Raw Info.

After submissions metadata is cached, deterministic stages derive:

1. exact referenced historical submissions-file requests needed to cover the
   requested as-of dates; and
2. exact filing primary-document requests, filtered by form and SEC acceptance
   time before each case cutoff.

The two-stage plan prevents an open-ended crawl and avoids constructing document
URLs before SEC metadata identifies the accession and primary document.

Historical submissions-file selection uses only SEC's `filings.files` entries.
The referenced filename must be a safe basename under
`https://data.sec.gov/submissions/`; its declared `filingFrom`/`filingTo` range
must overlap the exact metadata window. The default metadata window begins 550
calendar days before the earliest requested as-of and ends at the latest
requested as-of. Every primary CIK response must exist in raw cache before the
historical-file plan is written, and every planned historical response must be
cached before the filing-body plan is written.

The filing-body planner combines `filings.recent` arrays with selected historical
arrays, deduplicates by CIK/accession, and applies these bounded defaults at each
as-of:

- latest two annual forms (`10-K`, `20-F`, `40-F`);
- latest four quarterly forms (`10-Q`); and
- latest eight event forms (`8-K`, `6-K`) accepted in the preceding 120 days.

The union across all as-of dates becomes the exact primary-document plan. Forms,
lookbacks, and per-as-of limits are serialized into the plan and changing them
produces a new hash.

## SEC Company Facts

The label-free expanded acquisition scope may also produce one exact
`data.sec.gov/api/xbrl/companyfacts/CIK##########.json` request per CIK. This is
an independent financial-statements stage: completing submissions metadata does
not imply Company Facts coverage, and completing Company Facts does not imply
filing-body, news, profile-taxonomy, or transcript coverage.

The plan freezes the requested prediction dates, a period-end lookback, standard
taxonomy allow-list, filing-form allow-list, source artifact hash, and canonical
plan hash. The default lookback is 1,100 days before the earliest prediction
date. It accepts the standard namespaces returned by the SEC Company Facts API
(`dei`, `ifrs-full`, `srt`, and `us-gaap`) rather than silently limiting foreign
issuers to US-GAAP concepts.

Raw responses remain in the managed source cache. The materializer groups
selected fact rows by filing accession and appends one immutable
`source_type=sec_company_facts` Raw Info document per accession/capture version
for newly written v2 plans; historical v1 plans retain accession/content IDs.
Each document contains the complete selected standard-taxonomy fact rows for
that accession; it does not copy the response's current entity name into
historical content. Rows must have:

- a well-formed SEC accession number (its prefix is not assumed to equal the
  registrant CIK);
- an allowed filing form and standard taxonomy;
- a parseable filing date and period end within the frozen plan window; and
- an availability boundary no later than the latest prediction cutoff.

Company Facts rows expose a filing date but not a timezone-aware acceptance
timestamp. Therefore `published_at` is filing-date midnight UTC and
`available_at` is the next UTC midnight. Same-day facts are unavailable to a
historical case represented at midnight. Metadata records retrieval time,
taxonomy/tag/unit/accession lineage, selection window, and that the retrospective
API extraction remains auditable against the primary filing.

The pure `data.sec_company_facts` normalizer and date-only availability helper
are also used by live acquisition. Backfill's existing private wrapper preserves
the frozen v1 selection, `backfill_plan_hash`, IDs and complete records.
New plans use `sec-company-facts-backfill-plan-v2` and bind
`identity_policy=raw-info-capture-v1`; loaders/runners still accept v1 explicitly
as `legacy_content_v1`. The plan hash binds that choice, and resume cannot switch
identity policy. The shared wrapper defaults to legacy for historical direct
callers; a v2 runner passes capture explicitly. Both use the recorded managed
cache retrieval instant, not a fresh normalization clock on cache replay. It does
not import acquisition or research orchestration. Extraction validates response
CIK itself, including direct calls outside the backfill runner.

## Point-in-Time Contract

Legacy filing artifacts currently preserve only a public date, not a precise
SEC acceptance timestamp. A historical case is represented at `00:00 UTC`, so
using a same-calendar-day filing at midnight would create look-ahead. Until an
acceptance timestamp is available from SEC submissions, upgraded legacy bodies
use the conservative availability boundary:

```text
available_at = 00:00 UTC on the day after legacy available_date
```

`published_at` remains the original filing date. A later submissions-based
backfill uses an SEC `acceptanceDateTime` only when it includes an explicit time
zone. A missing or timezone-naive acceptance value falls back to next-day UTC;
it must never be interpreted as same-day midnight or replaced with retrieval
time. Each plan records the raw acceptance value, derived availability time,
policy, and the as-of dates for which the filing was selected.

## Persistence and Resume

- Raw HTTP responses use `RawDataCache` and `RequestLedger`.
- A caller supplies a non-negative maximum number of new network requests for
  each invocation. Cache hits do not consume that invocation limit.
- Progress is written atomically after every completed item.
- An interrupted response already present in the raw cache is reused on
  restart; an appended Raw Info record is idempotent by its recorded identity
  recipe (capture-version ID for new Company Facts v2 plans).
- Failed or quota-deferred items remain pending and are eligible for a later
  bounded retry. They are never silently marked complete.
- Reusing a progress file with a different plan hash fails closed.
- Positive CLI execution emits one secret-free JSON progress event when an item
  starts and when it completes, fails, defers, or reaches the invocation limit;
  the final JSON summary remains machine-readable.
- SEC submissions discovery uses the same cache/ledger/quota primitives and
  invocation request ceiling as filing-body execution. A completed CIK means
  its exact JSON response is durable in raw cache; it does not mean document
  coverage is complete.
- SEC Company Facts uses `financial_statements` cache/ledger capability keys,
  independently durable per-CIK progress, cache-first resume, and append-only
  fact materialization. A cached response may be materialized with zero new
  network requests through the executor API; the CLI's zero-request mode remains
  a read-only preview.

## SEC Filing Upgrade

Only `https://www.sec.gov/Archives/edgar/data/...` primary-document URLs are
allowed. Each successful body becomes a new append-only `RawInfoDocument` with:

- `source_type=filing`;
- complete source content and derived content hash;
- original source/document lineage;
- filing form, public dates, source URL, retrieval time, and
  `content_scope=complete_body`; and
- a content-derived id distinct from the legacy excerpt record.

Existing excerpts remain available for audit. The backfill does not delete or
replace them.

## Non-Goals

- Automatically editing or installing data-provider code from inside the
  evolution loop;
- inferring missing source facts with an LLM;
- opening Locked Test or reading historical outcomes;
- crawling arbitrary web pages or following SEC links beyond the exact plan;
- silently sleeping through quota resets; and
- treating a fetched source body as evidence that extraction or prediction
  quality improved.

## Testing

Cover coverage counts, deterministic plan hashing, SEC URL allow-listing,
label-free plan content, conservative availability, zero-network preview,
network-call ceilings, cache reuse, append-only Raw Info lineage, progress
resume, transient failure retry, and conflicting progress rejection. Expanded
scope tests additionally prove outcome/split fields are absent, exact CIK
submissions URLs are planned, missing CIKs stay explicit, cached discovery
resumes with zero network calls, and metadata completion is not misreported as
filing-body completion. Historical-stage tests cover safe referenced filenames,
date-range overlap, incomplete-parent rejection, cache-only plan derivation,
primary/historical array merging, accession deduplication, timezone-aware versus
conservative availability, bounded per-family selection, and exact body-plan
replay.
Company Facts tests cover exact per-CIK URLs, canonical plan tamper rejection,
standard-taxonomy/form/date filtering, foreign-taxonomy retention, CIK/accession
guards, next-day availability, current-name exclusion, cache-only recovery,
content-versioned append-only ids, and zero-network preview.
