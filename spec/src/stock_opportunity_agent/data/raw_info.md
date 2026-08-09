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

The store exposes append, exact load, and filtered search. Search may filter by
company, source type, query text, and prediction time, but every result must
satisfy:

```text
available_at <= prediction_time
```

## Invariants

- The public store API has no update or delete operation.
- Reusing a `document_id` with different content or provenance fails closed.
- Re-appending a byte-identical record is idempotent.
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

## Dependencies

Uses only standard-library persistence and shared validation errors. It feeds
the Signal Library and adaptive research runtime.

## Testing

Cover hash validation, idempotent append, conflicting append rejection,
point-in-time search, future-load rejection, source filtering, and persistence
reload.
