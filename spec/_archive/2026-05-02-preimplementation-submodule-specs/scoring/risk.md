# Scoring / Risk

## Status
Not started

## Purpose

Apply explicit risk penalties instead of burying risks inside optimistic scores.

## Responsibilities

- Penalize valuation stretch, crowded trades, weak evidence, catalyst distance, customer concentration, low-quality data, and narrative traps.

## Dependencies

- Parent spec: [`../scoring.md`](../../../src/stock_opportunity_agent/scoring.md).
- Consumes research, data, signals, themes, and config.

## Invariants

- Risk penalties must list their drivers.
- Lack of evidence should be a risk, not a reason for neutral confidence.

## Testing

Cover risk caps, multiple penalties, missing evidence, and score-card explanations.
