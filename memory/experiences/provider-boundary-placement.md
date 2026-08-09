# Provider Boundary Placement

visit_times: 7

## Trigger

Read this before adding a provider, adapter, registry, plugin-like extension point, or external-service integration.

## Lesson

Place reusable provider registries at the capability boundary instead of inside the first consumer module. A provider that may be shared by research, data, scoring, review, or orchestration should not live under one consumer's namespace merely because that consumer needs it first.

## Context

The first OpenAI adapter was implemented under `stock_opportunity_agent.research.models` because LLM output initially serves the research module. The user pointed out that a directory named `research` is misleading for a general model interface. The provider registry was moved to top-level `stock_opportunity_agent.llm`, leaving `research` for higher-level research agents.

## How to Apply

Before creating a new registry, ask whether the thing being registered is a capability provider or a module-specific helper. If it is a reusable provider, prefer a top-level capability namespace such as `llm` or `data_sources`; if it is truly private to one module, keep it inside that module.

## Limits

Do not create top-level namespaces for ordinary single-use helpers. A registry earns its own boundary when future providers are plausible and at least two modules could reasonably depend on the same capability.
