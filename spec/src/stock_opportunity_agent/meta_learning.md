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
- Generate testable hypotheses instead of direct code changes.
- Run walk-forward experiments before recommending framework changes.
- Track prompt, scoring, signal, model, data pipeline, universe, and ranking versions.

## Dependencies

- Consumes review records, signal memory, decision memory, config, reports, and historical data.
- Produces proposed config, prompt, signal, scoring, or architecture changes for human approval.

## Invariants

- Do not make large framework changes based on one month of results.
- Do not silently overwrite prompts, scoring weights, schemas, or memory.
- Low-risk changes may be proposed frequently; medium and high-risk changes require human approval.
- New versions should be compared with old versions before promotion.
- Recent samples matter, but cannot erase long-term evidence.

## Testing

Tests should cover hypothesis records, approval states, experiment result comparison, version tracking, and guardrails against automatic high-risk changes.
