# Themes / Discovery

## Status
Not started

## Purpose

Detect active and emerging market themes from structured indicators, documents, and memory.

## Responsibilities

- Identify candidate themes and why they may matter now.
- Separate recurring themes from one-off news clusters.

## Dependencies

- Parent spec: [`../themes.md`](../../../src/stock_opportunity_agent/themes.md).
- Consumes data, memory, and research outputs.

## Invariants

- Theme discovery must not promote a theme based only on popularity.
- Evidence should separate demand source, supplier response, financial validation, and market behavior.

## Testing

Use fixture news/transcript clusters to test promotion, rejection, and duplicate theme merging.
