# Signals / Evaluation

## Status
Not started

## Purpose

Evaluate signal performance over historical decisions, cases, segments, and review outcomes.

## Responsibilities

- Track precision, recall, false positives, sector behavior, and regime sensitivity.
- Feed meta-learning with evidence for signal changes.

## Dependencies

- Parent spec: [`../signals.md`](../signals.md).
- Consumes memory, review, cases, and data.

## Invariants

- Evaluation must use as-of observations, not revised hindsight packets.
- Short samples should be flagged as weak evidence.

## Testing

Cover historical windows, small-sample warnings, false-positive patterns, and version comparisons.
