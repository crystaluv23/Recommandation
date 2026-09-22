# Evolution Dashboard

## Status

Implemented

## Purpose

Maintain one stable, local, read-only view of Information Plan evolution across
workspaces. It reports committed experimental history and interruption/recovery
diagnostics; it does not run models, approve datasets, reveal Locked Test, or
mutate evolution state.

## Entry Point

The human-facing page is always:

```text
runs/cold_start/evolution/evolution_dashboard.html
```

The adjacent `evolution_dashboard_data.js` contains the self-contained bundle
needed under `file://`; `evolution_dashboard_index.json` is the machine-readable
copy. The page changes runs through one in-page selector rather than producing a
new primary HTML page per run.

## V1 Workspace Projection

A direct child directory is a v1 workspace only when it contains the Plan
Archive/experiment structure. The builder reads
`state.json:last_completed_round` first, then loads only checkpoints and Plan
records reachable at or below that pointer. It projects:

- candidate Plan id, parent ids, concise four-part Plan summary, and metrics;
- round candidate median/best and committed archive best;
- quality-diverse current Top-K ids and scores under frozen selection limits;
- full-trajectory count, per-case stop reasons, Signal/LLM usage totals;
- `cycle_state.json` active/completed cycle and resume phase;
- append-only debug event count, interruption count, and a bounded recent-event
  window;
- count of corrupt/truncated debug-event lines ignored during projection; and
- `contains_final_test_metrics=false`.

For each committed candidate, the projection also reports technical completion
count/rate and failure-class counts separately from formal metrics; Anchor,
Random, and Combined metrics remain visible. Magnitude reporting includes the
predicted-class distribution, true-class support, per-class recall, and
underestimate/overestimate/missed-surge counts. A technical exclusion stays in
the formal score denominator but is not labeled a correct research judgment in
these completion diagnostics. This prevents a higher macro-F1 or a negative-case
abstention from being presented as proof that higher-magnitude discrimination or
research completion improved.

Plan files, trajectory files, checkpoints, or events above the committed pointer
must not create a chart round. Staged artifacts may contribute only to the
explicit active/resume status, never to F1 or Top-K.

## Legacy Compatibility

Existing `evolution_history.json` runs from the superseded engine remain
readable and are clearly marked `legacy_scheme_genome`. Malformed runs are
listed under `skipped_runs` without blocking valid v1 or legacy runs.

## Refresh Contract

Initialization, status, completed round/cycle, exact-request pause, and
interrupt paths refresh the bundle atomically. During a continuous CLI run,
each durable round/cycle boundary refreshes the bundle without waiting for the
supervisor to stop. The refresh performs no network I/O and never reads
final-test labels. The HTML reload button rereads only the adjacent generated
bundle.

## Testing

Tests cover mixed v1/legacy discovery, committed-pointer filtering, malformed
run isolation, F1/Top-K projection, cycle/interruption fields, recent-event
bounds, secret-free output, atomic bundle writes, and `file://` script shape.
