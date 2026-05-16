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

Initial implementation provides a lightweight LLM provider registry under
`src/stock_opportunity_agent/llm/`. Provider modules register factories with
`@register("provider_name")`; concrete providers include an OpenAI Responses API
adapter and an OpenRouter Responses API adapter. The OpenRouter adapter keeps
provider-specific web-search compatibility separate from the OpenAI adapter.
Domain records remain in the top-level `models` module, and `research` is
reserved for higher-level agents that consume prepared packets.

Active child specs:

- [`research/cold_start.md`](research/cold_start.md): blind as-of-date LLM
  analysis for historical cold-start cases.
- [`research/inflection_discovery.md`](research/inflection_discovery.md):
  web-enabled retrospective inflection discovery before blind analysis.
- [`research/evidence_acquisition.md`](research/evidence_acquisition.md):
  pre-packet company, catalyst, theme, and public research evidence acquisition
  plus context coverage gating for formal cold start.
- [`research/playbooks.md`](research/playbooks.md): retrospective cross-case
  synthesis of reusable surge-research thinking patterns and prompt playbooks.

## Responsibilities

- Consume fixed `ResearchPacket` inputs.
- Collect source-linked pre-packet context when a pipeline explicitly invokes a
  retrieval phase before building fixed `ResearchPacket` inputs.
- Ask for additional retrieval only in identity-visible setup or live research
  stages; blind historical assessment must consume the prepared packet as given.
- Produce JSON-serializable, schema-validated outputs.
- Separate direct evidence from inference.
- Preserve prompt and model versions.
- Synthesize candidate research playbooks from historical cases without directly
  rewriting prompt defaults.
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
- Web search may enrich pre-packet context and retrospective inflection setup,
  but blind cold-start assessment remains web-disabled and anonymous.
- A high-priority recommendation requires structured evidence, catalysts, disconfirming conditions, and a validation contract.
- Incremental research must compare new evidence to the prior thesis instead of silently generating a fresh thesis from scratch.

## Testing

Tests should cover prompt assembly, schema validation, missing evidence
behavior, deterministic fixtures, version stamping, validation-contract
presence, incremental research behavior, coverage-gate behavior, web/no-web role
boundaries, and refusal to accept ungrounded high-confidence claims.
