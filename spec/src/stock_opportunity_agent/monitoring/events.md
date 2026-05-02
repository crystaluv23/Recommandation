# Monitoring / Events

## Status
Not started

## Purpose

Detect material events that may require reanalysis or state changes.

## Responsibilities

- Track filings, earnings, news, analyst revisions, peer read-throughs, price/volume events, short interest, options events when available, and theme-level changes.

## Dependencies

- Parent spec: [`../monitoring.md`](../monitoring.md).
- Consumes data, memory, themes, and signals.

## Invariants

- Events need source, timestamp, affected tickers, and materiality reason.
- Duplicate events should not repeatedly trigger expensive research.

## Testing

Cover deduplication, materiality thresholds, stale events, and trigger routing.
