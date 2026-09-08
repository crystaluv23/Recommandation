# Evolution Research Validation

## Purpose

Validate point-in-time research state, evidence references, Signal results,
reflection transitions, and Predictor inputs after generic JSON parsing.

## Invariants

- Evidence must resolve to local immutable source spans.
- Outcome and target-identity leakage checks remain fail closed.
- State transitions preserve stable ids and cumulative research history.
