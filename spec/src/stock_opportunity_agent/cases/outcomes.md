# Cases Outcomes

## Status
Started

## Purpose

Own versioned retrospective outcome definitions, such as what counts as a
"surge winner", neutral control candidate, failure, or unlabeled case after a
forward window has matured.

This submodule exists because outcome definitions affect cold start, monthly
review, future case increments, and experiment comparisons. They must be
testable and replaceable without changing cold-start signal learning.

## External Interface

The submodule should expose:

- `OutcomeDefinition`: versioned thresholds, horizon, and minimum observation
  requirements.
- `OutcomeObservation`: retrospective price outcome measured after an as-of
  date.
- `CaseOutcomeLabel`: winner, control, failure, or unlabeled.
- helpers to measure price outcomes from data-layer price bars and label returns
  under a chosen definition.

Initial implementation uses a conservative close-to-close 180-day default:
winner if return is at least 80%, control if return is between -10% and +20%,
failure if return is at most -20%, and unlabeled otherwise or when too few
trading days are available.

## Responsibilities

- Keep outcome labels outside point-in-time packets and blind research inputs.
- Make definition versions explicit in historical cases and run artifacts.
- Support future comparison of alternate definitions without changing case
  learning.
- Distinguish retrospective labels from live scanner signals.
- Leave richer definitions, such as max-forward-return, drawdown-adjusted surge,
  factor-conditioned labels, and sector-specific thresholds, to later confirmed
  implementations.

## Dependencies

- Consumes data-layer price bars for retrospective outcome measurement.
- Feeds `cases` learning, `review`, and future meta-learning experiments.
- Must not feed live scanner decisions directly because labels use future data.

## Invariants

- Outcome windows are explicitly after `as_of_date`.
- Outcome labels are retrospective review artifacts, never as-of research
  evidence.
- Changing thresholds, horizons, or labeling semantics requires a new definition
  id or version.

## Testing

Tests should cover definition validation, return labeling boundaries, insufficient
future data, and later comparison of alternative definitions.
