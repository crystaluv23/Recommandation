# Cases / Analysis

## Status
Not started

## Purpose

Run blind case analysis and compare winner, control, and failure patterns.

## Responsibilities

- Request structured blind research outputs.
- Compare observable pre-launch differences.
- Promote stable lessons into candidate signals, not directly into production weights.

## Dependencies

- Parent spec: [`../cases.md`](../../../src/stock_opportunity_agent/cases.md).
- Consumes research, signals, memory, and review.

## Invariants

- The analyzer must not know winner/control labels during blind scoring.
- Lessons require controls or failure comparison before promotion.

## Testing

Use fake blind outputs to verify comparison, lesson extraction, and signal-candidate records.
