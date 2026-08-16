# Research / Information-Plan and Signal Self-Evolution

## Status

Ready - strict v5 Anchor/Random cumulative dual-loop transition implemented

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
experiments/            # complete trajectories and round checkpoints
meta/                   # FIFO plan-round reflections
cache/                  # exact reusable model/tool outputs
state.json              # authoritative last_completed_round
cycle_state.json        # authoritative completed/active Fast+Slow cycle
```

The three logical cores are the Plan Archive, Signal Registry, and one global
Raw Info oracle stored outside the workspace. The run contract binds the oracle
identity and its initial inventory hash for diagnostics, but later oracle growth
is allowed. A workspace stores document references and resolution events, never
a private Raw Info copy. Experiments and meta-info preserve auditability; cache
is an optimization and never evidence that a round completed.

## Information Plan

```text
S = (B, H_init, H_reflect, H_analyse)
```

- `B`, Basic Info Policy: up to eight analyst-style retrieval requests describing
  which original sources to inspect and within what range. Each request contains
  `request_id`, information-purpose `description`, `source_types`, optional
  `lookback_days` and literal `query`, and `max_documents` up to ten. It does
  not define a fixed company-profile schema and cannot set `as_of`.
- The fixed `H_P` proposal boundary requires every automatically proposed Plan
  to retain one compact point-in-time market backbone request: canonical
  `market_data`, a positive lookback no longer than 60 days, and one source
  document. This gives every case recent price/volume evidence without exposing
  the future label or letting one long price archive consume the Basic Info
  budget. The remaining `B` requests and all three research skills remain
  evolvable. Missing this backbone is a proposal-validation error with the same
  single bounded correction as other malformed Plan content.
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
select a batch. Unknown, empty, or duplicate category/ref selections receive at
most one correction call with the exact allowed set. If the correction remains
invalid, the agent returns an empty selection and the runtime records
`no_signal_match`; it never guesses a category or Signal on the model's behalf.

An `EvidenceResolver` serves both bootstrap and Signal paths. It queries the
global Raw Info oracle first, optionally performs separately authorized and
bounded data acquisition, appends complete provider responses, and immediately
re-queries. Unknown or unavailable capabilities produce structured DataGaps.

All model-facing records enforce JSON types before domain construction. In
particular booleans must be JSON booleans (the string `"false"` is invalid),
list fields must be arrays rather than strings or objects, and required nested
objects/fields cannot be filled by Python truthiness or iterable coercion.
Malformed category/ref containers follow the same bounded correction path
instead of escaping as `TypeError` or being interpreted character by character.

Basic Info is an ordered `BasicInfoBundle` of exact original spans plus complete
lineage. `H_init` receives each request's purpose and these literal spans; it
does not receive a framework-generated summary. Signal Executor asks the same
resolver for complete point-in-time documents and then runs deterministic
functions or LLM extraction skills. Signal results remain derived trajectory
records and are never appended to Raw Info.

Blind Predictor consumes only the assembled label-free context. The same
Predictor adapter later receives its saved original context, saved prediction,
uncertainty, and revealed truth to produce post-hoc self-reflection.

Before Predictor handoff, direct identity fields are removed and company id,
current name/ticker, and the caller's source-derived alias inventory are masked
recursively across Signal interpretations, evidence spans, and document refs.
Composite formal names are split, terminal legal suffixes are removed, and a
distinctive leading brand token is retained to derive ordinary references such
as `Kinross Gold` and `Kinross` from
`Kinross Gold Corp / KINROSS GOLD CORP`. The assembled context is then scanned
again for this current case's expanded target aliases and fails closed before a
Predictor request if any remain. Third-party companies, publishers, and source
identities remain legitimate evidence: aliases from unrelated dataset cases are
not target-identity leaks and must not be scanned at the Predictor boundary.
The full unmasked trajectory remains inside the controlled experiment artifact;
the blind context is the only Predictor input.

## `execute_information_plan`

```text
Company routing identity -> B -> resolve Raw Info -> exact-span Basic InfoBundle
-> H_init -> information needs
-> select and execute Signal batch -> H_reflect
-> repeat until finalize or a runtime guard fires
-> H_analyse -> label-free final context -> blind two-stage prediction
-> persist prediction -> reveal label -> Predictor self-reflection
-> complete ExecutionTrajectory
```

Exact Basic Info spans use fixed 2,000-character chunks with 200-character
overlap and a 48,000-character per-case budget. Query requests rank literal
token hits deterministically; non-query requests rank by recency. Selected
spans are never partially truncated and must remain literal Raw Info substrings.

The prediction sink is mandatory and runs before the ground-truth provider is
called. A trajectory preserves Basic Info, every need, selected Signal ref,
Signal result, evidence, local resolution query, API/cache result, appended
document ref, DataGap, Signal-consumed document id/hash, reflection state, final
context, prediction, ground truth, self-reflection, usage, and stop reason. Each completed case trajectory
is also written independently under
`experiments/trajectories/<plan_id>/<case_id>.json` with an exact input hash
covering the Plan, case, frozen Signal snapshot, and runtime limits. Restart
reuses it only when that hash and serialized trajectory remain exact; this
prevents a process interruption late in a validation batch from repeating
completed case work.

Unrepaired pre-prediction structured-output failures are stored as
`CaseEvaluationFailure` artifacts and stop that candidate without fabricating a
prediction. Post-hoc, critic, or round-reflection failures use explicit
deterministic failure records because they occur after the immutable prediction
boundary.

The Raw Info oracle is deliberately not frozen candidate state. Earlier
candidates may enrich it and later candidates may reuse the new facts; already
completed candidates are not replayed. API cost constrains acquisition and is
diagnostic only, never part of Binary F1 fitness.

Runtime engineering guards are fixed framework controls:

- maximum Signal rounds;
- maximum Signal calls;
- maximum LLM calls;
- maximum tokens; and
- maximum cost.

They prevent infinite or unexpectedly expensive execution and are not Plan
research logic. When a guard or an empty/repeated Signal selection prevents the
controller from finishing normally, the runtime allows one bounded terminal
reflection. The case is valid only if that reflection returns `finalize` and a
source-backed prediction is durably saved.

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

The full-market construction path includes every deduplicated issuer whose
security identity passes the normal-operating-common-stock gate and that has at
least one fixed-calendar case passing the price-window, listing-date, label,
minimum-liquidity, and adjusted-price-integrity gates. It must not first cap the
library or enrich it by outcome class. Eligibility is case-level: an issuer is
not discarded merely because an earlier shared date predates its IPO or lacks
enough liquidity, but that failing date never becomes a case. A case is admitted
only when the listing
is active common equity on NASDAQ/NYSE/NYSE MKT/AMEX, has a resolved CIK and a
valid listing date, is not an exchange-traded product, preferred/debt/security
variant, test symbol, SPAC/blank-check issuer, or other non-operating shell, has
at least `$1m` average pre-prediction daily dollar volume for every admitted
prediction date, and has no `>=4x` or `<=0.25x` consecutive adjusted-close jump
from the baseline lookback through the six-month label horizon. The last rule is
a conservative corporate-action/data-discontinuity gate; it may exclude a real
event rather than silently admit a split/relisting artifact.

The fixed Anchor issuers are assigned first and removed from all other ownership
sets. Remaining eligible issuers are then split into Discovery, Evolution
Validation, and Locked Test. A stratum with at least four eligible issuers gives
Evolution Validation at least two issuer identities while keeping Locked Test
non-empty; this is a rare-class rotation safeguard, not outcome enrichment.
The resulting Evolution Validation share is the
Fast-loop Random candidate pool. Its stored class prevalence is descriptive;
controlled balancing occurs only in the frozen Anchor and per-round Random
snapshots.

### Fast-loop evaluation sampling

Information Plan evolution uses one human-approved fixed Anchor split plus the
human-approved Evolution Validation pool. It does not use the Locked Test and
does not try to mirror the extreme class imbalance of the live market. Every
round evaluates exactly 24 cases:

- Anchor 16: `7 non_surge / 5 2_3x / 3 3_10x / 1 10x_plus`;
- Random 8: `3 non_surge / 2 2_3x / 2 3_10x / 1 10x_plus`; and
- Combined 24: `10 non_surge / 7 2_3x / 5 3_10x / 2 10x_plus`.

The nine positive Anchor cases are an explicitly reviewed symbol/date list.
The seven negative Anchor cases are selected once during proposal creation from
normal eligible non-surge cases by deterministic prediction-date and historical
dollar-liquidity matching, then written into the immutable Anchor artifact.
Changing any Anchor case creates a new dataset proposal/hash and a new run
contract; an active workspace never resamples it.

Every round deterministically pseudo-randomizes and rotates only the eight
Random cases; ordinary execution does not use process-global nondeterministic
randomness. Within each label the order prefers cases with the fewest prior
Random selections, then the least recent selection, then a
`base_seed + round_id + case_id` hash. A shortage in any exact label count or in
distinct issuers fails preflight before any external request. The sampler never
duplicates, silently backfills another label, emits fewer than 24 combined
cases, or selects an Anchor issuer into Random.

Binary F1 is the parent-selection metric. Each Plan persists Anchor, Random, and
Combined metrics. Combined precision, recall, F1, magnitude macro-F1, and
accuracy are recomputed from all 24 saved predictions. In particular, Combined
F1 is not `w_anchor * anchor_f1 + w_random * random_f1`; it is calculated from
the combined TP/FP/FN counts. Anchor F1 is the stable cross-round reference,
Random F1 diagnoses generalization/noise, and Combined F1 determines Top-K.

Evaluation sampling is frozen below the evolution workspace:

```text
evaluation/
  anchor.json
  round_001/
    snapshot.json
```

`anchor.json` contains the exact approved 16 case ids, counts, and dataset-bound
hash. Round snapshots reference that Anchor hash and contain the exact eight
Random case ids, combined ordered case ids, seed, and target/actual counts for
all three cohorts. Existing snapshots are loaded before any sampling. A missing
or changed case referenced by a durable snapshot is an error, not a reason to
resample. Per-Plan diagnostic records persist all case attempts and failure
reasons. Fitness records additionally persist all 24 case ids, snapshot ids,
the three metric groups, evidence-coverage counts, predicted-positive count,
and eligibility decision.

Loading revalidates the same invariants as creation: exact round and seed,
Anchor `7/5/3/1`, Random `3/2/2/1`, Combined `10/7/5/2`, unique case ids, one
distinct company per case across both cohorts, and exact Anchor identity. A
self-consistent snapshot hash cannot weaken these evaluation rules.

### Fitness eligibility

Metrics are calculated only for a complete 24-case prediction set. Each case
must reach `finalize`, persist its prediction before label reveal, and contain at
least one exact Basic Info span or one non-unavailable Signal result backed by
validated source evidence. Incomplete or invalid candidates remain durable
diagnostic attempts.

A complete candidate is still `diagnostic_only` when it predicts zero positives
or has `TP=0`. Such records retain their confusion matrix and an explicit
`precision_defined` flag, but neither Top-K nor random exploration may select
them as parents. If every candidate in a round is ineligible, the workspace
writes `round_rejected` plus a capability-gap report and pauses without
advancing `state.json` or `cycle_state.json`.

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

The fixed Blind Predictor emits a binary Stage-1 `YES`/`NO` decision rather
than a four-way qualitative judgment. `YES` means that, using only the
anonymous as-of evidence, the model estimates at least 50% probability that
the exact adjusted-share-price outcome reaches `2x` inside the fixed horizon;
`NO` means below 50%. The threshold and output schema are fixed framework
controls, not evolvable Plan content. False positives and false negatives are
penalized by the same hidden-label precision, recall, and Binary F1; no class
quota or case-level label is disclosed.

For a `NO` decision, Stage 2 is omitted. For `YES`, the Predictor must
choose one magnitude class:

```text
2-3x | 3-10x | 10x+
```

The saved output also contains qualitative confidence, key reasons, and
uncertainties. If the provider supports output-token log probabilities, a
dedicated fixed call requests exactly one uppercase ASCII `YES` or `NO` token
at temperature `1.0`. Its input is a deterministic label-free condensation of
the final research state and Signal results; repeated Raw Info spans and the
Basic Info bundle are omitted, while `H_analyse` remains present under the
fixed framework semantics. It records the raw vocabulary probabilities of the two
canonical tokens plus `decision_margin = sigmoid(logp_yes - logp_no)`, the
pairwise YES-over-NO strength. A separate temperature-0 structured call authors
the primary binary prediction and explanation. The score call's sampled token
and pairwise strength are both ignored for decision and fitness purposes; any
disagreement with the primary prediction is retained for later reflection.
All three values are nullable together: an API without compatible
token-logprob support, an absent canonical alternative, a provider sentinel,
or an unparseable shape degrades to the ordinary greedy binary prediction with
no numeric decision evidence and must not fail the prediction. Continuous
`realized_max_multiple` remains the underlying truth.

Prediction Stage 1 metrics are precision, recall, and binary F1. Prediction
Stage 2 metrics are magnitude accuracy and macro-F1 over true surge cases; a
Stage-1 false negative counts as a missed magnitude prediction. Binary F1 is the
only Plan-selection fitness. Token probability and decision margin are
prediction-level reflection evidence only and never alter F1, Top-K, or parent
selection. PR-AUC and weighted composite objectives are deferred.

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
already saved prediction. Post-hoc and Plan-level critics receive the optional
token probabilities and decision margin in the saved prediction. After truth
is revealed, feedback chooses `P(YES)` for a true YES case or `P(NO)` for a
true NO case, and maps the pairwise value to `decision_margin` for true YES or
`1 - decision_margin` for true NO. These two truth-aligned values are always
better when closer to one. Critics are explicitly instructed to use them, when
present, as calibration evidence about correct, overconfident, or
underconfident decisions. The framework, not the reflection model, computes the
saved `prediction_outcome.correct` bit from the immutable prediction and truth.

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
The committed round checkpoint also stores the Signal Registry version/hash
used to produce those trajectories. That identity is provenance only: it does
not change `J`, eligibility, or parent-selection weight.

## Parent Selection

Select quality plus diversity:

1. sort all committed Plan records by binary F1 descending;
2. accept a Plan only when its cosine similarity to every selected Plan is
   below the fixed threshold;
3. stop at Top-K; and
4. add up to two random non-selected archive records for exploration.

Selection ranges over the cumulative committed archive, including Plans scored
under earlier Signal Registry versions. Their saved blind-evaluation metrics
are immutable and are not recomputed after a Signal promotion. New candidates
are sampled with the newest Registry and may gradually displace old Plans only
by achieving higher Binary F1 under the normal diversity rule. This is
system-level co-evolution, not a claim that F1 values isolate intrinsic Plan
quality across changing research capabilities.

Random exploration is deterministic per `(frozen parent-selection seed,
round_id)`. A restart before the round commit therefore selects the same
parents, while different rounds still receive independent deterministic draws.

The proposer receives `[top1..topK, rand1, rand2]`, current FIFO meta-info, and
fixed `H_P`. It is called independently N times. Every call also receives a
non-evolvable proposal slot (`round_id` and candidate index/count). Runtime
assigns the Plan id deterministically from the slot and copies parent ids from
the selected parents actually sent to the prompt. Model-supplied structural ids
are ignored. Malformed four-field content receives one bounded correction; a
second failure records `candidate_proposal_rejected` and leaves no partially
committed round. The proposer uses frozen temperature `1.0` sampling; anonymous blind
judging stays at temperature `0.0`. The slot prevents exact-cache collapse and
still rejects repeated ids if sampling returns the same candidate. It
participates in request identity but never becomes part of the candidate Plan.
This is conditional sampling, not a claim of genetic crossover.

Legacy Plans containing `BasicInfoPolicy.fields` remain readable through a
fixed compatibility mapping. New Plan artifacts write only `requests`.

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
are recorded by exact candidate hash (spec + skill + tests). The complete
validation outcome is staged before stable mutation. The orchestrator then
automatically promotes all passing hashes as one cycle-identified, recoverable
batch and advances the Registry version once. Empty passing batches do not
advance it. The next Fast Loop sees the resulting snapshot; the just-completed
Fast Loop remains bound to its input snapshot.

Both Slow agents have an explicit final-output contract:
`{"candidate_refs":[...]}`. A non-empty ref must come from a successful candidate
staging tool call; otherwise the agent returns an empty list. Diagnosis or a
proposed Signal object is not itself a valid final result. Schema and tool
validation errors may be repaired only within the frozen agent-step bound.
Missing required candidate fields, invalid enums, and other `SignalSpec`
deserialization failures are exposed to the agent as domain validation feedback;
they never escape as raw parser exceptions and are never filled with defaults.
External-approval pauses and other orchestration control-flow exceptions are not
domain validation feedback: every Fast evaluator, Generic Agent tool boundary,
candidate fixture, and Slow agent propagates them unchanged to the CLI.

Every durable Plan evaluation attempt contains its complete serialized case
trajectories, including DataGaps and stop reasons. The derived capability
backlog is rebuilt from those durable trajectories while preserving the source
types available from the current resolver, so the Slow loop receives the real
Fast-loop capability gaps rather than an empty or accidentally reopened report.
The complete derived backlog is part of each Slow agent workspace input; merely
writing `capability_backlog.json` without exposing it to the agents does not
satisfy this contract.

## Persistence and Completion

Fine-grained Plan, trajectory, candidate, and response artifacts may be written
as soon as available. A round becomes official only in this order:

Exact request payloads include only semantic model inputs. Runtime usage,
provider cost, cache-hit state, and other execution-accounting fields remain in
audit trajectories but never enter Predictor context; therefore a resume from
an exact cached response renders the same downstream request.

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
Restore also verifies that every checkpoint Plan id resolves to a record with
the same Plan id and round id, that checkpoint Plan ids are non-empty and
unique, and that the state pointer's checkpoint reference resolves to its exact
last round independent of an absolute-versus-relative path spelling. The same
rule applies to checkpoint meta references. A self-consistent but cross-linked
record cannot enter parent selection.

One Fast/Slow cycle has a second atomic `cycle_state.json` marker. It records the
cycle id, starting committed round, fixed round target, current Fast/Slow phase,
input Signal Registry version/hash, current committed output Registry
version/hash, and last completed cycle under the frozen run-contract hash.
After `Ctrl+C`, the supervisor derives completed Fast work from
`last_completed_round`, runs only the remaining rounds, and reuses an exact
staged Slow validation/transition/result before advancing the completed-cycle
pointer. The validated-batch artifact is durable before Registry mutation; the
final Slow result is durable before the cycle pointer. It never infers
completion from individual candidate files or an event log.

`experiments/trajectory.jsonl` is the append-only debug stream for lifecycle,
request/cache, round, candidate, case, score, Top-K, Slow-loop, interruption,
and resume events. Each line carries a UTC timestamp and monotonic sequence
number; it is diagnostic evidence, not a completion authority. A
truncated/corrupt line is counted and ignored so it cannot block recovery or
impersonate a commit.

## CLI Visibility and Local Dashboard

The API runner accepts a structured progress callback. The CLI renders those
events immediately with flushing and includes cycle/round ids, candidate Plan
summaries, per-case progress, request/cache state, candidate metrics, current
quality-diverse Top-K scores, checkpoint commits, resume decisions, and Slow
Signal candidate status. It must never print prompts, credentials, raw packet
content, or identity-masked Predictor inputs.

`init`, local preflight, migration, freeze, `run-cycle`, and `run-loop` require
an explicit global `--raw-info-root`; none may infer a workspace-private Raw
Info directory. `run-cycle` executes or resumes one frozen Fast/Slow cycle.
`run-loop` is a thin supervisor that starts another bounded cycle only after the prior cycle commits;
zero `--max-cycles` means continue until `Ctrl+C`. `KeyboardInterrupt` leaves
committed pointers intact, records an interruption event at the CLI boundary,
refreshes reporting, and exits with the conventional interrupted status. This
does not widen the frozen attempt or cost ceilings.

`scripts/run_information_plan_evolution.sh` is the stable operator-facing
launcher. `new` requires an unused workspace, the global Raw Info oracle, and an
already human-approved feasible dataset; it initializes and freezes one v5
contract, then stops at the first exact-request approval boundary without
external execution. `resume` requires the same workspace/oracle/dataset and
derives progress only from committed pointers. External execution is available
only in `resume` mode with both `--external` and an acknowledgement equal to the
stored contract hash. The launcher composes the Python CLI rather than
implementing a second state machine. It never persists or prints a key, opens
Locked Test, promotes an unvalidated or changed Signal candidate, infers
completion from files, or bypasses request leakage, cost, attempt,
dataset-feasibility, and contract-hash gates. Validated Signal auto-promotion is
part of the bounded cycle state machine, not external-call authorization. The
former DeepSeek-named shell is only a compatibility forwarder to this entry and
carries no workspace, model, budget, or approval defaults.

The stable cold-start default is two Fast rounds with three independently
sampled candidates per round. A one-candidate round remains available as an
explicit low-cost diagnostic, but it is not the operator default because it
provides no within-round quality comparison and makes a first-round TP miss too
likely to halt the fitness-gated run.

Source-data acquisition remains a separate two-step authorization in the stable
launcher. `new` may freeze explicit non-empty provider/capability/source-type
allowlists and positive request ceilings but still performs zero data calls;
`resume` must additionally receive the data-external execution flag. Requesting
runtime data execution when the frozen contract disabled it is an explicit
pause/error, not a silently disabled resolver.
Provider/capability/source-type or ceiling options without `--data-external`
are rejected rather than frozen as dormant authorization.

The CLI classifies exhausted transient transport failures (timeouts, connection
errors, incomplete responses, HTTP 408/429, and HTTP 5xx) with a dedicated
temporary-failure exit status. During the fixed wall-clock window, the launcher
may restart the same exact `run-loop` only for that status, after a short bounded
backoff. Every restart uses the same frozen contract and durable attempt ledger,
so the existing attempt/cost ceilings still apply. Provider rejections, invalid
model content, contract conflicts, and other deterministic failures remain
terminal and are never converted into unattended retry loops.

The single human-facing entry remains
`runs/cold_start/evolution/evolution_dashboard.html`. A read-only builder scans
direct child workspaces, trusts only committed round/cycle pointers, retains
legacy history compatibility, and rewrites the adjacent local data/index
artifacts. The page selects a run in-place and shows Binary F1 by round,
candidate scatter/median, committed best, current Top-K, cycle/resume status,
trajectory counts, stop reasons, and recent debug events. Locked Test metrics
are never included.

## Frozen Run and External-Call Contract

Before external execution, the runner writes a secret-free frozen manifest that
binds dataset/splits, Signal snapshot, fixed priors, role-model/provider routing,
code revision, runtime limits, maximum attempts, and cumulative cost. API-key
availability is recorded only as a boolean; secrets are never serialized.

Every newly rendered request is persisted and recursively checked for outcome
fields and future facts before network I/O. Predictor requests additionally
arrive through a current-case target-identity mask-and-scan boundary; they do not
scan the full dataset alias inventory because legitimate third-party evidence
can share names or short tickers with unrelated issuers. Structured roles
include the provider JSON-object response format in both
the persisted exact request and the provider call, so prompt compliance is not
the only JSON boundary and the format setting participates in the cache hash.
Every structured system message also explicitly requests one JSON object, as
required by providers that reject JSON-object mode without that input token.
The durable attempt ledger reserves an attempt and its conservative cost
ceiling before a call, then records completion or failure. An exact-response
cache is keyed by canonical request hash and is evidence of reuse, not evidence
of round completion. Dry-run and preflight perform no external calls. Locked
Test remains sealed from all ordinary commands.

Missing credentials, a missing/mismatched external acknowledgement, and
exhausted attempt/cost ceilings are control-plane pauses. They propagate across
case evaluation and both Slow agents, leave round/cycle pointers unchanged, and
must never be persisted as Plan failure, Signal-agent schema failure, or
`round_rejected`. The CLI returns a structured reason rather than a traceback.
Only content/schema failures attributable to a bounded candidate may become
candidate diagnostics.

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
8. Generic-Agent Signal Update, executable validation, recoverable automatic
   batch promotion, and versioned transition.

## Testing

Tests must prove point-in-time reads, dynamic Signal selection, whole-batch
reflection, mandatory prediction persistence before label access, two-stage
metric math, complete Plan records, quality-diverse selection, independent N
proposal calls with distinct slot identities, grounded FIFO updates,
observed-policy counts, candidate
isolation, executable candidate fixtures, exact-hash automatic promotion checks,
frozen fast-loop definitions, locked-test
isolation, runtime budgets, authoritative completion pointer behavior, and one
offline end-to-end dual-loop cycle. Recovery tests must additionally cover
independent case-trajectory reuse, interrupt-after-round recovery with no extra
Fast rounds, exact staged Slow-validation/transition/result recovery, a next
cycle that uses the promoted Registry without reevaluating historical Plans,
append-only debug events, CLI
progress flushing, and dashboard filtering to committed pointers.
