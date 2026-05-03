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
- `OpenAIWebInflectionResearcher`: OpenAI Responses API researcher using the
  `web_search` tool.

## Invariants

- Web search is permitted only in retrospective inflection discovery.
- Output is used to choose or audit historical slice anchors, not to enrich
  blind research packets.
- The following blind analysis step must disable web search and hide
  winner/control labels.

## Testing

Tests should cover result serialization and ensure web-search tools are passed
only through the inflection researcher path.
