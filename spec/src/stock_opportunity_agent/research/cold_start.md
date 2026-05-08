# Research Cold Start

## Status
Started

## Purpose

Run blind as-of-date LLM analysis for historical cold-start cases without
revealing winner/control/failure labels, ticker/company identity, or future
returns. The LLM's job is to judge whether the anonymous as-of packet looks like
a potential 3-6 month surge candidate and which pre-surge signals or contrary
evidence are visible.

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
- Prompts should mask ticker, company name, packet ids, source ids, source URLs,
  and direct identity strings inside evidence summaries by default.
- Prompts must explicitly forbid using future outcomes.
- Prompts must not include web-search tools; web search is allowed only in the
  separate retrospective inflection-discovery setup step.
- LLM output must include contrary evidence and confidence, not only bullish
  signal language.
- LLM output must include `surge_candidate` and `surge_candidate_reason` so the
  cold-start artifact records the actual blind judgment, not just a list of
  signals.
- LLM output is analysis evidence; it cannot mutate memory or signal versions
  directly.

## Testing

Tests should cover deterministic researcher behavior, JSON parsing, missing
field validation, and prompt construction that excludes outcome labels.
