# Meta-learning / Evaluation

## Status
Not started

## Purpose

Evaluate system-level performance across decisions, themes, signals, and versions.

## Responsibilities

- Summarize Top 10 and Top 20 outcomes, excess returns, drawdowns, hit rates, and false-positive rates.
- Compare LLM-only, quant-only, and hybrid evidence groups when possible.

## Dependencies

- Parent spec: [`../meta_learning.md`](../../../src/stock_opportunity_agent/meta_learning.md).
- Consumes review, signal evaluation, decision memory, and data.

## Invariants

- Evaluation must preserve sample windows and version filters.
- Recent results alone cannot justify large framework changes.

## Testing

Cover performance summaries, version filters, sample-size warnings, and benchmark-relative metrics.
