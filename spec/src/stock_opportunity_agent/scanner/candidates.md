# Scanner / Candidates

## Status
Not started

## Purpose

Merge universe, filter, theme, and existing-watchlist signals into a downstream candidate set.

## Responsibilities

- Deduplicate ticker candidates.
- Preserve multiple inclusion reasons.
- Keep candidate set size configurable.

## Dependencies

- Parent spec: [`../scanner.md`](../scanner.md).
- Consumes universe, filters, themes, and memory.

## Invariants

- Existing watchlist names should remain eligible for monitoring even when not newly screened.
- Candidate reasons must survive into reports or decision memory.

## Testing

Cover deduplication, reason merging, set size limits, and existing-watchlist carryover.
