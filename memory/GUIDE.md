# Memory Guide

Do not read memory at session start. Use this guide only when prior project experience might apply, or when starting work on a specific module and doing the required quick trigger-map scan.

## Trigger Map

| Trigger | Experience | visit_times | Notes |
| --- | --- | ---: | --- |
| Adding provider, adapter, registry, or plugin-like extension point | [`experiences/provider-boundary-placement.md`](experiences/provider-boundary-placement.md) | 1 | Avoid coupling reusable providers to the first consumer module. |
| Running or changing formal cold start, blind LLM prompts, OpenRouter cold-start calls, or seed/formal entry points | [`experiences/formal-cold-start-blind-boundaries.md`](experiences/formal-cold-start-blind-boundaries.md) | 18 | Restate the execution contract, packet contents, anonymity boundary, and web-search boundary before using existing scaffolding. |
| Running Python tests, project scripts, formal cold-start pipelines, or validation commands | [`experiences/python-runtime-for-tests.md`](experiences/python-runtime-for-tests.md) | 20 | Use the project-compatible Python 3.11+ runtime instead of system Python. |
| Comparing paired blind-LLM information plans or interpreting small confidence deltas | [`experiences/paired-llm-comparison-noise.md`](experiences/paired-llm-comparison-noise.md) | 0 | Reuse responses for identical packet hashes and separate model sampling noise from information lift. |

## Experience Index

- [`experiences/provider-boundary-placement.md`](experiences/provider-boundary-placement.md): reusable provider registries should live at the capability boundary, not inside the first module that consumes them.
- [`experiences/formal-cold-start-blind-boundaries.md`](experiences/formal-cold-start-blind-boundaries.md): formal cold-start work must verify the single entry point, actual packet contents, blind anonymity boundary, web-search boundary, and explicit surge-candidate judgment schema before execution.
- [`experiences/python-runtime-for-tests.md`](experiences/python-runtime-for-tests.md): test and script commands should use the bundled Python 3.11+ runtime because system Python may be 3.9.
- [`experiences/paired-llm-comparison-noise.md`](experiences/paired-llm-comparison-noise.md): paired information-plan runs must reuse identical-packet responses and avoid treating small single-call confidence movement as evidence.

## Consultation Protocol

1. Scan the Trigger Map for a matching situation.
2. If a relevant entry exists, read only that experience file.
3. Increment that experience's `visit_times` because it was consulted mid-session.
4. Add a line to `memory/meta/usage_log.md` with the date, trigger, experience path, and why it was used.
5. Apply the lesson only if it still fits the current specs and code.

Do not increment `visit_times` when creating a new experience at session end. The counter tracks mid-session read-consultations only.

## Experience Template

```markdown
# <Experience Title>

visit_times: 0

## Trigger
When should an agent read this?

## Lesson
What was learned?

## Context
What happened, and where?

## How to Apply
What should future agents do differently?

## Limits
When does this lesson not apply?
```

## Session-end Memory Rule

Create a new experience only when something non-obvious was learned that is likely to matter later. Routine implementation details, obvious bug fixes, and one-off preferences do not need memory entries.
