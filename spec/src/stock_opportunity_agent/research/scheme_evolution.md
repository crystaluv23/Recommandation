# Research / Information-Scheme Evolution

## Status

Started

## Purpose

Search over auditable information-scheme recipes without changing the fixed
historical exam. The evolved object is `SchemeGenome`, not a signal list learned
once from every labeled case and not the LLM itself.

This module is a controller around the existing Ralph information-plan,
anonymous packet, blind researcher, response cache, and deterministic evaluation
boundaries. It must not implement a second document pipeline, packet renderer,
labeler, or provider client.

## Operating Spine

```text
Codex or a human writes versioned candidate genomes
-> FileSchemeProposer imports bounded candidates
-> schema, leakage, complexity, cost, and duplicate checks
-> materialize each genome from one fold's discovery labels
-> freeze MaterializedScheme
-> build anonymous point-in-time admission inputs
-> persist all predictions
-> reveal admission labels to the deterministic evaluator
-> compare candidate and incumbent on the same samples
-> apply block-bootstrap admission gate
-> retain Pareto candidates in quality-diversity niches
-> aggregate structured meta-lessons
-> return the admitted incumbent and next mutation requests for review
```

The first implementation includes a deterministic synthetic vertical slice,
the evaluator protocol, and `RalphInformationPlanFoldEvaluator`, which reuses
the existing Ralph discovery, atomic-evidence, organized-packet, blind-analysis,
and source-archive boundaries. `HeuristicGenomeBlindAnalyzer` supports local
pipeline diagnostics; `OpenAIGenomeBlindAnalyzer` uses the existing
OpenAI/OpenRouter-compatible client, strict JSON Schema, exact request caching,
source-reference validation, and secret-free request metadata. Synthetic and
heuristic results prove orchestration only and cannot support an
information-plan effectiveness claim.

Implementation is split by responsibility:

- `scheme_evolution_records.py` owns immutable contracts and protocols;
- `scheme_evolution_evaluation.py` owns walk-forward metrics, bootstrap
  assumptions, and admission statistics;
- `scheme_evolution.py` owns proposal validation, persistence, archive, and
  bounded control flow; and
- `scheme_evolution_ralph.py` adapts the controller to existing Ralph cases,
  source documents, packets, heuristic diagnostics, and provider-backed blind
  analysis.

## Public Records

- `DataSourceSpec`: source family, retrieval/cutoff rules, required state,
  freshness, estimated cost, and failure policy.
- `SignalSpec`: source requirements, cutoff, extraction/value/direction rules,
  horizon/decay, evidence minimums, contradiction/confounder handling, missing
  policy, evidence schema, and version.
- `PromptSpec`: template, variables, output schema, model constraints, version,
  and deterministic content hash.
- `SchemeGenome`: parents, generation, mutation operator, change hypothesis,
  source specs, discovery/merge/blind prompts, seed signals, complexity budget,
  metadata, and schema version.
- `MaterializedScheme`: genome/fold identity, discovered and retained signals,
  rejected signals with reasons, and materialization input/output hashes.
- `PredictionRecord`: genome/materialized/fold/sample identities, prediction
  time, probability, decision, confidence, supporting/contradicting evidence,
  missing information, difficulty codes, evidence refs, model metadata, and raw
  response location.
- `SchemeEvaluationResult`: confusion counts, precision, recall, F1, PR-AUC,
  ROC-AUC, Brier score, log loss, precision/recall at K, coverage/abstention,
  period/sector/market-cap metrics, model sensitivity, cost, latency, and
  confidence intervals.
- `SchemeExperimentRecord`: parents, candidate, mutation, fixed-spec hashes,
  evaluation, admission decision/reason, timestamps, and optional git commit.
- `MetaLesson`: scoped lesson with supporting experiments, positive and
  counterexample counts, effect estimate, confidence, suggested mutations, and
  supersession metadata.

The existing top-level `ExperimentRecord` remains the canonical product-wide
meta-learning approval record. `SchemeExperimentRecord` is the detailed
research artifact for one candidate/fold comparison and does not replace it.

## Fixed Framework Records

- `LabelSpec` owns the positive outcome and observation horizon.
- `DataSplitSpec` owns walk-forward construction, purge, embargo, and split
  version.
- `EvaluationSpec` owns thresholds, utility weights, bootstrap assumptions,
  minimum evidence, coverage floor, degradation limit, and cost ceiling.

These records are inputs to the engine and are excluded from genome content and
candidate mutation diffs.

## Proposal Boundary

`SchemeProposer` accepts parents, structured meta-memory, mutation requests, and
a requested count. The initial implementations are:

- `MockSchemeProposer` for deterministic unit and end-to-end tests.
- `FileSchemeProposer` for candidates authored by Codex or a human and reviewed
  as JSON before execution.

An automatic LLM proposer is deliberately deferred. The existing provider
adapters can execute structured blind research, but the current project does
not yet have a sufficiently strict proposer-output audit, provider-independent
request ledger, or evidence that automatic proposer calls add value. The engine
therefore does not depend on an interactive Codex session or one model.

Supported mutation names are `local_refine`, `ablation`, `source_expand`,
`source_replace`, `signal_split`, `signal_merge`, `counterexample_repair`,
`crossover`, `orthogonal_redesign`, `cost_compress`, `robustness_mutation`, and
`random_restart`.

Every candidate records changed fields, expected benefit, possible side effects,
and a falsification test. Candidate validation rejects:

- invalid schema or parent/generation relationships;
- label or outcome variables in blind/merge prompt contracts;
- complexity or estimated-cost budget violations;
- exact duplicates; and
- deterministic near-duplicates above the configured similarity threshold.

Rejected candidates remain auditable with reasons.

## Split and Leakage Boundaries

- Discovery samples may expose labels only to materialization.
- Admission samples are converted to label-free blind inputs before the
  evaluator is called.
- Admission labels are read only after prediction files have been durably
  written.
- A discovery sample is eligible only when its entire label-observation horizon
  plus embargo ends before admission begins.
- One issuer cannot appear on both sides of a fold.
- Sealed-test and live-forward samples are not accepted by the evolution-engine
  constructor or serialized into its state. A separate one-shot evaluator owns
  them after a proposal has stopped changing.
- Existing `DocumentRecord.available_date`, `published_date`, `retrieved_at`,
  `source_id`, `source_url`, symbol, kind, and content-scope fields are the
  current equivalent point-in-time snapshot contract. Full source hashes remain
  computed in Ralph artifacts; the evolution layer references rather than
  duplicates the archive.

## Evaluation and Admission

Predictions are paired by fold and sample. The default utility combines PR-AUC,
precision at K, recall at K, Brier score, worst-period performance, data/token
cost, and complexity. The block bootstrap resamples configured period or issuer
blocks, not independent rows.

Admission requires all of:

- the paired utility-difference lower confidence bound is greater than zero;
- enough paired blocks exist for the statistical claim;
- worst-period degradation stays within the fixed limit;
- coverage meets the floor;
- total cost stays inside budget; and
- no leakage, schema, or persistence violation occurred.

Small samples return `insufficient_evidence`; they do not promote a candidate.
All admitted genomes remain proposal-only pending the existing human-review
boundary.

## Quality-Diversity Archive

The archive groups candidates by configured descriptors such as dominant source
family, dominant signal family, complexity bucket, cost bucket,
precision/recall orientation, and specialist sector. Each niche keeps
non-dominated candidates across predictive quality, calibration, cost, and
complexity. The archive, current incumbent, and sealed test are separate
concepts.

## Persistence and Resume

Each candidate/fold writes:

- materialized scheme;
- prediction records;
- deterministic evaluation;
- paired admission decision; and
- experiment record.

The run state stores fixed-spec hashes, incumbent, archive, candidate
rejections, completed experiment ids, aggregate meta-lessons, next mutation
requests, and proposal status. Only aggregate confusion counts, metrics, and
experiment ids enter meta-memory; no admission sample label or full
sample-specific critic is forwarded to the proposer. Multi-generation runs pass
the merged lessons and requests into the next proposer call. `--resume` reuses
completed work only when the genome recipe, exact fold contents, Ralph
case/source archive, evaluator/model settings, base scheme, and fixed-spec
hashes match. Prediction files are written before any label-aware evaluation
artifact.

## CLI

The thin runner supports dry-run, resume, synthetic mock mode, current-artifact
heuristic mode, real OpenRouter mode, candidate JSON import,
generation/candidate/cost caps, selected folds, archive export, and an
experiment report. Real provider execution reuses the existing provider client
and requires `OPENROUTER_API_KEY`, a fixed provider slug, strict parameter
support, disabled provider fallback, and explicit current token-price inputs;
no credential is persisted. Exact packet/prompt/model/provider requests share a
cache. External execution is never implied by a dry run or heuristic run.

The tracked Codex proposal batch contains:

- a `source_expand` candidate focused on binding orders/backlog/customer wins,
  transaction or restructuring status, financing/listing actions, causal
  industry transmission, and fresh expectation changes; and
- a low-context `ablation` candidate that tests whether static financial
  context is consuming budget without restoring recall.

The existing formal cases use the repository's current 180-day outcome labels.
The real runner therefore defaults its purge horizon to 180 days even though
the product target is 3-6 months. A distinct 90-day label experiment requires a
new versioned outcome definition and relabeled folds; changing only the CLI
number would not relabel the saved cases.

## Explicitly Deferred

- automatic `LLMSchemeProposer`;
- semantic-embedding duplicate search;
- parallel provider execution and provider-specific rate limiting beyond the
  existing client;
- sealed-test execution;
- live-forward evaluation;
- automatic promotion into weekly/daily defaults.

## Testing

Tests cover cutoff rejection, label-free analyzer inputs, discovery/admission
separation, purge/embargo, sealed-test exclusion, invalid candidate JSON,
duplicate filtering, persisted-before-evaluated ordering, exact-input resume
invalidation, admission failure under insufficient confidence, different
archive niches, secret-safe artifacts, cost fail-closed behavior, materialized
packet identity scanning, and a network-free end-to-end mock run.
