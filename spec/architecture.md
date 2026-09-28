# Architecture

## Status
Done

## Architectural Shape

The future source package should be `stock_opportunity_agent`. The design is a local-first research system with explicit boundaries between data, memory, LLM research, scoring, review, and meta-learning.

The system should optimize for auditability and iteration before scale. Local SQLite, DuckDB, Parquet, and file-based reports are good defaults for early versions. Vendor data sources, vector stores, and model providers should sit behind adapters.

## Thesis-Centered Spine

The architecture is organized around a single durable loop:

```text
historical case learning
-> validated research information plan
-> signal library and theme map
-> weekly theme-first market scan
-> structured coarse candidate screen
-> point-in-time research packets
-> LLM research plus skeptic critique
-> hybrid scoring
-> cross-sectional ranking
-> watchlist entry plus validation contract
-> daily event monitoring and incremental reanalysis
-> earnings and catalyst validation
-> monthly review and error labeling
-> signal, theme, company, thesis, and prompt improvements
-> quarterly experiments and version promotion
```

The system does not merely recommend tickers. It creates theses with explicit evidence and validation contracts, then keeps those theses alive until they are validated, broken, stale, or archived.

## Layered Flow

The module dependency flow is:

```text
Configuration
-> Data Layer
-> Memory Layer
-> Theme / Industry Chain Layer
-> Historical Case Learning
-> Signal Library
-> Market Scanner
-> LLM Research Layer
-> Scoring Engine
-> Cross-sectional Ranker
-> Reports and Watchlists
-> Catalyst Monitor
-> Review Layer
-> Meta-learning Layer
```

The operating cadences are:

```text
cold start
-> identify historical winners, controls, and failures
-> discover candidate information requirements across point-in-time windows
-> acquire source-linked evidence and build point-in-time case packets
-> append source facts to the point-in-time Raw Info Store
-> initialize a versioned Signal Registry with deterministic and LLM-driven signals
-> execute adaptive Information Plans against label-hidden evolution validation
-> retain quality-diverse plans and append layered completed-round reflection entries into FIFO meta-info
-> periodically mine or repair candidate signals on label-visible discovery data
-> execute candidate fixtures and validate leakage/evidence/version contracts
-> atomically promote every exact candidate hash that passes the fixed machine-validation contract
-> expose the resulting stable Signal Registry to the next fast-loop group
-> reserve the locked test for a later human-approved acceptance check

daily
-> update prices, volume, filings, news, earnings events, analyst revisions, and theme evidence
-> monitor active watchlist entries and archived reactivation triggers
-> rerun LLM research only for material new information
-> update universe state, thesis status, and memory annotations

weekly
-> scan themes and industry-chain segments before individual stocks
-> apply structured coarse screens and theme-aware candidate expansion
-> build research packets
-> run LLM company research, skeptic critique, and valuation critique
-> compute scores
-> run cross-sectional comparison
-> publish watchlists, research cards, validation contracts, and decision records

monthly
-> review 1-month, 3-month, and 6-month recommendation outcomes as they mature
-> validate or invalidate theses against their contracts
-> label success and failure causes
-> update review, signal, company, thesis, case, theme, and segment memory
-> propose small system improvements

quarterly
-> test whether the framework still fits the market
-> run walk-forward experiments for prompt, signal, scoring, theme, universe, and data-pipeline changes
-> compare versions
-> promote approved versions or keep proposals in the experiment pool
```

## Lifecycle Phases

The system should be understood as four connected phases, not as one large monitoring loop.

### Phase 1: Historical Case Learning

Purpose: establish a validated research information plan and then build the
first signal library without survivorship bias or look-ahead bias.

```text
find winners from the most recent one-year historical window
-> match 3-5 same-sector, similar-size failure controls per winner
-> split companies into label-visible discovery, label-hidden evolution validation, and locked test
-> append source documents with published_at and available_at to the Raw Info Store
-> run a frozen Signal Registry through adaptive, evidence-backed research trajectories
-> score two-stage blind predictions and collect Predictor self-reflection
-> archive complete Plan records S/E/J/R/U/T
-> select high-F1 but embedding-diverse Top-K parents plus random exploration parents
-> sample N new Information Plans from fixed proposer prior plus FIFO experimental meta-info
-> every bounded group of plan rounds, mine or repair candidate Signals on discovery data
-> execute candidate fixtures and validate schema, leakage, evidence traceability, and semantic uniqueness
-> durably record the validated batch, then automatically promote every passing exact hash as one recoverable Registry transition
-> start the next fast-loop group from the new Registry and the cumulative historical Plan Archive
```

“Bounded proposal engine” applies to each atomic development round: candidate
count, provider attempts, request scope, cost, and checkpoint commit are all
finite and auditable. A CLI supervisor may continuously start another bounded
round after the previous checkpoint commits, and may keep doing so until the
operator sends an interrupt. Continuous orchestration does not authorize an
unbounded request, spend, final-test loop, production promotion, or mutation of
the fixed exam. External execution still requires an explicit session scope
with fixed model/provider/routing, packet corpus, per-round limits, a cumulative
cost ledger, and fail-closed preflight validation for every newly rendered
request.

The operator launcher supervises retryable transport exits for a fixed
wall-clock window, defaulting to ten hours. It restarts the same exact
`run-loop` with bounded exponential backoff only after the dedicated temporary-
failure exit status. Every restart retains the frozen contract, exact response
cache, attempt/cost ledger, case checkpoints, and authoritative round/cycle
pointers. Interrupts, invalid model content, contract drift, exhausted budgets,
and all other deterministic failures remain terminal; this recovery window
does not widen any frozen execution or data boundary.

An external evolution run is identified by a secret-free frozen run contract:
dataset and split hash, initial stable Signal snapshot hash, global Raw Info oracle id,
fixed-prior hash, role/model and provider routing, exact code revision and Python
runtime, runtime limits, attempt limit, and cumulative cost ceiling. The current
full-market dataset path includes every identity-deduplicated issuer whose
security identity passes the normal-operating-common-stock gate and that has at
least one fixed-calendar case passing the case-level listing-date, price-window,
liquidity, and adjusted-price-integrity gates before the issuer-level split; it
does not impose a fixed issuer cap or outcome-enrich the rotating candidate pool. One
separate fixed Anchor split is removed by issuer before the remaining companies
are assigned to Discovery/Evolution Validation/Locked Test. Outcome balancing
belongs only to the Anchor and per-round Random evaluation snapshots. The
current contract evaluates every candidate on the same exact 24 cases: 16 fixed
Anchor cases with `7/5/3/1` label counts plus 8 round-randomized cases with
`3/2/2/1`, producing combined `10/7/5/2` counts. Anchor, Random, and Combined
metrics are all retained; the selection score is Combined Binary F1 recomputed
from the union confusion matrix, never an average of component F1s. There is no
Promotion or champion-rerun stage. Every external request is written and leakage-scanned before it is sent,
exact responses are keyed by the request hash, and every attempted call is
reserved in a durable ledger before network I/O. Restart may reuse an exact
response or an exact staged artifact, but it may not silently change the frozen
contract.

LLM authorization and source-data acquisition authorization are independent.
The latter freezes allowed providers, capabilities/source types, and per-cycle
and whole-run request ceilings. A disabled data boundary performs no network
I/O and records an `external_not_authorized` DataGap after a local miss.
Before Plan proposals, one label-free market-backbone readiness gate reuses or
materializes shared point-in-time evidence for the fixed Anchor and prospective
Random cases. Data adapters fall through in frozen provider order. Unavailable
prospective Random cases may be skipped before their snapshot is finalized,
but fixed Anchor cases and existing snapshots are never substituted. Shared
data failure is an orchestration pause, not Plan fitness or a permanent round
rejection.

Owned mainly by `cases`, `data`, `research`, `signals`, and `memory`.

Phase 1 contains two ordered subphases:

1. Information-plan research discovers what to collect, validates source
   coverage, extracts auditable atomic facts, derives candidate signals and
   research rubrics, and tests packet representations with a fixed plain LLM.
2. Analysis-method research begins only after the information plan passes its
   exit gate. It may then compare the plain-LLM baseline with multi-agent,
   specialist, debate, or skeptic architectures using the same fixed evidence.

The information-plan exit gate is not a claim of a universal optimum. It means
the best validated plan among the tested sources, context budgets, and plain-LLM
baseline has useful holdout separation, acceptable evidence fidelity, bounded
representation loss, and no competing tested proposal with a material,
repeatable improvement. The repository currently has no human-curated gold
packet, so a gold-packet upper bound must not be assumed in current experiments.

Information-scheme evolution changes only the four-part Information Plan:
Basic Info retrieval requests, initial-research skill, batch-reflection skill,
and final analysis prompt. `B` is an analyst's source-retrieval plan (for
example, read the latest eligible 10-K and retrieve company news from the prior
180 days), not a fixed profile schema. Company identifiers are fixed routing
inputs. The global append-only Raw Info Store is a point-in-time oracle outside
every evolution workspace and is not evolutionary state: its growth does not
change plan identity, parent selection, archive ranking, or state pointers.
Evolution workspaces preserve only document references and resolution
trajectories. Both Basic Info and Signals use one local-first resolver; Basic
Info sends deterministic exact source spans to `H_init`, while Signals compute
derived results from complete source documents.
The stable Signal Registry is frozen throughout a group of fast-loop rounds.
Every committed Fast trajectory also contributes to a version-bound,
append-only Signal learning ledger. The ledger keeps the Plan's explicit
selection reason, the executed state, the realized outcome, and post-hoc
reflection attribution separate: selecting a Signal is evidence about routing,
not proof that the Signal caused the prediction. Multiple Plans may retain
their distinct reasons for the same case/input, while effectiveness summaries
deduplicate that observation. A bounded, identity-free learned profile is
frozen beside the definitions and may guide later Signal selection; the full
ledger never enters blind model context.
At its Slow-Loop boundary, a durably staged and fully validated candidate batch
may advance it exactly once; the cycle marker records both input and output
Registry version/hash. A restart completes that same transition idempotently
before advancing the cycle pointer. The next group uses the output snapshot.
An explicitly frozen `slow_bootstrap` cycle is allowed only to break the
cold-start dependency in which a rejected Fast diagnostic needs a Signal that
does not yet exist. It has zero committed Fast rounds and reads an immutable
manifest derived from rejected-round trajectories: only label-hidden
`no_signal_match` information needs survive, issuer aliases are masked, and
source contract/rejection hashes plus the exact input Registry are bound. The
rejected Fast round remains outside history and parent selection. Bootstrap
uses the unchanged H1/H2/H3, candidate executor, paired effectiveness gate,
atomic transition, and Locked-Test boundary, then exposes any committed Registry
output only to a fresh subsequent Fast run.

`slow_only` is a separate v8 execution mode for a finite sequence of Signal
development cycles with zero Fast rounds. It never resets or reuses the
single-cycle bootstrap exception. A frozen, committed-only history manifest
may initialize the new workspace from one source workspace while preserving
source namespaces, exact Signal versions, source hashes, and source Fast/Slow
cutoffs. The new workspace keeps its Fast pointer at zero. Its contract fixes a
positive cumulative `max_slow_cycles`, a per-cycle minimum-new-Signal target,
and bounded reflection, Mining, Update, semantic-review, attempt, token, and
cost limits. Repeated CLI resumes cannot exceed those cumulative limits. The
same committed-only history manifest may also initialize a `fast_then_slow`
successor (dual-loop continuation) under the identical import and continuity
rules, with positive Fast-round targets; `slow_only` alone keeps the Fast
pointer frozen at zero.

Every Slow cycle freezes one neutral issuer-disjoint development/check sample
before any outcome-aware author role runs. Selection is a stable hash ordering
over an outcome-independent eligible population; evidence gaps stay attached
to the original case and never cause favorable resampling. E1 remains
outcome-hidden. H1, H3, E2, Update, and the entry reflection receive only their
role-scoped projections. Current check and confirmation sources, plus historical
episodes whose source closure would reveal them, are denied by the common Slow
source resolver. Confirmation remains a separately reserved, issuer-disjoint
offline evaluation boundary and never participates in candidate authoring or
promotion.

The Slow mining middle is being replaced under a gated plan: a controlled
label-aware mining controller over one shared, lazy, point-in-time Evidence
Graph is specified in `signal_mining_agent.md` and becomes the production path
only after zero-call replay, a controlled candidate closed loop, and one live
shadow cycle accept on identical frozen inputs. Until then H1/H2/H3 and E1/E2
remain authoritative and act as the read-only contrast baseline. Both paths
deliver candidates into the same fixture, holdout, paired-effectiveness, and
atomic-promotion gates; neither path may weaken them for yield. The
controller's runtime-owned mining ledger is additional reflection feedback
and never alters frozen samples or historical validation results.

The authoritative Slow dependency chain is `slow_input -> slow_memory ->
slow_experiments -> SlowLoopValidation -> Registry transition -> SlowLoopResult
-> cycle pointer`. The first three artifacts are immutable and hash-linked.
`slow_input` snapshots committed feedback facts and the sample manifest;
`slow_memory` appends episode reflections and evidence-linked method lessons
without rewriting raw facts or prior lessons; `slow_experiments` preserves all
search, no-candidate, technical-failure, validation, and update attempts. A
resume reuses the same frozen artifacts and candidate hashes. The cycle pointer
advances last, and only pointer-reachable artifacts become history for a later
cycle.

Each committed result reports new candidates, fully validated new Signal ids,
actually promoted new Signal ids, updated Signal versions, and
`signal_goal_status`. The status is `met` only when the configured number of new
Signal ids passed every contract, semantic, uniqueness, and effectiveness gate,
were atomically promoted, and the cycle committed. An update, draft,
provisional candidate, validation-only success, or renamed duplicate never
satisfies that target. Bounded honest failure is committed as `unmet`; it does
not lower a quality gate or authorize unbounded retry.
Signal Update is locally triggered only when repeated ledger evidence identifies
an actionable exact version. One Slow cycle selects at most three distinct
targets by evidence priority. Local code independently selects issuer-disjoint
induction and holdout cases for each target, exposes only that target's induction
evidence to one bounded semantic update call, and keeps contract, fixture, and
paired holdout decisions outside the model. One target's deferral or failure does
not block the other targets. No actionable target means no Signal-Update model
call.
The Plan Archive remains cumulative across these transitions: old Plans keep
their original Binary F1 and are neither rerun nor normalized against the new
Registry. Parent selection compares all eligible historical records by stored
Binary F1 plus the fixed diversity rule. Registry identity remains provenance
for the round that produced a score and never enters the score itself.

A separate confirmation evaluator may consume immutable completed artifacts to
measure whether evolution produced downstream benefit. It never participates in
candidate promotion or Plan Archive ordering. Its frozen protocol compares the
four combinations of baseline/candidate Plan and baseline/candidate Registry on
the same issuer-disjoint cases, point-in-time corpus, model configuration, and
budget identity. Contract validity, Signal extraction accuracy, Signal/outcome
association, and system-level prediction benefit remain separate report sections.
Sample size, minimum benefit, tolerated regression, repeat count, uncertainty,
experiment-look limits, and independent candidate-Signal measurement criteria
have no production defaults: they must be explicit in the reviewed protocol
before execution. A changed Registry cannot pass confirmation without
independent Signal fixtures. Confirmation cases are reserved once in an
append-only usage ledger and never returned to proposer or critic context.
At the creation of a separate new workspace, the runtime may additionally
build one deterministic cross-workspace historical Plan Seed Pool. It scans
only records reachable from each source workspace's authoritative completed-
round pointer, admits at most one quality Plan per independent source run
family, and freezes at most two source-diverse, embedding-diverse Plan
definitions plus their aggregate evaluation provenance. The Seed Pool is an
immutable parent-input snapshot bound into the new run contract, not imported
Plan Archive history: historical F1 selects seeds but is never represented as
fitness earned in the new workspace. Current committed Top-K Plans take
precedence and progressively replace warm-start seeds. If no compatible
committed source run exists, the Seed Pool is validly empty and the manual Plan
remains the cold-start fallback.
Reflection receives a deterministic anonymous comparison for every actual
parent of a new Plan. The comparison contains the parent Plan definition,
aggregate Anchor/Random/Combined metrics when available, a structured
parent-to-child Plan diff, and an exact-evaluation-snapshot comparability bit.
Only an exactly shared snapshot may produce confusion/precision/recall/F1
deltas; otherwise historical metrics remain contextual provenance. This
comparison is reflection evidence only: it is unavailable to blind prediction,
contains no case identities or per-case labels, and cannot change fitness,
Top-K, or the immutable historical Seed Pool.
Each committed round contributes one additive FIFO meta-info entry. The entry
retains, in order, every anonymous Predictor post-hoc case reflection, the exact
Plan-critic reflection plus its deterministic parent-comparison evidence, and
the Round reflector's horizontal comparison across the newly sampled Plans.
Later layers append insight; they never summarize over, rewrite, or replace an
earlier layer. The proposer may receive this retrospective outcome-aware entry
only after the corresponding round commits. It contains no company/case
identity, Raw Info, literal source evidence, or research context, and it is
never available to blind Plan execution or prediction. Meta-info remains one
fixed-length FIFO list: appending a completed round evicts only the oldest whole
entry when capacity is exceeded.
The complete archive and the model's working view are distinct contracts. As
approved on 2026-09-28, new case, Plan and Round reflections produce individually
addressable items: each carries complete content and an actionable brief from
the same generation, applicability, limitations, and exact supporting/opposing
source references. Runtime owns identifiers and canonical outcome facts. A
higher layer selects existing items unchanged or adds a sourced cross-case
insight; selection never deletes the original archive. Citation existence proves
provenance, not semantic truth or research benefit. Hypotheses remain hypotheses.
The proposer initially receives a byte-bounded selection of complete briefs,
coverage/deferred counts and lookup handles. It may request bounded reads of
registered anonymous original case/reflection units before proposing a Plan.
This replaces mandatory full-history replay, not full-history preservation.
Reads cannot access arbitrary files, identities, Raw Info, blind execution,
held-out labels or uncommitted rounds. Historical unstructured items remain
readable as explicitly unreviewed history; they are never silently upgraded to
validated lessons. One original case repeated across levels is one evidence
source, and important exceptions and counterexamples remain retrievable.

Research state bookkeeping is runtime-owned. H_reflect proposes ordered,
snapshot-bound changes instead of rewriting the complete ResearchState. Runtime
merges them, preserves untouched content, and checks the complete transition
before it becomes accepted state. Related evidence/claim/need changes form one
consistent validation unit. Corrections change only machine-authorized invalid
paths and necessary dependencies; safe progress is retained between attempts.
Normal instructions, parsers and repair permissions must express the same
contract. Missing instructions or contradictory producer/consumer contracts are
engineering failures, not research lessons or evidence of model incapacity.
Labels, dataset ownership, two-stage prediction semantics, metrics, runtime
guardrails, and fixed priors `H_R/H_P/H_E/H_U` are framework controls and
cannot be mutated by a candidate plan. Stage 1 predicts whether
the future fixed horizon reaches at least 2x through a fixed four-way
opportunity judgment. `likely` and `possible` map to the canonical positive
prediction; `unlikely` and `insufficient_information` map to negative. A
positive judgment means that the anonymous evidence supports an opportunity
candidate for the exact adjusted-share-price outcome; it does not require the
model to estimate more than 50% event probability. Stage 2 is evaluated only
for the positive ground-truth population and uses `2-3x`, `3-10x`, and `10x+`
classes. Binary F1 remains the primary Plan-selection fitness objective;
magnitude macro-F1 over the true-surge classes is the confirmed secondary
ordering, applied only among eligible candidates whose Binary F1 is equal
(compared as exact rationals of the confusion counts, never as floats), with
the stable plan id as the final deterministic tie-break. Records that
authentically lack the secondary metric never fill zero; the frozen
compatibility rule is that such records skip the secondary comparison and keep
their prior relative order. Precision, recall, magnitude accuracy, per-class
magnitude diagnostics, qualitative confidence, and the four-way judgment remain
diagnostics and reflection evidence only.

The durable blind prediction preserves both the original four-way judgment and
its deterministic binary projection. These two fields must agree; persistence
rejects any mismatch rather than guessing which value is authoritative. Only
the binary projection controls Stage-2 gating and enters the confusion matrix.
After truth reveal, the framework derives one deterministic
`candidate_judgment_feedback` record from the saved four-way judgment and the
binary truth. It distinguishes strong correct calls, conservative-but-binary-
correct calls, evidence-coverage gaps, false positives, and false negatives.
This outcome-aware record is supplied to Predictor self-reflection and the Plan
critic, but it is never a score, ordinal penalty, probability-calibration claim,
or Top-K input. In particular, one realized outcome cannot prove that `likely`
was the calibrated ex-ante category; it can only identify what evidence the
reflection should inspect. Alongside — never inside — that record, the
framework derives a deterministic per-case `magnitude_feedback` block from the
saved prediction and revealed truth (applicability, predicted and true class,
correctness, error kind, ordinal distance). It is diagnostic reflection
evidence with the same non-score status, and its field set is an additive
contract: legacy artifacts without the block remain valid and loadable.

After truth reveal, prediction correctness is computed by the framework from
the immutable saved prediction and deterministic truth. A reflection model may
explain that result but may not author or contradict the correctness bit.

Every prediction is durably handed to a prediction sink before the ground-truth
provider can be called. The Predictor receives the label only afterward for
post-hoc self-reflection. Discovery labels may be read by Signal Mining; the
evolution-validation label is inaccessible to plan execution; locked-test
records are absent from ordinary evolution calls. Plan rounds are finite and
advance one authoritative atomic `last_completed_round` pointer only after
plan records, trajectories, metrics, reflections, archive state, and round
meta-info have committed. A candidate that lacks 20 valid evidence-backed
predictions, predicts no positives, or has no true positive remains a diagnostic
experiment and cannot enter parent selection. A round with no fitness-eligible
candidate persists a rejection checkpoint and pauses without advancing either
the round or cycle pointer. Its pre-label `no_signal_match` needs may enter only
the explicit, immutable, identity-masked Slow-bootstrap manifest described
above; no prediction, truth, reflection, metric, or Plan fitness crosses that
boundary. Each repeated issuer/as-of observation has its own
stable `case_id`; company identity is never used as a case or prediction-file
key. Files beyond the pointer are staged recovery inputs, not completed history;
restart reuses them only when their canonical content exactly matches the
intended artifact under the same frozen run contract.

### Phase 2: Current Market Scan

Purpose: find live candidates cheaply before spending LLM work, starting from themes and industry-chain segments rather than isolated tickers.

```text
theme and segment state
-> full listed-stock universe
-> structured coarse screen
-> liquidity, market cap, financial-quality, and extreme-risk filters
-> theme-aware and anomaly-aware candidate expansion
-> point-in-time candidate packets
-> LLM thesis / catalyst / contrary-evidence / narrative-migration research
-> structured Rocket Score and related component scores
```

Owned mainly by `scanner`, `themes`, `data`, `research`, `signals`, `scoring`, and `memory`.

### Phase 3: Cross-sectional Comparison

Purpose: turn single-name analysis into a prioritized watchlist.

```text
compare candidates within sectors and segments
-> compare expectation gaps
-> compare catalyst timing
-> compare valuation room and market confirmation
-> identify crowded, expensive, or narrative-trap candidates
-> review gate
-> Top 20 watchlist, research cards, validation contracts, and decision records
```

Owned mainly by `ranking`, `scoring`, `research`, `reports`, and `memory`.

### Phase 4: Continuous Monitoring and Review

Purpose: keep the system current without rerunning everything from scratch.

```text
daily monitor news, filings, prices, volume, analyst revisions, and theme events
-> update current universe state
-> rerun LLM research only when material new information appears
-> validate catalyst and earnings events against active validation contracts
-> weekly rank refresh
-> monthly outcome review
-> add new winners, failures, and stale-watchlist cases
-> calibrate signal weights and feed meta-learning
```

Owned mainly by `monitoring`, `memory`, `review`, `signals`, `cases`, `ranking`, and `meta_learning`.

## Module Map

Module specs live under `spec/src/stock_opportunity_agent/` and describe active design boundaries. The active tree stays at module level unless implementation has proved a child boundary. The data layer currently has child specs because source adapters, feature normalization, document retrieval, and point-in-time packet assembly are already separate implementation boundaries.

- [`artifacts.md`](src/stock_opportunity_agent/artifacts.md): shared canonical JSON hashing and crash-safe local artifact writes; it owns byte-level mechanics only, never domain schemas or lifecycle policy.
- [`models.md`](src/stock_opportunity_agent/models.md): shared domain objects and versioned records.
- [`config.md`](src/stock_opportunity_agent/config.md): universe, scoring, data-source, prompt, and run configuration.
- [`data.md`](src/stock_opportunity_agent/data.md): structured and unstructured data access with point-in-time snapshots.
  - [`data/sources.md`](src/stock_opportunity_agent/data/sources.md): provider adapters and capability-level source selection.
  - [`data/structured.md`](src/stock_opportunity_agent/data/structured.md): normalized, source-linked feature records.
  - [`data/documents.md`](src/stock_opportunity_agent/data/documents.md): source-linked document archive and retrieval.
  - [`data/point_in_time.md`](src/stock_opportunity_agent/data/point_in_time.md): as-of-safe research packet assembly.
- [`memory.md`](src/stock_opportunity_agent/memory.md): persistent local memory stores.
- [`themes.md`](src/stock_opportunity_agent/themes.md): theme discovery, industry-chain maps, and segment timing.
- [`cases.md`](src/stock_opportunity_agent/cases.md): historical winners, controls, failures, and blind analysis packets.
- [`signals.md`](src/stock_opportunity_agent/signals.md): signal definitions, applicability, and performance.
- [`scanner.md`](src/stock_opportunity_agent/scanner.md): universe filtering and non-LLM coarse screens.
- [`research.md`](src/stock_opportunity_agent/research.md): LLM research agents and structured thesis generation.
- [`scoring.md`](src/stock_opportunity_agent/scoring.md): Rocket Score, theme scores, risk penalties, and final opportunity scores.
- [`ranking.md`](src/stock_opportunity_agent/ranking.md): cross-sectional ranking within segments and across the market.
- [`monitoring.md`](src/stock_opportunity_agent/monitoring.md): catalyst monitoring and watchlist state transitions.
- [`review.md`](src/stock_opportunity_agent/review.md): outcome review, error labeling, and thesis validation.
- [`meta_learning.md`](src/stock_opportunity_agent/meta_learning.md): system-level learning, experiments, and change proposals.
- [`reports.md`](src/stock_opportunity_agent/reports.md): watchlists, company cards, reviews, and audit reports.
- [`orchestration.md`](src/stock_opportunity_agent/orchestration.md): daily, weekly, monthly, quarterly, and cold-start pipelines.

## Primary Data Contracts

The system revolves around a few durable records:

- `ResearchPacket`: point-in-time company, price, financial, valuation, news, filing, transcript, sector, theme, and memory context.
- `ThemeMap`: a theme, its industry-chain segments, bottlenecks, leading indicators, evidence, candidates, and risks.
- `Thesis`: a versioned claim with evidence, catalysts, disconfirming conditions, status, and review dates.
- `ValidationContract`: forward-looking facts that would validate, weaken, or break a thesis, with expected review windows and measurement sources.
- `SignalDefinition`: a measurable signal with applicability, positive examples, counterexamples, false-positive patterns, hindsight-risk notes, and performance.
- `ScoreCard`: component scores and final opportunity score.
- `WatchlistEntry`: ranked output with recommendation state, reason, active thesis, and validation contract reference when priority requires it.
- `DecisionRecord`: immutable record of what the system recommended and which versions produced it.
- `UniverseStateRecord`: current ticker state with last analysis date, latest score, active thesis summary, new information markers, and reanalysis need.
- `EarningsValidationReport`: event-time comparison between a thesis validation contract and an earnings release, filing, transcript, price reaction, and analyst revision response.
- `ReviewRecord`: outcome, thesis validation result, error label, and lesson after time has passed.
- `ExperimentRecord`: meta-learning proposal, test design, result, and approval state.

Concrete field names belong in `models.md` and implementation schemas.

## Recommendation State Machine

The canonical research states are:

```text
ignore
monitor
thesis_forming
high_priority_watchlist
action_candidate
thesis_validated
thesis_broken
archived
```

State changes are research-state changes, not trades. A ticker can move from `monitor` to `thesis_forming` when evidence accumulates, from `thesis_forming` to `high_priority_watchlist` only after research, scoring, and review-gate checks, and from `high_priority_watchlist` to `action_candidate` or `thesis_validated` only when material new evidence confirms the thesis. It moves to `thesis_broken` when the validation contract fails or contrary evidence dominates. Archived names may be reactivated only by material new events such as a new CEO, major order, industry-cycle reversal, spin-off, unusually strong earnings surprise, or abnormal price and volume confirmation.

No entry should reach `high_priority_watchlist` or `action_candidate` without a validation contract.

## Major Boundaries

### Spec vs Implementation Detail

Top-level specs define responsibilities, invariants, and module boundaries. They do not settle every research parameter. When implementation reaches a detail that has several valid choices and could change conclusions, the agent must ask the user before coding it and then update the relevant module spec with the chosen rule. Examples include control-group matching standards, winner labels, score thresholds, theme-stage boundaries, and experiment promotion criteria.

The architecture should not add a new active module, child spec, score, agent role, or memory type unless it buys a clearer boundary, auditability, or testability. Related concerns should stay inside the parent module until they need separate ownership.

### Recommendation vs Trading

This system can mark an opportunity as `action_candidate`, but it must not place orders, size positions, set leverage, or manage exits. A separate trading or portfolio system may consume watchlist output later.

The final watchlist should pass through a review gate that checks evidence, contrary evidence, catalyst timing, valuation stretch, and thesis-break conditions. Passing that gate means "worth human attention", not "buy". A validation contract means "we know what would prove or disprove the research claim", not "the system has permission to trade".

### Research vs Data

LLM research consumes prepared packets and retrieved documents. It should not become the data source of record. If a web or model search finds relevant facts, the facts should be stored with source metadata before influencing repeatable scoring.

The Signal Library declares data needs; it does not query providers directly.
One shared Raw Info resolver must translate each stable `SignalSpec` into a
point-in-time request, reuse or acquire authorized documents, and return the
exact lineage consumed by the Signal executor. A run must establish broad
Signal-input readiness before spending calls on Plan evaluation; repeatedly
turning a satisfiable request into `unavailable` is an interface failure, not a
valid error-handling strategy. Authorization, provider ceilings, and
point-in-time rules remain unchanged by readiness preparation.

### Memory vs Reports

Reports are human-readable artifacts. Memory is structured state used by future runs. A report without memory is not enough; a memory record without source links is not auditable.

### Meta-learning vs Self-modification

Meta-learning may propose changes, generate experiments, and recommend version upgrades. It must not silently overwrite prompts, scoring weights, schemas, or modules. The explicitly defined Slow-Loop Signal validator may automatically promote exact passing candidate hashes at a cycle boundary only after both executable contract validation and a fixed paired effectiveness gate. Changing that validator, its gates, datasets, priors, score semantics, or promotion policy remains a framework change; medium and high-risk framework changes require human approval.

## Scoring Shape

The final opportunity score should combine:

```text
Final Opportunity Score =
Theme Transmission Score
* Segment Timing Score
* Company Rocket Score
* risk adjustment
```

The Company Rocket Score should consider:

- fundamental inflection,
- earnings and revenue revisions,
- narrative migration,
- catalyst density,
- industry tailwind,
- market early confirmation,
- valuation room,
- and risk penalty.

The system should also preserve separate `upside_potential` and `launch_probability` because a large long-term opportunity and a likely 3-6 month launch are not the same thing.

## Cold-start Learning

Cold-start should not begin with live recommendations. It should build a case library:

- define winners programmatically,
- match controls by sector, size, volatility, valuation, prior performance, and market environment,
- create point-in-time packets,
- run blind LLM analysis,
- compare winner ranking against controls,
- and convert stable differences into signal candidates.

## Incremental Operation

Once memory exists, reruns should be incremental:

- daily jobs update data and detect changes,
- current universe state records last analysis, latest score, new information, and whether a ticker needs fresh research,
- changed tickers or catalysts trigger selective research,
- weekly jobs refresh broad rankings,
- monthly jobs review outcomes,
- and quarterly jobs evaluate framework stability.

## Safety and Audit Invariants

- Never use future information in historical packets.
- Never store a recommendation without its evidence, versions, and as-of date.
- Never ask historical analysis to explain why a known future winner later surged; historical prompts must be framed as as-of-date blind analysis.
- Never let pure narrative override missing data, missing catalysts, or extreme valuation risk.
- Always preserve evidence against the thesis.
- Always keep failed recommendations and controls; do not curate only winners.
- Always include novelty and anomaly checks so the system does not only rediscover historical lookalikes.
- Always distinguish unavailable data from neutral data.
- Always separate "worth studying" from "worth buying".
