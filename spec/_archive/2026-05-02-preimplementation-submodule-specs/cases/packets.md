# Cases / Packets

## Status
Not started

## Purpose

Build case-specific point-in-time packets at historical time slices.

## Responsibilities

- Generate T-180, T-120, T-90, T-60, T-30, and T-0 packets when configured.
- Hide future outcome labels from blind analysis.

## Dependencies

- Parent spec: [`../cases.md`](../../../src/stock_opportunity_agent/cases.md).
- Consumes data point-in-time packet builder.

## Invariants

- Future information leakage is a blocking bug.
- Packet slices must be reproducible from stored inputs.

## Testing

Cover slice construction, hidden labels, unavailable documents, and packet checksums.
