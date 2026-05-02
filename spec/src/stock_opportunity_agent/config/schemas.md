# Config / Schemas

## Status
Not started

## Purpose

Define typed configuration schemas for universe filters, data sources, storage, scoring, prompts, pipelines, and meta-learning policies.

## Responsibilities

- Keep config fields explicit and versionable.
- Distinguish required values, defaults, optional vendor-specific values, and secrets.

## Dependencies

- Parent spec: [`../config.md`](../config.md).
- Uses model validation patterns but should not depend on runtime pipelines.

## Invariants

- Secrets must not be serializable into run manifests or reports.
- Risk-bearing thresholds should be named clearly enough to review.

## Testing

Validate default config, minimal config, bad thresholds, unknown fields, and secret redaction.
