# Evolution Control

## Purpose

Own frozen run contracts, recovery/preflight checks, role composition, and the
bounded Fast/Slow cycle entry point.

## Invariants

- Only committed workspace pointers define progress.
- Runtime verification binds code, dataset, Signal Registry, and model
  identities before execution.
- Readiness, external authorization, transmitted work, and committed state are
  represented separately.
- This module composes lower layers and contains no role-specific parser.
