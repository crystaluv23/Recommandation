# Meta-learning

## Status
Not started

## Purpose

Evaluate the system itself. Meta-learning finds systematic errors, proposes improvements, runs experiments, and controls version changes without allowing uncontrolled self-modification.

## External Interface

Core components:

- Performance Evaluator
- Error Analyzer
- Hypothesis Generator
- Experiment Runner
- Version Controller
- System Design Recommender

Expected records:

- `PerformanceSummary`
- `ErrorAnalysis`
- `ImprovementHypothesis`
- `ExperimentRecord`
- `VersionComparison`
- `ChangeProposal`

## Responsibilities

- Evaluate Top 10 and Top 20 results across 1-month, 3-month, and 6-month horizons.
- Compare LLM-only, quant-only, and hybrid signal groups when data allows.
- Identify prompt bias, scoring weakness, data-source noise, sector-specific failures, and regime sensitivity.
- Evaluate whether theme-first, stock-first, or hybrid discovery is currently producing better candidates.
- Track whether prompts are becoming too bullish, too theme-seeking, too tolerant of weak evidence, or too dismissive of contrary evidence.
- Estimate which data sources or evidence families add value by sector and which mostly add cost or noise.
- Generate testable hypotheses instead of direct code changes.
- Run walk-forward experiments before recommending framework changes.
- Run new versions in shadow or side-by-side mode when the blast radius is meaningful.
- Track prompt, scoring, signal, model, data pipeline, universe, and ranking versions.

## Change Risk Classes

- Low-risk proposals may adjust bounded parameters, prompt wording, report emphasis, review labels, or candidate tie-breakers. They still require versioning, recorded rationale, and post-change monitoring.
- Medium-risk proposals may add data sources, change universe thresholds, alter signal weights materially, add a new theme or scoring component, or change promotion thresholds. They require experiment evidence and human approval before becoming the production default.
- High-risk proposals include brokerage integration, order placement, leverage, position sizing, destructive memory rewrites, canonical schema rewrites, or replacing the top-level recommendation framework. They must not be applied automatically and require explicit top-down design confirmation before implementation.

## Dependencies

- Consumes review records, signal memory, decision memory, config, reports, and historical data.
- Produces proposed config, prompt, signal, scoring, or architecture changes for human approval.

## Invariants

- Do not make large framework changes based on one month of results.
- Do not silently overwrite prompts, scoring weights, schemas, or memory.
- Low-risk changes may be proposed frequently; medium and high-risk changes require human approval.
- New versions should be compared with old versions before promotion.
- Recent samples matter, but cannot erase long-term evidence.
- A meta-learning recommendation is not itself permission to modify code, schemas, or trading scope.

## Testing

Tests should cover hypothesis records, approval states, experiment result comparison, version tracking, and guardrails against automatic high-risk changes.
