# Scoring / Rocket

## Status
Not started

## Purpose

Compute company-level Rocket Score components.

## Responsibilities

- Combine fundamental inflection, revisions, narrative migration, catalysts, industry tailwind, market confirmation, valuation room, and risk.
- Preserve upside potential and launch probability as separate fields.

## Dependencies

- Parent spec: [`../scoring.md`](../../../src/stock_opportunity_agent/scoring.md).
- Consumes signal observations, research outputs, data, and config.

## Invariants

- Weights materially affect output and must be confirmed before first implementation.
- Component scores must remain visible.

## Testing

Cover component bounds, weight changes, narrative-only downgrades, and missing signal handling.
