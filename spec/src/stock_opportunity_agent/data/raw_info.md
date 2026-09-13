# Data / Raw Info Store

## Status

Started

## Purpose

Own the append-only fact layer used by Signal execution. A Raw Info document is
source content plus point-in-time provenance; it is not a packet summary, a
Signal result, a prediction, or an outcome label.

## Record

`RawInfoDocument` stores:

- `document_id` and `company_id`;
- `source_type`;
- `published_at` and `available_at`;
- complete or explicitly scoped `content`;
- SHA-256 `content_hash`; and
- source-specific metadata that must not contain hidden outcome labels in an
  evolution-validation workspace.

The store exposes append, exact load, filtered search, an immutable in-memory
snapshot, and explicit `refresh()` for file-backed instances. A file-backed
instance is a snapshot until refreshed; refresh adds newly committed documents
and fails closed if disk state conflicts with a document already observed.
Refresh may reuse an already parsed canonical file only while its device, inode,
size, nanosecond modification time and nanosecond change time are unchanged.
New or changed files are read and fully validated; a file changing during that
read fails closed. This cache is local to one store instance and never substitutes
for the append lock or cross-path document-id conflict checks. It prevents each
single-document append from reparsing the complete historical oracle.
Search may filter by
company, source type, publication lookback, and prediction time, but every result must
satisfy:

```text
available_at <= prediction_time
```

## Invariants

- The public store API has no update or delete operation.
- File-backed append writes must become visible atomically; process interruption
  cannot leave a partial JSON document at its canonical path.
- Reusing a `document_id` with different content or provenance fails closed.
- Re-appending a byte-identical record is idempotent.
- Concurrent append is serialized by an oracle-root lock independent of any
  evolution workspace lock. If another writer wins, the loser reads back and
  compares the complete canonical record: an exact record is an idempotent
  replay and any field difference is rejected. `document_id` is unique across
  every source/company path under the oracle root.
- `available_at` cannot precede `published_at`.
- A future document cannot be loaded through an as-of read.
- Paths are derived only from validated identifiers; caller-controlled path
  traversal is rejected.
- Metadata is recursively rejected when keys encode labels or post-outcome
  facts such as `ground_truth`, `is_surge`, `realized_max_multiple`,
  `future_price`, or `future_return`. Source text may discuss forward-looking
  expectations; the guard targets hidden machine metadata, not ordinary prose.
- The Information Plan Basic Info policy is subject to the same forbidden-field
  boundary and cannot request label or outcome columns.
- Raw Info is a global oracle, not Plan or cycle state. Appending a document
  must not advance `state.json`, `cycle_state.json`, Plan embeddings, Top-K
  selection, or fitness.
- Provider responses retain the complete response body (text or canonical raw
  JSON). Derived Signal values never enter this store.

## Dependencies

Uses only standard-library persistence and shared validation errors. It feeds
the Signal Library and adaptive research runtime.

## Testing

Cover hash validation, idempotent append, conflicting append rejection,
point-in-time/lookback search, future-load rejection, source filtering, and
persistence reload.
