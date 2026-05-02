# Scoring

## Status
Not started

## Purpose

Convert structured signals, theme context, LLM research, market confirmation, valuation state, and risks into transparent component scores and final opportunity rankings.

## External Interface

The module should compute:

- `ThemeTransmissionScore`
- `SegmentTimingScore`
- `CompanyRocketScore`
- `UpsidePotential`
- `LaunchProbability`
- `RiskPenalty`
- `FinalOpportunityScore`

It should return a `ScoreCard` with components, explanations, weights, and version stamps.

## Responsibilities

- Combine quantitative and qualitative evidence without hiding components.
- Keep upside and launch timing separate.
- Apply valuation and crowdedness penalties.
- Penalize pure narrative without financial or market validation.
- Penalize missing revenue exposure checks when a company is being credited for a hot theme.
- Keep launch probability, upside potential, and thesis validation state separate; a validated thesis may still have poor upside if valuation is exhausted.
- Support regime-aware scoring only after the regime design is specified and testable.

## Dependencies

- Consumes config, models, signals, themes, data features, memory, and research outputs.
- Feeds ranking, monitoring, decision memory, review, meta-learning, and reports.

## Invariants

- Final score cannot exist without component scores.
- Score ranges and weights must be versioned.
- LLM score components must be traceable to research evidence.
- Risk penalty cannot be negative evidence hidden inside a positive score.
- Narrative migration cannot receive high contribution from keyword mentions alone; it needs exposure evidence, financial evidence, market confirmation, or a clearly stated low-confidence caveat.

## Testing

Tests should cover score bounds, weighted combinations, missing data behavior, risk penalties, version stamps, and fixture examples where narrative-only candidates are downgraded.
