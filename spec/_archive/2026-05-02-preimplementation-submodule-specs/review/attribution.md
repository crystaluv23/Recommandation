# Review / Attribution

## Status
Not started

## Purpose

Attribute outcomes and errors to signals, themes, scoring components, and research claims.

## Responsibilities

- Identify which signals helped, which failed, and which were absent.
- Feed signal evaluation and meta-learning.

## Dependencies

- Parent spec: [`../review.md`](../../../src/stock_opportunity_agent/review.md).
- Consumes outcomes, errors, signals, scores, and memory.

## Invariants

- Attribution must not pretend correlation is proof.
- Small samples need explicit weakness markers.

## Testing

Cover signal contribution records, missing signal data, small-sample warnings, and theme attribution.
