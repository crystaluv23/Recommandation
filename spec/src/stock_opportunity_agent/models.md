# Models

## Status
Started

## Purpose

Own the shared domain records used across the system. These records make LLM outputs, data packets, scores, decisions, reviews, and experiments auditable and versionable.

## External Interface

Other modules may depend on stable model types such as:

- `TickerRef`
- `AsOfContext`
- `EvidenceItem`
- `Catalyst`
- `ResearchPacket`
- `ThemeMap`
- `SegmentAssessment`
- `CompanyProfile`
- `FeatureRecord`
- `Thesis`
- `ValidationContract`
- `SignalDefinition`
- `ScoreCard`
- `WatchlistEntry`
- `DecisionRecord`
- `UniverseStateRecord`
- `EarningsValidationReport`
- `ReviewRecord`
- `ExperimentRecord`
- `VersionStamp`

Implementation may use dataclasses, Pydantic models, or typed dictionaries, but records crossing module boundaries must be explicit and serializable.

Initial implementation uses standard-library dataclasses and enums in `src/stock_opportunity_agent/models.py`. `FeatureRecord` is the cross-module structured data contract used by the data layer and later scanner/scoring modules. These are domain records, not LLM provider adapters; model-provider API integrations belong under the research module.

`EvidenceKind` includes source categories for filings, transcripts, news,
public research-report summaries, theme-context summaries, price/volume,
financials, valuation, memory, and inference. The research-report and
theme-context kinds are evidence provenance labels, not permission to persist
full public reports or article bodies.

`ThemeMap` and `SegmentAssessment` carry the initial industry-chain map contract:
stage scale version, segment transmission stage, timing/transmission scores,
candidate symbols, leading indicators, validation state, risks, and crowdedness
flags.

## Responsibilities

- Define canonical field names and status enums.
- Distinguish missing, stale, estimated, and confirmed data.
- Carry `as_of_date`, source metadata, and version fields where relevant.
- Represent structured data availability with feature values, source metadata, retrieval time, quality state, and explicit missing reasons.
- Represent current ticker state without confusing it with a recommendation or trade.
- Keep recommendation states separate from trading states.
- Represent validation contracts as first-class records linked to theses, watchlist entries, decisions, monitoring events, and reviews.
- Represent event-time validation reports, especially earnings validation, without rewriting the original thesis or decision.
- Provide validation for score ranges, dates, identifiers, and required evidence.

## Dependencies

- May use standard library typing and validation helpers.
- Must not depend on vendor data clients, LLM providers, database drivers, or pipeline runners.

## Invariants

- Every research, score, decision, and review record must be tied to an `as_of_date`.
- Every LLM-generated claim that affects a thesis must be attachable to evidence or explicitly marked as inference.
- Score models must preserve component scores; only storing a final score is not enough.
- `ResearchPacket` records must include structured `FeatureRecord` values as well as evidence summaries, so downstream modules can score repeatably instead of parsing prose.
- A `WatchlistEntry` at `high_priority_watchlist` or `action_candidate` must reference a `ValidationContract`.
- A `ValidationContract` must distinguish validation metrics, disconfirming events, expected review windows, and measurement sources.
- Versioned records must include prompt, scoring, signal, model, and data-pipeline versions when those versions affect output.

## Testing

Unit tests should cover serialization, deserialization, status enums, required fields, score bounds, date handling, and validation errors for ambiguous records.
