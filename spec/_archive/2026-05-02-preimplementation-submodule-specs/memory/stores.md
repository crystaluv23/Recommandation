# Memory / Stores

## Status
Not started

## Purpose

Own physical local storage choices for structured memory, time-series artifacts, document indexes, and report references.

## Responsibilities

- Provide storage initialization, migrations, backups, and health checks.
- Keep local-first defaults simple and auditable.

## Dependencies

- Parent spec: [`../memory.md`](../../../src/stock_opportunity_agent/memory.md).
- Uses config for paths and models for schemas.

## Invariants

- Memory stores must not silently delete or rewrite historical decisions.
- Schema changes require migration records.

## Testing

Cover initialization, migration idempotency, read/write permissions, and backup paths.
