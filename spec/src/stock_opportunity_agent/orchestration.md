# Orchestration

## Status
Not started

## Purpose

Coordinate the daily, weekly, monthly, quarterly, and cold-start workflows without embedding business logic inside pipeline glue.

## External Interface

Expected pipelines:

- `cold_start_case_learning`
- `daily_monitor`
- `weekly_scan`
- `monthly_review`
- `quarterly_walk_forward`
- `manual_research`

Each pipeline should produce a run manifest with config, versions, input windows, outputs, warnings, and artifact paths.

## Responsibilities

- Execute modules in dependency order.
- Write run manifests and logs.
- Make incremental reruns possible.
- Use current universe state so daily and weekly runs prioritize changed tickers instead of reanalyzing the whole market from scratch.
- Stop early on missing critical data or failed validation.
- Keep long-running tasks resumable where practical.

## Dependencies

- Consumes config and coordinates all other modules.
- Writes outputs through memory and reports rather than bypassing module boundaries.

## Invariants

- A pipeline run must record active config, data, prompt, model, scoring, signal, and ranking versions.
- Failed pipeline steps must not leave partial decisions that look final.
- Weekly recommendations must be persisted before reports are considered complete.
- Cold-start and live-scan paths must both obey point-in-time rules.

## Testing

Tests should cover pipeline ordering, failure handling, run manifests, idempotent reruns, and correct handoff between modules.
