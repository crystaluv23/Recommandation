# Scanner / Universe

## Status
Not started

## Purpose

Define the investable and researchable universe for scans.

## Responsibilities

- Apply listing, security type, liquidity, price, market cap, and exclusion rules.
- Preserve the reason a ticker is included or excluded.

## Dependencies

- Parent spec: [`../scanner.md`](../../../src/stock_opportunity_agent/scanner.md).
- Consumes config and data.

## Invariants

- Universe thresholds materially affect scope and should be confirmed before first implementation.
- Exclusions must be audit-friendly.

## Testing

Cover defaults, overrides, exclusions, stale listings, and inclusion reasons.
