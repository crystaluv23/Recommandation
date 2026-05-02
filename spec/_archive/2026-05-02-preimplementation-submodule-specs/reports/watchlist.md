# Reports / Watchlist

## Status
Not started

## Purpose

Render weekly watchlists from ranking, scoring, research, and memory records.

## Responsibilities

- Show ranked candidates, recommendation state, thesis, catalysts, contrary evidence, scores, and rank changes.

## Dependencies

- Parent spec: [`../reports.md`](../../../src/stock_opportunity_agent/reports.md).
- Consumes ranking, scoring, research, themes, and memory.

## Invariants

- Watchlists are not buy/sell instructions.
- High-priority entries must include disconfirming conditions.

## Testing

Cover required sections, score consistency, rank-change explanations, and empty watchlists.
