# Ranking / Cross Section

## Status
Not started

## Purpose

Rank candidates within segments, across themes, and across the market.

## Responsibilities

- Compare candidates with similar theme exposure.
- Preserve close-call reasoning and category assignment.

## Dependencies

- Parent spec: [`../ranking.md`](../ranking.md).
- Consumes score cards, research outputs, themes, and memory.

## Invariants

- Rankings must be as-of date aware.
- A single final score should not erase segment context.

## Testing

Cover stable sorting, tie-breakers, category output, and sector concentration warnings.
