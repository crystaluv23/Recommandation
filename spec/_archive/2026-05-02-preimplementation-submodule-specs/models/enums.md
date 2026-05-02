# Models / Enums

## Status
Not started

## Purpose

Define shared status and category enums so modules do not invent incompatible strings.

## Responsibilities

- Own recommendation states, thesis states, evidence source types, error labels, approval states, and run statuses.
- Keep names stable once records are persisted.

## Dependencies

- Parent spec: [`../models.md`](../../../src/stock_opportunity_agent/models.md).

## Invariants

- New enum values that affect stored records require spec updates and migration notes.
- Trading execution states do not belong here unless the project scope is explicitly expanded.

## Testing

Verify serialization values, backward-compatible aliases if any, and rejection of unknown persisted states.
