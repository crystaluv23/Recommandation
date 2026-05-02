# Review / Errors

## Status
Not started

## Purpose

Label why recommendations failed, lagged, or produced misleading results.

## Responsibilities

- Apply error labels such as thesis wrong, too early, valuation overstretched, regime shift, right theme wrong stock, and narrative without data.

## Dependencies

- Parent spec: [`../review.md`](../review.md).
- Consumes original decision records, outcomes, and later evidence.

## Invariants

- Error labels must preserve the original as-of context.
- Labels should distinguish thesis failure from price-path disappointment.

## Testing

Cover label validation, multiple labels, reviewer notes, and original-record preservation.
