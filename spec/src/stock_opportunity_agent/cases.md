# Cases

## Status
Not started

## Purpose

Build the historical case-learning layer for cold start and ongoing research. Cases teach the system what observable differences existed before winners, controls, and failures diverged.

## External Interface

The module should support:

- winner definition rules,
- matched control construction,
- failure-case labels,
- point-in-time case packets,
- blind LLM analysis requests,
- case comparison results,
- and lessons promoted into signal candidates.

## Responsibilities

- Define winners programmatically, such as strong 6-month returns or top percentile outcomes.
- Exclude mechanical jumps such as deterministic cash acquisitions when appropriate.
- Match controls by sector, size, volatility, valuation, prior performance, and market environment after the user confirms the exact thresholds and matching method for the first implementation.
- Construct time slices such as T-180, T-120, T-90, T-60, T-30, and T-0.
- Store postmortems and matched-control lessons in memory.

## Dependencies

- Uses data for historical packets.
- Uses memory for case library persistence.
- Uses research for blind analysis.
- Uses signals and meta-learning to convert lessons into testable changes.

## Invariants

- Do not reveal winner/control labels to blind analysis prompts.
- Do not train only on winners.
- Do not promote a lesson into the signal library without controls or review evidence.
- Every case must state what future information was hidden.

## Open Implementation Questions

Before implementing the first case-learning module, confirm:

- exact winner definitions and return horizons,
- whether industry matching uses GICS, custom theme segments, ETF membership, or another taxonomy,
- market cap, volatility, valuation, and prior-performance tolerance bands,
- the number of matched controls per winner,
- whether matching is nearest-neighbor, rule-based buckets, or a hybrid,
- and how to label failures that looked promising but did not launch.

## Testing

Tests should cover control matching, time-slice construction, future-information exclusion, case labels, and promotion of lessons into candidate signals.
