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
-> build point-in-time case packets
-> run blind as-of-date research
-> initialize signal library, theme map, scoring defaults, prompts, and memory

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

Purpose: build the first signal library without survivorship bias or look-ahead bias.

```text
find 1-3 year winners
-> match 3-5 same-sector, similar-size failure controls per winner
-> construct T-180 / T-120 / T-90 / T-60 / T-30 point-in-time packets
-> run blind as-of-date LLM analysis
-> compare winners against controls and failures
-> update Signal Library, Theme Memory, prompt defaults, scoring hypotheses, and case memory
```

Owned mainly by `cases`, `data`, `research`, `signals`, and `memory`.

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

Meta-learning may propose changes, generate experiments, and recommend version upgrades. It must not silently overwrite prompts, scoring weights, schemas, or modules. Low-risk parameter changes may be automated only after the architecture explicitly allows them; medium and high-risk changes require human approval.

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
