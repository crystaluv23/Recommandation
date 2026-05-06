# Orchestration

## Status
Started

## Purpose

Coordinate the daily, weekly, monthly, quarterly, and cold-start workflows without embedding business logic inside pipeline glue.

## External Interface

Expected pipelines:

- `cold_start_case_learning`
- `daily_monitor`
- `weekly_scan`
- `earnings_validation`
- `monthly_review`
- `quarterly_meta_learning`
- `manual_research`
- `review_gate`

Each pipeline should produce a run manifest with config, versions, input windows, outputs, warnings, and artifact paths.
Longer-running pipelines should accept a progress reporter so CLI scripts can
show stages, intermediate summaries, warnings, and final artifact paths.
Stages that depend on external data providers or LLM calls should checkpoint
their completed inputs and partial research outputs before proceeding to the
next expensive stage.

Initial `cold_start_case_learning` is implemented as an auditable local pipeline
that runs supplied historical cases through retrospective inflection discovery,
blind as-of analysis, case learning, and initial theme-map construction, then writes
`inflection_analyses.json`, `pre_surge_signal_logic.json`,
`signal_definitions.json`, `case_signal_observations.json`,
`theme_maps.json`, `blind_case_analyses.json`, and `manifest.json`. It can also
write promoted definitions into the local signal library, write cold-start theme
maps into the local theme library, and apply versioned control-matching criteria
when supplied. Long-running LLM research writes partial checkpoints as
individual inflection and blind analyses finish. Retrospective web-enabled
inflection discovery should be cached by symbol and outcome window so the same
historical anchor is not researched separately for every T-slice packet. The
remaining first-run blockers are the production outcome/matching definitions,
clean provider coverage for a universe-wide historical candidate scan, and
review of the first full-market run's data-quality warnings.

The orchestrated product loop is:

```text
cold-start learning
-> weekly theme-first discovery and watchlist publication
-> daily incremental monitoring of active theses
-> event-time validation when earnings or catalysts arrive
-> monthly review and signal-memory updates
-> quarterly meta-learning experiments and version decisions
```

## Lifecycle Mapping

The orchestration layer maps the product lifecycle into concrete pipelines:

- Phase 1 Historical Case Learning: `cold_start_case_learning`, followed later by monthly case increments from `monthly_review`.
- Phase 2 Current Market Scan: `weekly_scan` through theme and segment scanning, universe filters, structured screens, theme/anomaly expansion, packet construction, LLM research, and scoring.
- Phase 3 Cross-sectional Comparison: `weekly_scan` plus `review_gate`, producing ranked watchlists, research cards, validation contracts, and decision records.
- Phase 4 Continuous Monitoring and Review: `daily_monitor`, `earnings_validation`, weekly rank refresh inside `weekly_scan`, `monthly_review`, and `quarterly_meta_learning`.

Monitoring owns event detection and reanalysis triggers; it does not own the whole discovery workflow.

## Responsibilities

- Execute modules in dependency order.
- Write run manifests and logs.
- Make incremental reruns possible.
- Use current universe state so daily and weekly runs prioritize changed tickers instead of reanalyzing the whole market from scratch.
- Keep weekly scan ordering explicit: theme and segment scan, non-LLM coarse screen, LLM deep research, non-LLM scoring, LLM-assisted cross-sectional comparison, validation contract generation, then review gate and reporting.
- Route active-thesis events to incremental reanalysis rather than full research unless the old thesis no longer frames the new evidence.
- Run earnings validation by comparing actual releases, filings, transcripts, analyst reactions, and price reactions against the original validation contract.
- Add new winner, failure, and stale-watchlist cases during monthly review rather than rebuilding the whole case library.
- Stop early on missing critical data or failed validation.
- Keep long-running tasks resumable where practical.
- Avoid repeated LLM calls for identical retrospective research keys; reserve
  per-packet LLM calls for analyses whose input genuinely differs by as-of date.

## Dependencies

- Consumes config and coordinates all other modules.
- Writes outputs through memory and reports rather than bypassing module boundaries.

## Invariants

- A pipeline run must record active config, data, prompt, model, scoring, signal, and ranking versions.
- Failed pipeline steps must not leave partial decisions that look final.
- Weekly recommendations, active theses, and required validation contracts must be persisted before reports are considered complete.
- Review-gate output must be stored before an entry can be labeled `action_candidate`.
- No high-priority watchlist entry may be emitted without a validation contract.
- Cold-start and live-scan paths must both obey point-in-time rules.

## Testing

Tests should cover pipeline ordering, progress reporting, failure handling, run
manifests, idempotent reruns, and correct handoff between modules.
