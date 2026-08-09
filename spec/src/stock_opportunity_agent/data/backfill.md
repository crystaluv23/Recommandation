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
backfill may use the exact acceptance timestamp, but it must never weaken this
boundary by substituting current retrieval time or same-day midnight.

## Persistence and Resume

- Raw HTTP responses use `RawDataCache` and `RequestLedger`.
- A caller supplies a non-negative maximum number of new network requests for
  each invocation. Cache hits do not consume that invocation limit.
- Progress is written atomically after every completed item.
- An interrupted response already present in the raw cache is reused on
  restart; an appended Raw Info record is idempotent by content-derived id.
- Failed or quota-deferred items remain pending and are eligible for a later
  bounded retry. They are never silently marked complete.
- Reusing a progress file with a different plan hash fails closed.

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
resume, transient failure retry, and conflicting progress rejection.
