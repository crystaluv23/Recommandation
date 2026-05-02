# Scoring / Theme Scores

## Status
Not started

## Purpose

Compute Theme Transmission Score and Segment Timing Score.

## Responsibilities

- Combine demand source strength, supply bottleneck, text resonance, financial validation, analyst revisions, market confirmation, crowdedness, and valuation exhaustion.

## Dependencies

- Parent spec: [`../scoring.md`](../../../src/stock_opportunity_agent/scoring.md).
- Consumes themes and segment scoring outputs.

## Invariants

- Theme and segment score components must be auditable.
- Scoring thresholds require user confirmation before first implementation.

## Testing

Cover segment fixtures, score bounds, crowdedness penalties, and missing evidence.
