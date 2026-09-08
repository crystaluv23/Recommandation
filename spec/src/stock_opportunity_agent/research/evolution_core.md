# Evolution Core

## Purpose

Own immutable evolution records, validation, scoring, evaluation-dataset
selection, role protocols, and pure research helpers. It has no workspace or
Fast/Slow engine dependency.

## Invariants

- Point-in-time and identity masking rules remain fail closed.
- Record serialization stays explicit and schema-compatible.
- Scoring and fitness rules remain deterministic.
- The module may depend on Raw Info and Signal contracts, but not on Plan or
  Signal engine implementations.
