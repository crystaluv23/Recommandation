# Evolution Dataset Preparation

## Status

Ready - extracted from the runtime control plane without changing artifact schemas

## Purpose

Own the offline data boundary for evolution runs: local input inventory,
label-free legacy Raw Info migration, issuer-disjoint dataset proposals,
expanded-universe selection, and explicit human approval. It does not call
models, execute Fast/Slow rounds, mutate a Signal Registry, or advance an
evolution workspace.

## Public Interface

- `filter_case_price_history`
- `inventory_local_evolution_inputs`
- `migrate_legacy_raw_info`
- `prepare_dataset_proposal`
- `prepare_expanded_dataset_proposal`
- `approve_dataset_proposal`

`evolution_runtime.py` re-exports these functions for compatibility with the
existing maintenance CLI. New code may import them from this module directly.

## Invariants

- Dataset labels retain the fixed six-calendar-month smoothed-price contract.
- Splits remain issuer-disjoint and Locked Test stays sealed during proposal.
- Identity-decision inputs reject outcome fields recursively.
- Approval remains bound to the exact reviewed proposal hash.
- Writes use the shared canonical artifact primitives and preserve immutable
  artifact conflict checks.

## Dependencies

This module may depend on Raw Info storage, listing selection, evolution case
records, and evaluation-dataset feasibility checks. It must not depend on the
runtime role adapters or external model clients.
