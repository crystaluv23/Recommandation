# Signals

## Status
Not started

## Purpose

Own the signal library: definitions, applicability, measurement, historical performance, false-positive patterns, and versioning.

## External Interface

Signal categories should initially include:

- fundamental inflection,
- earnings and revenue revisions,
- narrative migration,
- supply-demand reversal,
- catalyst density,
- market early confirmation,
- valuation room,
- analyst disagreement,
- short squeeze potential,
- management tone change,
- supply-chain resonance,
- and novelty/anomaly.

Each signal should expose a definition, data requirements, sector applicability, positive examples, counterexamples, measurement function, confidence, historical hit and false-positive behavior, hindsight-risk notes, and known failure modes.

## Responsibilities

- Store and version signal definitions.
- Compute or request measurable signal observations.
- Capture novelty and anomaly observations such as new company keywords, new customer groups, abnormal financial changes, cross-company language shifts, or lagged supply-chain transmission.
- Track precision, recall, false positives, and sector-specific behavior.
- Preserve counterexamples and known hindsight traps so signals do not become polished post-hoc stories.
- Feed scoring with transparent component evidence.
- Accept candidate signal changes from case learning and meta-learning only through versioned updates.

## Dependencies

- Consumes data, memory, themes, review records, and config.
- Feeds scanner, research, scoring, review, and meta-learning.

## Invariants

- A signal must be measurable or explicitly marked as qualitative.
- Qualitative LLM signals must include source evidence and confidence.
- Signal performance must be evaluated by as-of date, not hindsight summaries.
- Signal definitions cannot be silently changed without a new version.
- Novelty signals must not be promoted on text alone; they need later validation through data, market behavior, catalyst evidence, or explicit review labels.

## Testing

Tests should cover signal definition validation, measurement on fixtures, version changes, missing-data behavior, and false-positive tagging.
