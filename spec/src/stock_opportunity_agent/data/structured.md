# Data / Structured

## Status
Not started

## Purpose

Normalize structured price, volume, financial, valuation, revision, event, and market-context data into repeatable feature records.

## Responsibilities

- Build structured features used by scanner, scoring, review, and reports.
- Preserve feature windows and as-of availability.

## Dependencies

- Parent spec: [`../data.md`](../data.md).
- Consumes [`sources.md`](sources.md).

## Invariants

- Missing data must be explicit.
- Feature calculations must not inspect future observations for historical packets.

## Testing

Use fixture time series and financial rows to verify windows, restatements, stale data, and missing values.
