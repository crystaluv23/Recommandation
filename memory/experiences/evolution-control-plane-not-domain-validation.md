# Evolution Control Flow Is Not Domain Validation

visit_times: 0

## Trigger

Read this before adding authorization, budget, approval, retry, pause, or
operator-readiness errors inside evolution role adapters, Generic Agent tools,
candidate evaluation, or Slow-loop validation.

## Lesson

Exceptions that mean "the orchestrator cannot currently execute" must not be
subclasses of the domain `ValidationError` used for repairable model content.
The bounded role and tool loops intentionally catch domain validation so the
model can correct malformed JSON or tool arguments. If an API-key, approval, or
budget exception shares that type, it can be swallowed as candidate feedback
and later misreported as a bad Plan, rejected round, or zero-quality result.

## Context

The Information-Plan v3 audit found that missing external readiness and durable
attempt/cost exhaustion were raised as `ValidationError` inside boundaries that
catch that error for one-shot model correction. The correct behavior is a
dedicated control-flow exception that propagates to the CLI, records a
structured pause, leaves committed pointers unchanged, and performs no request
reservation when readiness is absent.

## How to Apply

Use separate exception families for orchestration control flow and domain
validation. Catch control-flow exceptions only at the run/cycle supervisor.
Regression-test that they cross Fast evaluators, Generic Agents, candidate
fixtures, and Slow agents unchanged; also assert that missing readiness does
not reserve an external attempt and that budget exhaustion cannot write a
round-rejection checkpoint.

## Limits

This does not make provider output valid or make exhausted frozen budgets
extendable. Malformed output still uses bounded domain correction, while an
exhausted immutable contract remains paused until an explicitly designed new
contract or generation is created.
