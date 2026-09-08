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
- H1 runtime fields are deterministic and cycle-bound. The committed audit
  stores the structured conclusion and an input fingerprint so a later cycle
  can distinguish changed evidence or search strategy from identical work.
  An identical prior `no_testable_hypothesis` or exhausted structured recovery
  suppresses the same H1 work; changed demand, visible capability, Registry,
  applicability inventory, limits, contract, or model identity creates new work.
- Exploration extraction runs in bounded microbatches keyed by stable case refs.
  A failed microbatch cannot discard valid sibling signatures or become a
  domain observation. The full frozen E1 cohort, failed refs, and usage remain
  visible; E2 runs only if both fixed groups still meet the configured grounded
  evidence floor, without replacing validation cases.
- Update evidence packets separate label-free source observations from the
  locally computed outcome relation. Model diagnostics must cite a supplied
  document ref and literal span for every claimed fact before an update draft
  can be considered.
