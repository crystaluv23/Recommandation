# Meta-learning / Proposals

## Status
Not started

## Purpose

Create change proposals for prompts, scoring, signals, data sources, modules, and review rules.

## Responsibilities

- Turn evaluation and error analysis into testable hypotheses.
- Classify risk level and required approval.

## Dependencies

- Parent spec: [`../meta_learning.md`](../meta_learning.md).
- Consumes evaluation, experiments, review, and memory.

## Invariants

- Proposals do not directly modify production behavior.
- Medium and high-risk proposals require human approval before implementation.

## Testing

Cover proposal schemas, risk classification, approval states, and rejection paths.
