# Ranking / Changes

## Status
Not started

## Purpose

Explain additions, removals, upgrades, downgrades, and rank changes versus prior runs.

## Responsibilities

- Compare current rankings with decision memory.
- Attribute changes to score, evidence, catalyst, theme, valuation, risk, or data freshness.

## Dependencies

- Parent spec: [`../ranking.md`](../ranking.md).
- Consumes memory and current ranking output.

## Invariants

- Existing watchlist names should not vanish without an explanation.
- Data gaps must be distinguished from real downgrades.

## Testing

Cover new names, removed names, stale data, score shifts, and explanation categories.
