# Scanner / Filters

## Status
Not started

## Purpose

Apply cheap non-LLM screens to reduce the universe before research.

## Responsibilities

- Filter or score candidates using relative strength, financial trend, revisions, catalysts, valuation sanity, and volume behavior.
- Keep explanations for every candidate.

## Dependencies

- Parent spec: [`../scanner.md`](../../../src/stock_opportunity_agent/scanner.md).
- Consumes data, signals, and config.

## Invariants

- Filters must not use future labels.
- A failed data source should produce a warning, not silent neutral treatment.

## Testing

Cover filter boundaries, missing data, stale features, and explanation generation.
