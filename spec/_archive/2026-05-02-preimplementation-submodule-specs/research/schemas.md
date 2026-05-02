# Research / Schemas

## Status
Not started

## Purpose

Define structured output schemas for LLM research and critique results.

## Responsibilities

- Validate old narrative, new narrative, thesis, evidence, risks, catalysts, scores, and recommendation state.
- Reject ungrounded high-priority outputs.

## Dependencies

- Parent spec: [`../research.md`](../../../src/stock_opportunity_agent/research.md).
- Uses models and validation.

## Invariants

- Evidence for and evidence against must both be representable.
- Claims affecting scores must have source or inference markers.

## Testing

Cover valid outputs, missing evidence, invalid scores, unknown states, and ungrounded high-confidence claims.
