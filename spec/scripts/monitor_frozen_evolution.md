# Frozen Evolution Process Monitor

## Purpose

Run the already-authorized `run_minimal_rounds.py --root ... --run` from its
frozen source checkout and recover terminal transient transport failures using
the same contract, inputs, cache, and ledger. This is diagnostic orchestration,
not research logic, scoring, Registry publication, or an authorization source.

## Contract

`scripts/monitor_frozen_evolution.py --source SOURCE --root ROOT --control CONTROL`
uses the calling Python runtime and the frozen checkout's `src` path. Before
every launch, source HEAD must match the existing run contract, tracked source
must be clean, and contract/input-manifest bytes must match the initial monitor
snapshot. It never changes source, input records, budget ceilings, or model roles.

A monitor lock and existing process checks prevent a second executor. Runtime
retains its own evolution-run lock. `process.json` records child/wrapper PIDs,
the actual command, source revision, and `running`/`retry_wait`/`stopped` status.
Only final monitor termination creates `exit.json`; every child termination is
archived separately, and monitor events append to a JSONL journal. A live wrapper
in `retry_wait` is an existing job to observe, not permission to start another.

Automatic recovery requires a nonzero, nonsignal child exit, the last traceback
line naming `RetryableOpenAIClientError`, and a matching fresh failed ledger
attempt after that child's start. The unchanged ledger must have attempt and
cost headroom. The monitor waits 30 seconds between recoveries and permits at
most ten automatic recoveries per invocation. Observation timeout, a missing
poll response, a stale error, authorization/payment/budget failure, source drift,
or user interruption cannot cause an automatic restart. SIGINT/SIGTERM stops the
child and disables recovery. Case exclusions and recorded Signal failures stay
in the original artifacts; recovery is never reported as a completed cycle.

## Verification

Test fresh/stale/terminal/signal/control failure distinctions, unchanged ledger
ceilings and exhausted budgets, and source/contract drift. For a real monitored
run, inspect the current wrapper and child command plus persisted lifecycle
records; pointer advancement and research acceptance remain separate checks.
