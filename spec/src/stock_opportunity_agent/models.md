# Models

## Status
Not started

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
- `Thesis`
- `SignalDefinition`
- `ScoreCard`
- `WatchlistEntry`
- `DecisionRecord`
- `ReviewRecord`
- `ExperimentRecord`
- `VersionStamp`

Implementation may use dataclasses, Pydantic models, or typed dictionaries, but records crossing module boundaries must be explicit and serializable.

## Responsibilities

- Define canonical field names and status enums.
- Distinguish missing, stale, estimated, and confirmed data.
- Carry `as_of_date`, source metadata, and version fields where relevant.
- Keep recommendation states separate from trading states.
- Provide validation for score ranges, dates, identifiers, and required evidence.

## Dependencies

- May use standard library typing and validation helpers.
- Must not depend on vendor data clients, LLM providers, database drivers, or pipeline runners.

## Invariants

- Every research, score, decision, and review record must be tied to an `as_of_date`.
- Every LLM-generated claim that affects a thesis must be attachable to evidence or explicitly marked as inference.
- Score models must preserve component scores; only storing a final score is not enough.
- Versioned records must include prompt, scoring, signal, model, and data-pipeline versions when those versions affect output.

## Testing

Unit tests should cover serialization, deserialization, status enums, required fields, score bounds, date handling, and validation errors for ambiguous records.
