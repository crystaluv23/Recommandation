# Monitoring / State Machine

## Status
Not started

## Purpose

Manage watchlist and thesis states after candidates enter memory.

## Responsibilities

- Apply valid transitions among ignore, monitor, thesis forming, high-priority watchlist, action candidate, thesis validated, thesis broken, and archived.

## Dependencies

- Parent spec: [`../monitoring.md`](../../../src/stock_opportunity_agent/monitoring.md).
- Consumes events, review records, scores, and memory.

## Invariants

- State transitions require reason and evidence.
- The state machine cannot create trade orders.

## Testing

Cover valid transitions, invalid transitions, thesis-broken paths, and archived records.
