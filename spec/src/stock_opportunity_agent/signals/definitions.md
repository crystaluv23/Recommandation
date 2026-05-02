# Signals / Definitions

## Status
Not started

## Purpose

Store versioned signal definitions, applicability, data requirements, and false-positive patterns.

## Responsibilities

- Keep qualitative and quantitative signal definitions explicit.
- Record sector/theme applicability and known limits.

## Dependencies

- Parent spec: [`../signals.md`](../signals.md).

## Invariants

- Changing a signal definition creates a new version.
- A signal that cannot be measured must be marked qualitative.

## Testing

Cover validation, versioning, applicability filters, and false-positive metadata.
