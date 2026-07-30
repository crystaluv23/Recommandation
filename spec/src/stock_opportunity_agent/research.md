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
provider-specific web-search compatibility separate from the OpenAI adapter,
and optionally fixes an allowed provider slug, disables fallbacks, and requires
support for every requested parameter. The shared HTTP transport applies
bounded exponential backoff to retryable transport, rate-limit, and server
failures.
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
- [`research/ralph_loop.md`](research/ralph_loop.md): retrospective
  label-aware research-information-plan discovery, acquisition/extraction
  diagnosis, packet-scheme proposal, and blind plain-LLM validation for formal
  cold-start packets.
- [`research/information_plan.md`](research/information_plan.md): broad
  information requirements, source coverage, atomic evidence, raw-versus-
  organized comparison, family experiments, and layered failure attribution
  coordinated by Ralph before analysis-method experiments.
- [`research/scheme_evolution.md`](research/scheme_evolution.md): bounded
  proposal search over versioned information-scheme genomes while label, split,
  evaluation, packet, and analyzer contracts remain fixed.
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
- Propose cold-start information schemes through Ralph Loop without promoting
  them into production prompt defaults.
- Keep information requirements, atomic evidence, signals, analysis rubrics,
  packet rendering, and prompt wording as distinct research products. A request
  to collect actual order evidence is not itself a signal; a signal requires a
  measurable or explicitly qualitative definition over source-linked facts.
- Preserve the full source archive and provenance while allowing the final LLM
  packet to be intentionally compressed. Every packet claim must remain
  traceable to atomic evidence and its point-in-time source.
- Compare raw-source and organized-packet variants only when they use the same
  source bundle, as-of cutoff, model, output contract, and documented context
  budget. Derived cross-sectional data used by a signal counts as additional
  input information and must not be hidden inside only one comparison arm.
- Materialize each candidate genome with discovery labels from one fold only;
  freeze the result before building anonymous admission inputs, persist all
  predictions before deterministic scoring, and keep sealed-test records
  outside the evolution engine.
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
- Retrospective Ralph diagnostics may read historical outcome groups only in
  explicitly marked label-aware artifacts; scheme-built blind packets must stay
  anonymous and point-in-time.
- Blind feedback must be attributed to one of: source unavailable, acquisition
  miss, extraction error, signal error, representation loss, analysis error, or
  outcome not predictably supported by available as-of evidence. Feedback may
  refine a development set, but an independent claim requires a new untouched
  company holdout.
- Current experiments do not have a human-curated gold packet. Automatically
  generated reference packets, source audits, or limited fact checks must not be
  described as gold or used to claim that an information plan is globally
  optimal.
- Multi-agent analysis is a later analysis-method experiment. It must use a
  fixed validated information plan so gains are not confounded with better data
  acquisition or representation.
- A high-priority recommendation requires structured evidence, catalysts, disconfirming conditions, and a validation contract.
- Incremental research must compare new evidence to the prior thesis instead of silently generating a fresh thesis from scratch.

## Testing

Tests should cover prompt assembly, schema validation, missing evidence
behavior, deterministic fixtures, version stamping, validation-contract
presence, incremental research behavior, coverage-gate behavior, web/no-web role
boundaries, and refusal to accept ungrounded high-confidence claims.
