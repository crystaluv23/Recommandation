# Themes / Chain Map

## Status
Not started

## Purpose

Represent industry-chain structure: demand source, core suppliers, infrastructure bottlenecks, second-order beneficiaries, and risks.

## Responsibilities

- Map themes into segments and candidate company types.
- Track leading indicators and transmission paths.

## Dependencies

- Parent spec: [`../themes.md`](../../../src/stock_opportunity_agent/themes.md).
- Consumes discovery output, data, and memory.

## Invariants

- Candidate companies require exposure rationale, not keyword matching alone.
- Chain maps must allow uncertainty and competing interpretations.

## Testing

Cover segment creation, candidate mapping, leading indicators, and conflicting chain hypotheses.
