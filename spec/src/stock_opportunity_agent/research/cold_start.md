# Research Cold Start

## Status
Started

## Purpose

Run blind as-of-date LLM analysis for historical cold-start cases without
revealing winner/control/failure labels or future returns.

## External Interface

The submodule exposes:

- `BlindCaseAnalysis`: structured JSON-compatible analysis output.
- `BlindCaseResearcher`: protocol for blind researchers.
- `HeuristicBlindCaseResearcher`: offline dry-run researcher for tests and
  pipeline validation.
- `OpenAIBlindCaseResearcher`: OpenAI-backed researcher using prepared
  `ResearchPacket` inputs.

## Invariants

- Prompts must include only packet data available as of the packet date.
- Prompts should mask ticker, company name, and source URLs by default.
- Prompts must explicitly forbid using future outcomes.
- LLM output must include contrary evidence and confidence, not only bullish
  signal language.
- LLM output is analysis evidence; it cannot mutate memory or signal versions
  directly.

## Testing

Tests should cover deterministic researcher behavior, JSON parsing, missing
field validation, and prompt construction that excludes outcome labels.
