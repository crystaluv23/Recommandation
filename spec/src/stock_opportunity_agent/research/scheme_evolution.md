# Research / Information-Plan and Signal Self-Evolution

## Status

Started - v1 replacement contract

## Purpose

Evolve how the system researches and organizes information, while gradually
improving the reusable Signal Library. The active system has two coupled time
scales:

```text
Fast Loop: Information Plan Evolution
Slow Loop: Signal Mining and Signal Update
```

The evolved object is not one prediction prompt. An `InformationPlan` learns
what basic information to bootstrap, how to formulate initial information
needs, how to reflect over a batch of Signal results, and how to assemble final
context. The Signal Library learns which reusable real-world concepts deserve
observation and how to extract them reliably from Raw Info.

## Supersession

This contract replaces the former active `SchemeGenome + A/B/C + external
proposal dashboard` engine. Old `scheme_evolution_*` implementation modules,
its CLI configuration, and its test contract are removed rather than supported
in parallel. The older Ralph information-plan experiment remains an isolated
retrospective source/acquisition diagnostic; it is not a second active
self-evolution engine.

## Durable State

A workspace contains:

```text
plans/                 # Plan Archive records
signals/               # stable Signal Registry
signals_candidates/    # slow-loop staging only
raw_info/               # append-only facts and source bodies
experiments/            # complete trajectories and round checkpoints
meta/                   # FIFO plan-round reflections
cache/                  # exact reusable model/tool outputs
state.json              # authoritative last_completed_round
```

The three logical cores are the Plan Archive, Signal Registry, and Raw Info
Store. Experiments and meta-info preserve auditability; cache is an optimization
and never evidence that a round completed.

## Information Plan

```text
S = (B, H_init, H_reflect, H_analyse)
```

- `B`, Basic Info Policy: the small company profile needed to form initial
  hypotheses. It must not preload the full Raw Info Store.
- `H_init`: turns Basic Info into hypotheses and natural-language information
  needs, not hard-coded Signal ids.
- `H_reflect`: consumes the complete current research state plus one whole
  Signal batch and returns beliefs, supporting evidence, contradictions,
  resolved/open questions, next needs, and `continue` or `finalize`.
- `H_analyse`: assembles Basic Info, important Signal results, counter-evidence,
  and final state into the label-free Predictor context.

The retrieval path is therefore created at runtime. Candidate Plans may change
only these four fields plus their own id and parent references.

## Runtime Roles

Research Controller answers: “What information is needed next?” It owns
`H_init` and `H_reflect`.

Signal Retrieval Agent answers: “Which existing Signals can answer that need?”
It progressively browses categories, Signal cards, then full specs, and may
select a batch.

Signal Executor retrieves point-in-time Raw Info and runs deterministic
functions or LLM extraction skills.

Blind Predictor consumes only the assembled label-free context. The same
Predictor adapter later receives its saved original context, saved prediction,
uncertainty, and revealed truth to produce post-hoc self-reflection.

Before Predictor handoff, direct identity fields are removed and company id,
current name/ticker, and the caller's source-derived alias inventory are masked
recursively across Signal interpretations, evidence spans, and document refs.
The full unmasked trajectory remains inside the controlled experiment artifact;
the blind context is the only Predictor input.

## `execute_information_plan`

```text
Company -> B -> Basic Info -> H_init -> information needs
-> select and execute Signal batch -> H_reflect
-> repeat until finalize or a runtime guard fires
-> H_analyse -> label-free final context -> blind two-stage prediction
-> persist prediction -> reveal label -> Predictor self-reflection
-> complete ExecutionTrajectory
```

The prediction sink is mandatory and runs before the ground-truth provider is
called. A trajectory preserves Basic Info, every need, selected Signal ref,
Signal result, evidence, reflection state, final context, prediction, ground
truth, self-reflection, usage, and stop reason.

Runtime engineering guards are fixed framework controls:

- maximum Signal rounds;
- maximum Signal calls;
- maximum LLM calls;
- maximum tokens; and
- maximum cost.

They prevent infinite or unexpectedly expensive execution and are not Plan
research logic.

## Dataset Ownership

`EvolutionDataset` has three issuer-disjoint sets:

- Discovery: label-visible only to Signal Mining/Update, preferably matched
  positive and control companies.
- Evolution Validation: labels hidden from plan runtime and Predictor; only the
  deterministic scorer and post-prediction self-reflection boundary may read
  them.
- Locked Test: absent from ordinary fast/slow-loop calls and opened only for a
  separate human-approved acceptance test.

All source reads remain point-in-time. Every observation has a stable `case_id`
distinct from `company_id`; prediction artifacts, label closures, tool access,
and statistics use `case_id`. Repeated as-of cases for one issuer must not cross
dataset ownership boundaries, and no two observations may share a `case_id`.

## Two-Stage Prediction and Labels

Stage 1 predicts whether the fixed future horizon reaches at least 2x:

```text
is_surge = realized_max_multiple >= 2.0
```

For the historical six-month contract, the baseline is the arithmetic mean of
the last five complete trading-day adjusted closes strictly before the as-of
timestamp. The future numerator is the maximum arithmetic mean of any complete
five consecutive trading-day adjusted-close window after as-of and no later
than six calendar months after as-of. Fewer than five valid baseline or future
bars makes the case ineligible. This implements the user's “上涨至少 1 倍” as
price reaching at least `2x`; it does not classify `1x-<2x` as a surge and it
does not reward an isolated one-day spike.

If predicted false, Stage 2 is omitted. If predicted true, the Predictor must
choose one magnitude class:

```text
2-3x | 3-10x | 10x+
```

The saved output also contains qualitative confidence, key reasons, and
uncertainties. Numeric probability is not required. Continuous
`realized_max_multiple` remains the underlying truth.

Stage 1 metrics are precision, recall, and binary F1. Stage 2 metrics are
magnitude accuracy and macro-F1 over true surge cases; a Stage-1 false negative
counts as a missed magnitude prediction. Binary F1 is the initial Plan fitness.
PR-AUC and weighted composite objectives are deferred.

## Label-Revealed Reflection

After prediction persistence, the Predictor may see truth and return:

- whether the prediction was correct;
- failure causes;
- misleading Signals;
- ignored evidence;
- missing information; and
- Plan issues such as premature finalization.

This is usability feedback from the actual consumer of the Information Plan.
It is stored separately from prediction-time uncertainty and cannot alter the
already saved prediction.

## Plan Archive

Each `PlanRecord` stores:

```text
P_i = (S_i, E_i, J_i, R_i, U_i, T_i)
```

- `S`: complete Information Plan;
- `E`: embedding of its canonicalized Plan;
- `J`: metrics;
- `R`: Plan-level critic reflection over the full validation batch;
- `U`: actual Signal selection/state usage;
- `T`: complete execution trajectories.

Canonicalization captures bootstrap, hypothesis, reflection, adaptive search,
and evidence-assembly behavior rather than raw whitespace. The default local
embedder is deterministic and replaceable by an external embedding adapter.

## Parent Selection

Select quality plus diversity:

1. sort all committed Plan records by binary F1 descending;
2. accept a Plan only when its cosine similarity to every selected Plan is
   below the fixed threshold;
3. stop at Top-K; and
4. add up to two random non-selected archive records for exploration.

The proposer receives `[top1..topK, rand1, rand2]`, current FIFO meta-info, and
fixed `H_P`. It is called independently N times. This is conditional sampling,
not a claim of genetic crossover.

## Plan Meta-Info and Fixed Priors

One FIFO window, default length 10, stores structured `RoundMetaEntry` values:
successful/failed plan patterns, false-positive/false-negative patterns, useful
or suspicious Signals, missing capabilities, search implications, and evidence
references.

The only valid update is:

```text
H_R(new completed round experiments) -> new meta entry -> FIFO append
```

The system must not ask an LLM to improve old meta text without new experiment
evidence. Four priors are fixed framework inputs:

- `H_R`: reflect on one completed Plan round;
- `H_P`: propose a new Information Plan;
- `H_E`: mine a candidate Signal;
- `H_U`: repair an existing Signal into a candidate next version.

Changing a prior requires human review and a spec update.

## Fast Loop

For each bounded round under one frozen Signal Registry snapshot:

1. select Top-K diverse plus random parents;
2. call the proposer independently N times;
3. execute every candidate across evolution validation;
4. score saved predictions;
5. run the Plan-level critic;
6. embed and archive `S/E/J/R/U/T`;
7. update observed-policy Signal statistics; and
8. derive one grounded round meta entry and commit the round.

## Slow Loop

After a configured number of fast rounds, unfreeze definitions and run two
Generic Agents.

Signal Mining receives `H_E`, current meta-info, Signal cards, label-visible
Discovery cases, and Raw Info tools. It performs contrastive case analysis and
stages new candidate Signal specs.

Signal Update receives `H_U`, current meta-info, stable Signal stats, committed
Plan experiments, failure trajectories, and version-cloning tools. It stages
`vNext` candidates and cannot overwrite stable files.

Both agents receive domain tools only. All candidates are staged first; the
orchestrator then executes the candidate's non-empty point-in-time fixtures
through the real candidate executor and checks expected canonical state, schema,
leakage (including discovery-case aliases and fixture data), evidence
traceability, semantic duplication, and version progression. Passing candidates
are recorded as `validated_pending_human_approval`; validation alone never
changes the stable Registry. A separate approval command binds reviewer identity
to the exact candidate hash (spec + skill + tests). Only those exact approved
hashes may be promoted, and the Registry version advances once after the approved
batch.

## Persistence and Completion

Fine-grained Plan, trajectory, candidate, and response artifacts may be written
as soon as available. A round becomes official only in this order:

```text
all candidate records and trajectories
-> metrics and Plan reflections
-> archive selection state and round meta entry
-> immutable round checkpoint
-> atomic state.json:last_completed_round advance
```

Restore, reporting, and parent selection ignore artifacts above the pointer.
On restart, an already staged plan, meta record, or checkpoint is reused only
when its canonical JSON exactly matches the artifact currently being committed;
a mismatch fails closed. The pointer remains the last write. Exact external
responses are separately reusable only under their exact request hash.

## Frozen Run and External-Call Contract

Before external execution, the runner writes a secret-free frozen manifest that
binds dataset/splits, Signal snapshot, fixed priors, role-model/provider routing,
code revision, runtime limits, maximum attempts, and cumulative cost. API-key
availability is recorded only as a boolean; secrets are never serialized.

Every newly rendered request is persisted and recursively checked for outcome
fields, future facts, company identity, and cross-case aliases before network
I/O. The durable attempt ledger reserves an attempt and its conservative cost
ceiling before a call, then records completion or failure. An exact-response
cache is keyed by canonical request hash and is evidence of reuse, not evidence
of round completion. Dry-run and preflight perform no external calls. Locked
Test remains sealed from all ordinary commands.

## Local Point-in-Time Migration

Legacy cold-start cases, source documents, and adjusted-price artifacts are
inputs to an explicit migration step, not implicit runtime databases. Migration
must record source hashes, preserve `published_at/available_at`, recompute the
current six-month five-day-smoothed `realized_max_multiple` label from adjusted
prices, assign stable case ids, and materialize a reviewed issuer-disjoint split
manifest. Older terminal-return labels cannot be reused as if they were the
current label. Missing symbols/cases are reported and excluded, never silently
imputed.

## V1 Non-Goals

- Shapley credit or trajectory counterfactuals;
- learned Signal routing or stopping;
- Signal interaction graphs;
- automatic optimization of `H_R/H_P/H_E/H_U`;
- meta-meta evolution;
- complex multi-agent communication;
- automatic locked-test access or production promotion; and
- any order placement, brokerage, leverage, or position sizing.

## Implementation Order

1. Raw Info Store, Signal Registry/spec/result/executor, and 12 seed Signals.
2. Adaptive Information Plan runtime with one manual Plan.
3. Two-stage evaluation, label reveal, self-reflection, and trajectories.
4. Plan Archive, embedding, diverse Top-K, and random exploration parents.
5. Independent candidate sampling, fast-loop evaluation, `H_R`, and FIFO meta.
6. Observed-policy Signal state statistics.
7. Generic-Agent Signal Mining into candidate storage.
8. Generic-Agent Signal Update, executable validation, human approval, and
   versioned promotion.

## Testing

Tests must prove point-in-time reads, dynamic Signal selection, whole-batch
reflection, mandatory prediction persistence before label access, two-stage
metric math, complete Plan records, quality-diverse selection, independent N
proposal calls, grounded FIFO updates, observed-policy counts, candidate
isolation, executable candidate fixtures, exact-hash human promotion checks,
frozen fast-loop definitions, locked-test
isolation, runtime budgets, authoritative completion pointer behavior, and one
offline end-to-end dual-loop cycle.
