# Signals / Measurement

## Status
Not started

## Purpose

Measure signal observations from structured data, documents, and research outputs.

## Responsibilities

- Compute feature-backed signal values.
- Convert LLM qualitative observations into evidence-linked signal observations.

## Dependencies

- Parent spec: [`../signals.md`](../../../src/stock_opportunity_agent/signals.md).
- Consumes data, research, and definitions.

## Invariants

- Signal observations must include data availability and confidence.
- LLM-derived observations need source evidence.

## Testing

Use fixture features and research outputs to validate measurements, missing data, and confidence.
