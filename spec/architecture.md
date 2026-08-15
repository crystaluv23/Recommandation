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
-> retain quality-diverse plans and compress completed-round lessons into FIFO meta-info
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

An external evolution run is identified by a secret-free frozen run contract:
dataset and split hash, initial stable Signal snapshot hash, global Raw Info oracle id,
fixed-prior hash, role/model and provider routing, exact code revision and Python
runtime, runtime limits, attempt limit, and cumulative cost ceiling. The current
full-market dataset path includes every identity-deduplicated issuer that passes
the fixed price-window, listing-date, and reviewed identity-decision gates before
the issuer-level Discovery/Evolution Validation/Locked Test split; it does not
impose a fixed issuer cap or outcome-enrich the candidate pool. The proposal
still requires historical identity and security-type review before approval.
Outcome balancing belongs only to the per-round evaluation snapshot. The current
contract evaluates every candidate on one shared, exact 20-case round snapshot
with fixed `8/6/4/2` label counts and no Anchor, Promotion, or champion-rerun
stage. Every external request is written and leakage-scanned before it is sent,
exact responses are keyed by the request hash, and every attempted call is
reserved in a durable ledger before network I/O. Restart may reuse an exact
response or an exact staged artifact, but it may not silently change the frozen
contract.

LLM authorization and source-data acquisition authorization are independent.
The latter freezes allowed providers, capabilities/source types, and per-cycle
and whole-run request ceilings. A disabled data boundary performs no network
I/O and records an `external_not_authorized` DataGap after a local miss.

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
At its Slow-Loop boundary, a durably staged and fully validated candidate batch
may advance it exactly once; the cycle marker records both input and output
Registry version/hash. A restart completes that same transition idempotently
before advancing the cycle pointer. The next group uses the output snapshot.
The Plan Archive remains cumulative across these transitions: old Plans keep
their original Binary F1 and are neither rerun nor normalized against the new
Registry. Parent selection compares all eligible historical records by stored
Binary F1 plus the fixed diversity rule. Registry identity remains provenance
for the round that produced a score and never enters the score itself.
Labels, dataset ownership, two-stage prediction semantics, metrics, runtime
guardrails, and fixed priors `H_R/H_P/H_E/H_U` are framework controls and
cannot be mutated by a candidate plan. Stage 1 predicts whether
the future fixed horizon reaches at least 2x. Stage 2 is evaluated only for the
positive ground-truth population and uses `2-3x`, `3-10x`, and `10x+` classes.
Binary F1 is the first fitness objective; precision, recall, magnitude accuracy,
and magnitude macro-F1 remain visible diagnostics.

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
the round or cycle pointer. Each repeated issuer/as-of observation has its own
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

### Memory vs Reports

Reports are human-readable artifacts. Memory is structured state used by future runs. A report without memory is not enough; a memory record without source links is not auditable.

### Meta-learning vs Self-modification

Meta-learning may propose changes, generate experiments, and recommend version upgrades. It must not silently overwrite prompts, scoring weights, schemas, or modules. The explicitly defined Slow-Loop Signal validator may automatically promote exact passing candidate hashes at a cycle boundary. Changing that validator, its gates, datasets, priors, score semantics, or promotion policy remains a framework change; medium and high-risk framework changes require human approval.

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
