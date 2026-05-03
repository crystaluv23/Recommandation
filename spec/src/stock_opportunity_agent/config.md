# Config

## Status
Started

## Purpose

Own user-editable configuration for universe filters, data sources, scoring weights, prompt versions, pipeline schedules, storage paths, and approval rules.

## External Interface

Expected configuration groups:

- `UniverseConfig`
- `DataSourceConfig`
- `StorageConfig`
- `ScoringConfig`
- `PromptConfig`
- `PipelineConfig`
- `MetaLearningPolicy`

The module should expose a loader that returns validated configuration records and records the active config version for every run.

Initial implementation lives in `src/stock_opportunity_agent/config.py` and supports validated defaults, JSON file loading, and environment overrides for run/storage/API-key variable names, including Massive and Stooq credential env-var names.

## Responsibilities

- Provide conservative defaults for MVP v0.1.
- Validate thresholds such as market cap, liquidity, score cutoffs, and review windows.
- Keep secrets out of committed config files.
- Allow environment-specific overrides without changing specs or source logic.
- Track config version identifiers used in decisions and experiments.

## Dependencies

- Consumed by data, scanner, scoring, research, orchestration, and meta-learning.
- Should not import those modules directly; configuration flows outward.

## Invariants

- A run must not proceed with ambiguous universe, storage, or scoring configuration.
- Data-source credentials must not be written to reports, memory, or logs.
- Meta-learning cannot apply medium or high-risk config changes without human approval recorded in memory.

## Testing

Tests should load minimal, default, and invalid configs. They should verify that secrets are excluded from serialized run records and that version identifiers are stable.
