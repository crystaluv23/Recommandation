# Config / Loader

## Status
Not started

## Purpose

Load, merge, validate, and version repository configuration.

## Responsibilities

- Read default config plus environment-specific overrides.
- Attach a stable config version to every run.
- Fail loudly when required config is missing or ambiguous.

## Dependencies

- Parent spec: [`../config.md`](../../../src/stock_opportunity_agent/config.md).
- Consumes [`schemas.md`](schemas.md).

## Invariants

- Loading config must not mutate config files.
- Runtime overrides must be visible in run manifests except for secrets.

## Testing

Cover merge order, missing files, invalid values, version generation, and secret redaction.
