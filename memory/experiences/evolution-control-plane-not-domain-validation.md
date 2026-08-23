# Evolution Control Flow Is Not Domain Validation

visit_times: 9

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

The later v5 launch audit also found a duplicated shell-side contract-schema
gate still accepting only v4 after the Python runtime had moved to v5. Stable
launchers are part of the control plane: their executable schema check must
advance with the runtime and carry a regression assertion, or a correct frozen
contract becomes operationally impossible to resume.

## 2026-08-16 Paid Structured-Output Failure

A DeepSeek proposal returned more than one top-level JSON value. The provider
call succeeded, but raw parsing raised `JSONDecodeError`, recorded zero cost,
discarded the model text, and terminated the whole run. This is neither an
operator pause nor valid role output. Persist and cost the paid response, keep
it out of the valid cache, then route it through the role's already bounded
structured correction. Repeated malformed output becomes a candidate/role
failure and never a process-level traceback.

## 2026-08-16 Process-Level Transport Recovery

One HTTP request retry and one evolution-process restart are different safety
boundaries. Keep exact provider calls single-attempt and durably reserved so an
EOF after transmission remains visible. The stable operator launcher may then
relaunch the same pointer-driven `run-loop` only when the CLI returns its
dedicated temporary status. Bound that relaunch policy by wall-clock time,
exponential backoff, and the unchanged frozen attempt/cost ceilings. Never
restart `Ctrl+C`, validation, contract, provider-rejection, or budget exits.

## How to Apply

Use separate exception families for orchestration control flow and domain
validation. Catch control-flow exceptions only at the run/cycle supervisor.
Regression-test that they cross Fast evaluators, Generic Agents, candidate
fixtures, and Slow agents unchanged; also assert that missing readiness does
not reserve an external attempt and that budget exhaustion cannot write a
round-rejection checkpoint. When a contract schema changes, search every
operator launcher for duplicated schema literals and test both the accepted
current schema and rejection of the immediately retired schema.

## Limits

This does not make provider output valid or make exhausted frozen budgets
extendable. Malformed output still uses bounded domain correction, while an
exhausted immutable contract remains paused until an explicitly designed new
contract or generation is created.
