# Orchestration / Manifests

## Status
Not started

## Purpose

Record run manifests for auditability and reproducibility.

## Responsibilities

- Store run id, schedule type, as-of date, config versions, data windows, model/prompt/scoring versions, outputs, warnings, and artifact paths.

## Dependencies

- Parent spec: [`../orchestration.md`](../orchestration.md).
- Consumes models, config, and outputs from pipelines.

## Invariants

- A completed run without a manifest is incomplete.
- Manifests must not include secrets.

## Testing

Cover manifest creation, missing-version validation, warning capture, and report artifact references.
