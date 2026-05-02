# Memory / Repositories

## Status
Not started

## Purpose

Provide repository interfaces for company, thesis, signal, case, decision, review, theme, segment, experiment, and preference memory.

## Responsibilities

- Hide storage mechanics from research and scoring modules.
- Provide append-friendly writes and query methods.

## Dependencies

- Parent spec: [`../memory.md`](../memory.md).
- Consumes [`stores.md`](stores.md) and shared models.

## Invariants

- A decision record is immutable after creation.
- Updates to thesis or review status create traceable changes.

## Testing

Use temporary stores to test CRUD, archival, idempotent writes, queries, and immutable records.
