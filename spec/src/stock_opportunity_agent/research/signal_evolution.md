# Signal and Dual-Loop Evolution

## Purpose

Own Signal-learning aggregation, candidate validation/effectiveness, Slow
Update and Mining, and the finite dual-loop coordinator. It depends on
`evolution_core.py` and `plan_evolution.py`.

## Invariants

- Signal candidates validate before promotion.
- Registry transitions remain version-bound and auditable.
- Slow-loop results and cycle completion preserve existing recovery semantics.
- The module never imports the `scheme_evolution.py` compatibility facade.
