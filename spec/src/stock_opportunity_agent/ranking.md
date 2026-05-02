# Ranking

## Status
Not started

## Purpose

Rank candidates within segments, across themes, and across the full market. Ranking turns individual research into a portfolio of watchlist priorities.

## External Interface

Expected outputs:

- Top watchlist,
- high-conviction candidates,
- wait-for-pullback candidates,
- thesis-interesting-but-expensive candidates,
- likely narrative traps,
- new additions, removals, upgrades, and downgrades.

## Responsibilities

- Compare candidates inside the same segment.
- Compare final opportunity scores across themes while preserving theme context.
- Detect crowding, redundancy, and sector concentration.
- Explain rank changes from prior runs.
- Produce stable ordered outputs for reports and memory.

## Dependencies

- Consumes scanner candidates, research outputs, score cards, themes, memory, and config.
- Feeds reports, decision memory, monitoring, and review.

## Invariants

- Ranking must not collapse all context into a single unexplained number.
- Ranking should preserve why a candidate is above close alternatives.
- Existing watchlist names should not disappear without a reason.
- Cross-sectional comparisons must be as-of date aware.

## Testing

Tests should cover stable sorting, tie-breakers, category assignment, rank-change explanations, sector concentration warnings, and missing prior-run memory.
