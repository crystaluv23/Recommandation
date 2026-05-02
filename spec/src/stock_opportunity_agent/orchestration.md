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
- `review_gate`

Each pipeline should produce a run manifest with config, versions, input windows, outputs, warnings, and artifact paths.

## Lifecycle Mapping

The orchestration layer maps the product lifecycle into concrete pipelines:

- Phase 1 Historical Case Learning: `cold_start_case_learning`, followed later by monthly case increments from `monthly_review`.
- Phase 2 Current Market Scan: `weekly_scan` through universe filters, structured screens, theme/anomaly expansion, packet construction, LLM research, and scoring.
- Phase 3 Cross-sectional Comparison: `weekly_scan` plus `review_gate`, producing ranked watchlists, research cards, and decision records.
- Phase 4 Continuous Monitoring and Review: `daily_monitor`, weekly rank refresh inside `weekly_scan`, `monthly_review`, and `quarterly_walk_forward`.

Monitoring owns event detection and reanalysis triggers; it does not own the whole discovery workflow.

## Responsibilities

- Execute modules in dependency order.
- Write run manifests and logs.
- Make incremental reruns possible.
- Use current universe state so daily and weekly runs prioritize changed tickers instead of reanalyzing the whole market from scratch.
- Keep weekly scan ordering explicit: non-LLM coarse screen, LLM deep research, non-LLM scoring, LLM-assisted cross-sectional comparison, then review gate and reporting.
- Add new winner, failure, and stale-watchlist cases during monthly review rather than rebuilding the whole case library.
- Stop early on missing critical data or failed validation.
- Keep long-running tasks resumable where practical.

## Dependencies

- Consumes config and coordinates all other modules.
- Writes outputs through memory and reports rather than bypassing module boundaries.

## Invariants

- A pipeline run must record active config, data, prompt, model, scoring, signal, and ranking versions.
- Failed pipeline steps must not leave partial decisions that look final.
- Weekly recommendations must be persisted before reports are considered complete.
- Review-gate output must be stored before an entry can be labeled `action_candidate`.
- Cold-start and live-scan paths must both obey point-in-time rules.

## Testing

Tests should cover pipeline ordering, failure handling, run manifests, idempotent reruns, and correct handoff between modules.
