# Cases / Labeling

## Status
Not started

## Purpose

Label historical winners, controls, failures, and excluded events for case learning.

## Responsibilities

- Apply user-confirmed winner and failure definitions.
- Exclude cases that violate the study goal, such as deterministic cash-acquisition jumps when configured.

## Dependencies

- Parent spec: [`../cases.md`](../cases.md).
- Consumes historical data and config.

## Invariants

- Label definitions must be versioned.
- Labels must not be inferred from post-hoc narrative.

## Testing

Cover return horizons, benchmark-relative labels, exclusion flags, and definition-version changes.
