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
Formal cold-start runs have a single execution entry point:
`scripts/run_cold_start_formal.py`. They default to
`runs/cold_start/formal/<run_id>/` so diagnostic reports, formal checkpoints, and
future recurring runs do not share a flat output directory.

Initial `cold_start_case_learning` is implemented as an auditable local pipeline
that runs supplied historical cases through retrospective inflection discovery,
    blind as-of analysis, case learning, initial theme-map construction, and
    research-playbook synthesis, then writes
`inflection_analyses.json`, `pre_surge_signal_logic.json`,
`signal_definitions.json`, `case_signal_observations.json`,
`theme_maps.json`, `surge_research_playbooks.json`,
`blind_case_analyses.json`, Ralph Loop information-scheme proposal artifacts,
and `manifest.json`. It can also write promoted
definitions into the local signal library, write cold-start theme maps into the
local theme library, write surge-research playbooks into the local playbook
library, append Ralph information-scheme proposals to local proposal memory,
and apply versioned control-matching criteria when supplied.
Long-running LLM research writes partial checkpoints as individual inflection
and blind analyses finish, and reruns should load completed blind analyses
instead of spending LLM budget again. Retrospective web-enabled inflection
discovery should be cached by symbol and outcome window so the same historical
anchor is not researched separately for every T-slice packet. Late-stage
playbook synthesis should not invalidate an otherwise complete run when provider
JSON is malformed; it should retry and then fall back to a deterministic
candidate playbook with warnings. The remaining first-run blockers are deeper
packet context coverage, production outcome/matching definitions, clean provider
coverage for a universe-wide historical candidate scan, OpenRouter web-search
response handling for retrospective inflection discovery, and review of the
first full-market run's data-quality warnings.
The formal runner owns the pre-LLM stage order:
universe -> prices -> selection -> provider/web context -> packets -> context
coverage gate -> research. The context stage is a pre-packet checkpoint for SEC
filings/facts, provider news and transcripts, report/theme web summaries, web
queries, catalysts, warnings, and later coverage reports. It should be reused on
reruns just like universe, prices, and candidate selection. A formal rerun may
load an existing eligible-universe checkpoint when a listing provider is
temporarily unavailable, but it must still reapply the current eligibility
filter before selection.

Formal context acquisition supports `--web-context-mode cached|off` and
`--coverage-gate-mode warn|enforce`. `warn` mode records insufficient coverage
without excluding packets. `enforce` mode excludes insufficient packets from
blind LLM analysis and signal learning while preserving the full packet audit in
`05_packets/historical_cases.json` and the coverage report in
`04_documents/documents_and_catalysts.json`.

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
- Run Ralph Loop only inside formal cold-start / historical learning; it may
  propose a new blind information scheme but must not promote that scheme into
  daily or weekly prompt defaults.
- Keep run workspaces stage-oriented: universe, prices, selection, unstructured
  context, packets, then LLM/research artifacts.
- Do not treat generated historical packets as learning-ready unless their
  context coverage report says they have enough company evidence plus supporting
  financial, theme, catalyst, or risk context.

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
- Context acquisition may use identity and web search before packet assembly;
  blind cold-start assessment must stay anonymous and web-disabled.
- Ralph Loop diagnostics are retrospective and label-aware, while Ralph blind
  scheme validation uses only anonymous point-in-time packet contents.

## Testing

Tests should cover pipeline ordering, progress reporting, failure handling, run
manifests, idempotent reruns, and correct handoff between modules.
