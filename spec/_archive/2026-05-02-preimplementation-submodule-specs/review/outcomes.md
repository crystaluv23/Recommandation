# Review / Outcomes

## Status
Not started

## Purpose

Measure realized outcomes after recommendations.

## Responsibilities

- Compute 1-month, 3-month, and 6-month returns, benchmark-relative returns, drawdowns, and path behavior.

## Dependencies

- Parent spec: [`../review.md`](../../../src/stock_opportunity_agent/review.md).
- Consumes data and decision memory.

## Invariants

- Outcome windows must reference original decision dates.
- Price outcome does not automatically prove or disprove thesis quality.

## Testing

Cover return windows, benchmark comparison, missing prices, and corporate-action fixtures when available.
