# Models / Records

## Status
Not started

## Purpose

Define serializable records that cross module boundaries: research packets, evidence, theses, scores, watchlist entries, decisions, reviews, experiments, and run manifests.

## Responsibilities

- Keep field names canonical across the repository.
- Preserve `as_of_date`, source metadata, and version stamps.
- Distinguish raw observations, normalized features, LLM interpretations, and human decisions.

## Dependencies

- Parent spec: [`../models.md`](../models.md).
- Used by every module that persists or exchanges structured records.

## Invariants

- Records that affect recommendations must be auditable and serializable.
- Do not hide component scores or evidence inside opaque text summaries.

## Testing

Use fixture records to verify validation, serialization, equality, and round-trip behavior.
