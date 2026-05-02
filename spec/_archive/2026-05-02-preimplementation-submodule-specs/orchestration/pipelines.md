# Orchestration / Pipelines

## Status
Not started

## Purpose

Coordinate cold-start, daily, weekly, monthly, quarterly, and manual research workflows.

## Responsibilities

- Execute module steps in dependency order.
- Make reruns incremental and failure-aware.

## Dependencies

- Parent spec: [`../orchestration.md`](../../../src/stock_opportunity_agent/orchestration.md).
- Coordinates all modules through their public interfaces.

## Invariants

- Pipeline glue should not contain hidden business logic.
- Failed steps must not leave partial decisions that look final.

## Testing

Cover step order, retry behavior, partial failure, idempotency, and manual-run entry points.
