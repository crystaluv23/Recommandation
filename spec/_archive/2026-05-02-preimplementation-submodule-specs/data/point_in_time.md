# Data / Point In Time

## Status
Not started

## Purpose

Construct point-in-time research packets for current scans and historical case learning.

## Responsibilities

- Assemble company profile, structured features, documents, sector context, theme context, and memory snippets for an `as_of_date`.
- Exclude information unavailable at that date.

## Dependencies

- Parent spec: [`../data.md`](../../../src/stock_opportunity_agent/data.md).
- Consumes structured data, documents, memory, themes, and models.

## Invariants

- Future information leakage is a blocking bug.
- Every packet must say what data was unavailable, stale, or excluded.

## Testing

Use historical fixtures with known future documents to ensure strict exclusion and packet reproducibility.
