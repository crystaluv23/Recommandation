# Models / Validation

## Status
Not started

## Purpose

Validate model records without coupling them to storage, data vendors, or LLM providers.

## Responsibilities

- Check score ranges, required evidence, date ordering, version stamps, and missing-data markers.
- Provide reusable validation errors for callers.

## Dependencies

- Parent spec: [`../models.md`](../models.md).
- Consumes records and enums from this package.

## Invariants

- Invalid records should fail before they reach memory or reports.
- Validation must not fetch external data.

## Testing

Cover valid records, missing required fields, invalid dates, score bounds, and ambiguous evidence claims.
