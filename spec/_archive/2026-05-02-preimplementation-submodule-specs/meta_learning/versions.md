# Meta-learning / Versions

## Status
Not started

## Purpose

Track prompt, scoring, signal, model, data-pipeline, universe, ranking, and config versions.

## Responsibilities

- Attach versions to decisions, reviews, experiments, and reports.
- Compare version performance without losing historical context.

## Dependencies

- Parent spec: [`../meta_learning.md`](../../../src/stock_opportunity_agent/meta_learning.md).
- Consumes models, config, memory, and reports.

## Invariants

- Recommendations without version stamps are incomplete.
- Version promotion requires recorded rationale.

## Testing

Cover version stamps, comparison filters, promotion records, and missing-version validation.
