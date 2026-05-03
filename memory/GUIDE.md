# Memory Guide

Do not read memory at session start. Use this guide only when prior project experience might apply, or when starting work on a specific module and doing the required quick trigger-map scan.

## Trigger Map

| Trigger | Experience | visit_times | Notes |
| --- | --- | ---: | --- |
| Adding provider, adapter, registry, or plugin-like extension point | [`experiences/provider-boundary-placement.md`](experiences/provider-boundary-placement.md) | 1 | Avoid coupling reusable providers to the first consumer module. |
| Running Python tests, scripts, seed pipelines, or validation commands | [`experiences/python-runtime-for-tests.md`](experiences/python-runtime-for-tests.md) | 1 | Use the project-compatible Python 3.11+ runtime instead of system Python. |

## Experience Index

- [`experiences/provider-boundary-placement.md`](experiences/provider-boundary-placement.md): reusable provider registries should live at the capability boundary, not inside the first module that consumes them.
- [`experiences/python-runtime-for-tests.md`](experiences/python-runtime-for-tests.md): test and script commands should use the bundled Python 3.11+ runtime because system Python may be 3.9.

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
