# Memory / Retrieval

## Status
Not started

## Purpose

Retrieve relevant prior memory for research packets, reviews, and meta-learning without flooding prompts with stale context.

## Responsibilities

- Select prior theses, decisions, errors, company facts, theme stages, and signal lessons.
- Explain why a memory item was retrieved.

## Dependencies

- Parent spec: [`../memory.md`](../../../src/stock_opportunity_agent/memory.md).
- Uses repositories and feeds data packet construction plus research.

## Invariants

- Retrieval relevance must be inspectable.
- Old memory should be included as history, not treated as current fact without freshness checks.

## Testing

Cover ticker, theme, segment, and signal-based retrieval with stale and conflicting memory fixtures.
