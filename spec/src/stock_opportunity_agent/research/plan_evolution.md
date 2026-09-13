# Plan Evolution

Backlog refresh in a slow-only workspace consumes the hash-verified Fast context
seed in its v2 Slow-history manifest when the local Fast archive is empty. The
zero local pointer must not erase imported unmet needs. Refresh remains derived
and repeatable, including after Slow validation and restart; it never reads an
unbound ancestor's mutable backlog file.

## V8 Slow cycle persistence

`EvolutionWorkspace` owns immutable cycle files `slow_input.json`,
`slow_memory.json`, and `slow_experiments.json`. Loaders verify schema, cycle,
contract, upstream hashes, and committed source cutoffs. Only the currently
active cycle may resume its uncommitted artifacts. Later cycles enumerate Slow
history strictly through `last_completed_cycle`.

Staging validation requires the exact input/memory/experiments chain. Staging a
result additionally requires the recorded Registry transition output. Every
fresh and shortcut resume path revalidates that same chain. The atomic cycle
pointer advances after the result is durable and never from artifact presence.

## Purpose

Own crash-safe evolution workspace state, runtime Plan evaluation, and the Fast
Plan-evolution engine. It depends on `evolution_core.py` and has no dependency
on the Slow Signal engine.

## Invariants

- Only committed pointers define completed rounds and cycles.
- Staged artifacts remain recoverable but never count as progress.
- Plan evaluation retains Anchor/Random lineage and fitness gating.
- The ordinary capability backlog is derived only from Plan records reachable
  through committed round checkpoints. Each committed round refreshes it after
  archive, learning, and meta publication; staged attempts may contribute a
  separate technical diagnostic but never formal Slow-learning needs.
- A resumed Slow loop refreshes the backlog before creating a new frozen Slow
  validation. An already staged validation retains its exact original backlog.
