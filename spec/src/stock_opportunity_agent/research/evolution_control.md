# Evolution Control

Frozen contract loading preserves the JSON representation of an accepted numeric
cost ceiling (integer or float). Loading and re-freezing must reproduce its exact
canonical hash without rewriting the original file. Booleans, nonnumbers and
nonfinite/nonpositive values still fail the existing constructor validation.

## V8 finite slow-only control

The run contract supports `fast_then_slow`, one-cycle `slow_bootstrap`, and
finite `slow_only`. Slow-only fixes zero Fast rounds, positive cumulative
`max_slow_cycles`, `min_new_signals_per_cycle`, one committed-only source history
manifest, and bounded role budgets. `--max-cycles` may reduce work in one CLI
invocation but cannot enlarge the contract total across resumes.

A v8 `fast_then_slow` contract may also freeze one committed-only source
history manifest: this is dual-loop continuation, requested by passing an
explicit `--cycle-mode fast_then_slow` together with `--slow-history-from`.
Fast-round targets stay positive, and the import follows the identical
succession rules below (namespaces, exact Registry, provisional residents,
pooled evaluation, chain continuity on resume). `--slow-history-from` without
an explicit mode still infers `slow_only`, and `slow_bootstrap` remains
mutually exclusive with a history manifest.

History import preserves namespaced pointer-reachable history: the immediate
source contributes one namespace, and that source's own imported namespaces
are carried forward unchanged so multi-hop successor chains keep the full
namespaced history that resident enumeration and reflection footprints read.
Exact Registry, usage, experiment, and memory hashes are preserved. It never
imports staged or rejected work as completed history. Provisional residents are the one
exception to dropping staged work: the history manifest carries the source's
`signals_candidates` tree (excluding the `.rejected` archive) so provisional
residents and their pooled evaluation history survive workspace succession,
and the successor enumerates provisional attempts from the namespaced
imported cycle artifacts plus its own committed cycles — pooled three-zone
accumulation therefore continues across workspace boundaries instead of
resetting to zero in every successor. The initial seed hash is checked once;
subsequent Registry continuity comes from committed cycle state so legitimate
promotion does not conflict with the frozen seed.
Learning-event continuity is transitive across execution modes. In addition to
events owned by Fast rounds at or below the source Fast pointer, a Slow-history
manifest carries the exact events already imported through its source's frozen
`slow_bootstrap` or `slow_history` manifest. Those inherited events must exist
byte-for-byte in the source Registry before they may be re-exported. Events found
only in mutable Registry ledgers, and not reachable from either the committed Fast
pointer or a contract-bound import manifest, remain excluded.
Imports preserve exact v1/v2 event identity and source metadata. A new committed
Fast bootstrap derives v2 identities from its hash-verified source records;
existing frozen import manifests remain unchanged and resume with their original
events. No import promotes repeated case/input use into independent evidence.
An unfinished higher-numbered active cycle does not invalidate the committed
prefix: its staged files are ignored. Import is allowed only when the live
Registry still equals the version/hash recorded at the committed pointer, the
active cycle id is strictly after that pointer, and every artifact required for
each committed cycle exists. A post-transition/pre-pointer Registry mismatch or
an incomplete committed cycle fails closed because the committed snapshot
cannot then be reconstructed safely. Within a running slow_only workspace the
live Registry may advance past the imported history manifest: each committed
cycle records its exact input and output Registry identity, and resume accepts
a live Registry that equals the committed chain's last output (a promotion
committed by an own cycle), still rejecting any drift the chain does not
explain. Each CLI invocation also bounds every cycle's wall time with a
watchdog: a silent stall (CPU-bound explosion or wedged I/O) becomes the
retryable channel — exit 75, auto-resume, cycle restart from the committed
boundary with request-cache replay — instead of an unbounded hang.

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

Every newly frozen executable contract records `max_parallel_plans`; the CLI
defaults it to 2 and validates it as a positive integer no greater than the
candidate count. Runtime passes values above 1 to a production evaluator
factory that creates worker-local mutable role/resolver/client state. Legacy
contracts without the field execute with 1, preserving the proven V130
sequential composition. The workspace lock still has one coordinator, and all
worker progress is funneled through a lock-protected append so event order and
sequence ids remain valid.


The production evidence resolver connects configured Finnhub news after Alpha
Vantage, matching the existing news capability catalog. The fallback uses the
same managed transport, cache, ledger and frozen authorization ceilings. A new
code checkpoint requires a successor contract; an interrupted workspace is not
retroactively run against changed adapter wiring.


## Imported committed Signal tracking

Hash-verified committed Slow-history and Fast-bootstrap learning events use the
same tracking bridge as local round commits. It derives only the purposes declared
by exact version metadata, preserves imported event identities, and never imports
staged/unbound rows as target effectiveness.
