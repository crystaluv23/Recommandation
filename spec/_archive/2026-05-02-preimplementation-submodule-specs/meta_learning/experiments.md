# Meta-learning / Experiments

## Status
Not started

## Purpose

Design and run controlled experiments for proposed system changes.

## Responsibilities

- Define test windows, old/new versions, success criteria, and promotion gates.
- Run walk-forward or replay tests when data allows.

## Dependencies

- Parent spec: [`../meta_learning.md`](../../../src/stock_opportunity_agent/meta_learning.md).
- Consumes evaluation, config, signals, scoring, and historical records.

## Invariants

- Experiment definitions must be recorded before results are interpreted.
- Passing one narrow sample does not automatically promote a change.

## Testing

Cover experiment records, comparison outputs, failed experiments, and promotion gate logic.
