# Cases / Controls

## Status
Not started

## Purpose

Select matched control groups for historical winner and failure studies.

## Responsibilities

- Implement the user-confirmed matching method.
- Record match criteria, tolerances, and rejected candidates.

## Dependencies

- Parent spec: [`../cases.md`](../cases.md).
- Consumes labels, historical structured data, and taxonomy/theme mappings.

## Invariants

- Matching criteria materially affect conclusions and must be confirmed before implementation.
- Controls must be selected using only information available at the case anchor date.

## Testing

Cover deterministic matches, insufficient controls, tolerance changes, and as-of filtering.
