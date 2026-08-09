# Cold Start Run Workspace

This directory is the local workspace for formal cold-start research, Ralph
source/acquisition diagnostics, and the active dual-loop information-plan
evolution system. Generated run directories are ignored by git.

## Formal and Ralph workspaces

```text
runs/cold_start/
  formal/<run_id>/
    01_universe/
    02_prices/
    03_selection/
    04_documents/
    05_packets/
    06_research/
  ralph/<run_id>/
    research_information_plan.json
    information_requirements.json
    evidence_coverage_ledger.json
    atomic_evidence_by_case.json
    raw_vs_organized_evaluation.json
    ralph_experiment_summary.json
  evolution/<run_id>/
    plans/
    signals/
    signals_candidates/
    raw_info/
    experiments/
    meta/
    cache/
    state.json
```

`formal/01_universe` through `formal/05_packets` are pre-model checkpoints.
Interrupted research should reuse compatible stage outputs rather than repeat
the universe scan. `04_documents` preserves source content and coverage;
`05_packets` remains the complete point-in-time packet audit even when a
coverage gate excludes thin cases from model calls.

`ralph/<run_id>/` remains the broad retrospective information-requirement,
source acquisition, atomic extraction, and raw-versus-organized diagnostic.
It may expose labels only in explicitly marked discovery/diagnostic stages.
Blind evaluation remains anonymous, point-in-time, and no-web. The repository
has no human-curated gold packet, and a development holdout used to propose a
change is not independent validation for that proposal.

## Active evolution workspace

The former A/B/C `SchemeGenome` search, dashboard, provider preflight CLI, and
its per-run configuration family were removed. The active system follows
[`spec/src/stock_opportunity_agent/research/scheme_evolution.md`](../../spec/src/stock_opportunity_agent/research/scheme_evolution.md):

```text
Fast Loop: adaptive Information Plan experiments
-> Plan Archive S/E/J/R/U/T
-> quality-diverse Top-K plus random parents
-> FIFO experiment-grounded meta-info

Slow Loop: Signal Mining and Signal Update
-> signals_candidates/
-> schema/execution/leakage/evidence/duplicate validation
-> versioned promotion into signals/
```

The three dataset roles are separate:

- Discovery labels are visible only to Signal Mining/Update.
- Evolution Validation labels remain hidden until each prediction is durably
  written and are then used by the scorer and Predictor self-reflection.
- Locked Test is absent from ordinary evolution calls.

Stage 1 predicts whether the fixed horizon reaches at least 2x. Stage 2, when
predicted positive, returns `2-3x`, `3-10x`, or `10x+`. Binary F1 is initial Plan
fitness; precision, recall, magnitude accuracy, and magnitude macro-F1 remain
diagnostics.

Initialize a run workspace and materialize the 12 manually defined v1 Signals:

```sh
PYTHONPATH=src python3 scripts/evolve_information_schemes.py init \
  --workspace runs/cold_start/evolution/<run_id>
```

Validate the source-controlled seed catalog without changing a real workspace:

```sh
PYTHONPATH=src python3 scripts/evolve_information_schemes.py validate-catalog
```

Inspect committed state:

```sh
PYTHONPATH=src python3 scripts/evolve_information_schemes.py status \
  --workspace runs/cold_start/evolution/<run_id>
```

Actual Research Controller, Signal Retrieval Agent, Predictor, proposer,
critics, and Signal Mining/Update agents are injected through the Python API.
This keeps provider credentials and task-specific execution policy out of a
generic repository config. External model calls require a separate exact
preflight and explicit authorization; workspace initialization never transmits
data.

`state.json:last_completed_round` is the only authority for restore and parent
selection. Fine-grained artifacts may exist for an interrupted round, but a
round becomes official only after its complete Plan records, trajectories,
metrics, reflections, archive state, and meta entry are checkpointed and the
pointer advances atomically. Artifacts above the pointer are staged recovery
inputs, not completed history.

Keep durable lessons in `memory/`, durable design in `spec/`, and only commit
code or documentation changes.
