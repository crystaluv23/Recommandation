# Research Inflection Discovery

## Status
Started

## Purpose

Use LLM research with web search enabled to identify public narrative, earnings,
order, analyst, and industry-chain events that likely marked a historical surge
inflection.

## External Interface

The submodule exposes:

- `InflectionResearchResult`: JSON-compatible inflection candidates for one
  case.
- `FactorInflectionResearcher`: price/volume factor researcher using historical
  bars.
- `HeuristicInflectionResearcher`: offline fallback for tests and dry runs.
- `CompositeInflectionResearcher`: combines factor and LLM/web candidates.
- `CachedInflectionResearcher`: wraps expensive retrospective researchers and
  reuses results for cases with the same symbol and outcome window.
- `OpenAIWebInflectionResearcher`: OpenAI Responses API researcher using the
  `web_search` tool.

## Invariants

- Web search is permitted only in retrospective inflection discovery.
- Composite discovery may keep factor-based candidates when a supplemental
  web-search researcher fails, but the failure must remain visible in raw output.
- Web-enabled retrospective discovery must not be repeated for every T-slice of
  the same symbol/outcome window; cache or group those calls before spending LLM
  budget.
- Output is used to choose or audit historical slice anchors, not to enrich
  blind research packets.
- The following blind analysis step must disable web search and hide
  winner/control labels.

## Testing

Tests should cover result serialization and ensure web-search tools are passed
only through the inflection researcher path.
