# Architecture

## Status
Done

## Architectural Shape

The future source package should be `stock_opportunity_agent`. The design is a local-first research system with explicit boundaries between data, memory, LLM research, scoring, review, and meta-learning.

The system should optimize for auditability and iteration before scale. Local SQLite, DuckDB, Parquet, and file-based reports are good defaults for early versions. Vendor data sources, vector stores, and model providers should sit behind adapters.

## Layered Flow

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

The normal production loop is:

```text
daily update
-> detect changed themes, segments, tickers, and catalysts
-> rerun research only where needed
-> persist decisions and observations

weekly scan
-> coarse market screen
-> theme and segment scoring
-> company research packets
-> LLM research
-> scoring and ranking
-> Top watchlist report
-> decision memory

monthly review
-> outcome tracking
-> error labeling
-> signal attribution
-> meta-learning hypotheses

quarterly evaluation
-> walk-forward tests
-> version comparison
-> framework changes for human approval
```

## Module Map

Module specs live under `spec/src/stock_opportunity_agent/` and mirror the intended future source tree. A package-level spec such as `data.md` describes the full `src/stock_opportunity_agent/data/` package; child specs under `data/` describe submodules such as `point_in_time.py`.

- [`models.md`](src/stock_opportunity_agent/models.md): shared domain objects and versioned records.
- [`config.md`](src/stock_opportunity_agent/config.md): universe, scoring, data-source, prompt, and run configuration.
- [`data.md`](src/stock_opportunity_agent/data.md): structured and unstructured data access with point-in-time snapshots.
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
- `SignalDefinition`: a measurable signal with applicability, false-positive patterns, and performance.
- `ScoreCard`: component scores and final opportunity score.
- `WatchlistEntry`: ranked output with recommendation state and reason.
- `DecisionRecord`: immutable record of what the system recommended and which versions produced it.
- `ReviewRecord`: outcome, error label, and lesson after time has passed.
- `ExperimentRecord`: meta-learning proposal, test design, result, and approval state.

Concrete field names belong in `models.md` and implementation schemas.

## Major Boundaries

### Spec vs Implementation Detail

Top-level specs define responsibilities, invariants, and module boundaries. They do not settle every research parameter. When implementation reaches a detail that has several valid choices and could change conclusions, the agent must ask the user before coding it and then update the relevant module spec with the chosen rule. Examples include control-group matching standards, winner labels, score thresholds, theme-stage boundaries, and experiment promotion criteria.

### Recommendation vs Trading

This system can mark an opportunity as `action_candidate`, but it must not place orders, size positions, set leverage, or manage exits. A separate trading or portfolio system may consume watchlist output later.

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
- changed tickers or catalysts trigger selective research,
- weekly jobs refresh broad rankings,
- monthly jobs review outcomes,
- and quarterly jobs evaluate framework stability.

## Safety and Audit Invariants

- Never use future information in historical packets.
- Never store a recommendation without its evidence, versions, and as-of date.
- Never let pure narrative override missing data, missing catalysts, or extreme valuation risk.
- Always preserve evidence against the thesis.
- Always keep failed recommendations and controls; do not curate only winners.
- Always distinguish unavailable data from neutral data.
- Always separate "worth studying" from "worth buying".
