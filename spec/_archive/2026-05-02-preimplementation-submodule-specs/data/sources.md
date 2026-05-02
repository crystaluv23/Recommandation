# Data / Sources

## Status
Not started

## Purpose

Define adapters for external and local data sources without leaking vendor details into research modules.

## Responsibilities

- Normalize provider-specific symbols, timestamps, source metadata, and error states.
- Separate raw retrieval from feature construction.

## Dependencies

- Parent spec: [`../data.md`](../../../src/stock_opportunity_agent/data.md).
- Uses config for provider settings and models for source metadata.

## Invariants

- A source adapter must report availability time, retrieval time, and missing-data reasons.
- Vendor-specific objects must not cross module boundaries.

## Testing

Use fake source adapters to test errors, stale data, symbol mapping, and metadata preservation.
