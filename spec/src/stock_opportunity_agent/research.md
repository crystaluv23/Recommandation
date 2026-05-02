# Research

## Status
Started

## Purpose

Coordinate LLM-based stock and theme research. This module turns prepared packets and retrieved evidence into structured theses, risks, catalysts, and recommendation states.

## External Interface

Expected agent roles:

- Research Agent for bull/base thesis generation.
- Skeptic Agent for contrary evidence and thesis break conditions.
- Theme Agent for industry-chain transmission reasoning.
- Valuation Agent for valuation-stretch critique.
- Judge Agent for synthesis into a recommendation state.

Expected outputs:

- structured LLM research result,
- thesis draft,
- evidence for and against,
- catalysts,
- disconfirming events,
- validation contract draft,
- old and new narrative,
- and confidence notes.

Initial implementation provides a lightweight LLM provider registry under `src/stock_opportunity_agent/llm/`. Provider modules register factories with `@register("provider_name")`; the first concrete provider is an OpenAI Responses API adapter. Domain records remain in the top-level `models` module, and `research` is reserved for higher-level agents that consume prepared packets.

## Responsibilities

- Consume fixed `ResearchPacket` inputs.
- Ask for additional retrieval only when packet evidence is insufficient.
- Produce JSON-serializable, schema-validated outputs.
- Separate direct evidence from inference.
- Preserve prompt and model versions.
- Prefer monitor or ignore when evidence is weak.
- Support full research for new candidates and delta research for already-studied companies where the task is to judge whether new evidence changes the active thesis.
- Require a skeptic pass before a candidate can become high-priority, with explicit checks for narrative traps, missing financial validation, valuation stretch, crowded trades, and one-time items.
- Draft validation metrics and thesis-break conditions that monitoring and review can evaluate later.

## Dependencies

- Consumes models, config, data, memory, themes, signals, and scanner candidates.
- Feeds scoring, ranking, memory, monitoring, review, reports, and meta-learning.

## Invariants

- LLM output must include evidence against the thesis.
- The module must distinguish "interesting story" from "validated opportunity".
- The LLM cannot directly mutate memory, scoring weights, or config.
- A high-priority recommendation requires structured evidence, catalysts, disconfirming conditions, and a validation contract.
- Incremental research must compare new evidence to the prior thesis instead of silently generating a fresh thesis from scratch.

## Testing

Tests should cover prompt assembly, schema validation, missing evidence behavior, deterministic fixtures, version stamping, validation-contract presence, incremental research behavior, and refusal to accept ungrounded high-confidence claims.
