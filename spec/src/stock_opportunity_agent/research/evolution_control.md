# Evolution Control

## V8 finite slow-only control

The run contract supports `fast_then_slow`, one-cycle `slow_bootstrap`, and
finite `slow_only`. Slow-only fixes zero Fast rounds, positive cumulative
`max_slow_cycles`, `min_new_signals_per_cycle`, one committed-only source history
manifest, and bounded role budgets. `--max-cycles` may reduce work in one CLI
invocation but cannot enlarge the contract total across resumes.

History import preserves one source namespace and exact pointer-reachable
Registry, usage, experiment, and memory hashes. It never imports staged or
rejected work as completed history. The initial seed hash is checked once;
subsequent Registry continuity comes from committed cycle state so legitimate
promotion does not conflict with the frozen seed.
An unfinished higher-numbered active cycle does not invalidate the committed
prefix: its staged files are ignored. Import is allowed only when the live
Registry still equals the version/hash recorded at the committed pointer, the
active cycle id is strictly after that pointer, and every artifact required for
each committed cycle exists. A post-transition/pre-pointer Registry mismatch or
an incomplete committed cycle fails closed because the committed snapshot
cannot then be reconstructed safely.

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
