# Memory Guide

Do not read memory at session start. Use this guide only when prior project experience might apply, or when starting work on a specific module and doing the required quick trigger-map scan.

## Trigger Map

| Trigger | Experience | visit_times | Notes |
| --- | --- | ---: | --- |
| Adding provider, adapter, registry, or plugin-like extension point | [`experiences/provider-boundary-placement.md`](experiences/provider-boundary-placement.md) | 13 | Avoid coupling reusable providers to the first consumer module. |
| Running or changing formal cold start, blind LLM prompts, OpenRouter cold-start calls, or seed/formal entry points | [`experiences/formal-cold-start-blind-boundaries.md`](experiences/formal-cold-start-blind-boundaries.md) | 44 | Restate the execution contract, exact prediction unit, packet contents, anonymity boundary, and web-search boundary before using existing scaffolding. |
| Running Python tests, project scripts, formal cold-start pipelines, or validation commands | [`experiences/python-runtime-for-tests.md`](experiences/python-runtime-for-tests.md) | 55 | Use the project-compatible Python 3.11+ runtime instead of system Python. |
| Comparing paired blind-LLM information plans or interpreting small confidence deltas | [`experiences/paired-llm-comparison-noise.md`](experiences/paired-llm-comparison-noise.md) | 11 | Reuse responses for identical packet hashes and separate model sampling noise from information lift. |
| Computing evolution benefit with missing, failed, invalid, or abstained frozen cases | [`experiences/evolution-confirmation-failure-denominators.md`](experiences/evolution-confirmation-failure-denominators.md) | 1 | Keep the cohort fixed; positive technical failures are false negatives, negative failures are not true negatives, and missing rows make the report incomplete. |
| Changing continuous self-evolution persistence, resume, branching, or dashboard history | [`experiences/continuous-round-commit-marker.md`](experiences/continuous-round-commit-marker.md) | 38 | Treat round/cycle pointers as authoritative; case artifacts are exact checkpoints and debug events never prove completion. |
| Changing additive case/Plan/Round reflection or Plan FIFO meta-info | [`experiences/additive-reflection-fifo.md`](experiences/additive-reflection-fifo.md) | 4 | Preserve original, vertical, and horizontal layers in one whole FIFO entry; outcome-aware proposer memory never enters blind prediction. |
| Changing evaluation evidence gates, provider fallback, or shared missing-source handling | [`experiences/evolution-shared-data-readiness.md`](experiences/evolution-shared-data-readiness.md) | 5 | Prepare shared data before Plan work; unavailable Random candidates may rotate, while Anchor/snapshots stay immutable and shared gaps never become Plan fitness. |
| Adding authorization, budget, approval, pause exceptions inside evolution role/tool boundaries | [`experiences/evolution-control-plane-not-domain-validation.md`](experiences/evolution-control-plane-not-domain-validation.md) | 10 | Keep orchestration control flow outside bounded model-content correction. |
| Migrating legacy cold-start cases/documents/prices into the replacement evolution runtime | [`experiences/legacy-artifact-raw-info-migration.md`](experiences/legacy-artifact-raw-info-migration.md) | 4 | Separate source facts, Basic Info, and labels; recompute outcomes and keep Locked Test sealed. |
| Expanding the historical case library from a full-market price archive | [`experiences/full-market-case-expansion-boundaries.md`](experiences/full-market-case-expansion-boundaries.md) | 8 | Preserve all eligible issuers by default, balance only round snapshots, reject pre-IPO identity conflicts, and emit a label-free acquisition scope. |
| Acquiring historical company news or interpreting provider coverage | [`experiences/historical-news-backfill-boundaries.md`](experiences/historical-news-backfill-boundaries.md) | 2 | Preserve publication-time availability, title/summary scope, quota resume, and explicit provider-limit saturation. |
| Materializing historical SEC Company Facts | [`experiences/sec-company-facts-point-in-time-boundaries.md`](experiences/sec-company-facts-point-in-time-boundaries.md) | 1 | Group facts by accession, use conservative availability, and never infer registrant CIK from the accession prefix. |
| Auditing or changing SignalResult evidence validation and LLM Signal correction | [`experiences/signal-result-evidence-invariants.md`](experiences/signal-result-evidence-invariants.md) | 5 | Validate unavailable/evidence coherence before early returns and distinguish semantic unavailable from parser/validator failure. |
| Changing Signal learning events, learned profiles, or Fast-cycle profile recovery | [`experiences/signal-learning-profile-cycle-freeze.md`](experiences/signal-learning-profile-cycle-freeze.md) | 4 | Separate Plan selection events from deduplicated observations and freeze dynamic profiles at the Fast-cycle start for restart equivalence. |
| Changing structured role correction, explicit empty results, or exact provider request auditing | [`experiences/structured-role-boundary-exactness.md`](experiences/structured-role-boundary-exactness.md) | 15 | Keep domain empty distinct from invalid output and make prompt, parser, persisted body, provider builder, and HTTP bytes one contract. |
| Auditing a real evolution run's exact prompts, contexts, privacy boundaries, or token use | [`experiences/live-evolution-context-audit.md`](experiences/live-evolution-context-audit.md) | 24 | Join exact requests to attempts, pointers, fitness gates, invocation authorization, and snapshots; zero calls do not prove sampling stayed neutral. |

## Experience Index

- [`experiences/provider-boundary-placement.md`](experiences/provider-boundary-placement.md): reusable provider registries should live at the capability boundary, not inside the first module that consumes them.
- [`experiences/formal-cold-start-blind-boundaries.md`](experiences/formal-cold-start-blind-boundaries.md): formal cold-start work must verify the single entry point, actual packet contents, blind anonymity boundary, web-search boundary, and explicit surge-candidate judgment schema before execution.
- [`experiences/python-runtime-for-tests.md`](experiences/python-runtime-for-tests.md): test and script commands should use the bundled Python 3.11+ runtime because system Python may be 3.9.
- [`experiences/paired-llm-comparison-noise.md`](experiences/paired-llm-comparison-noise.md): paired information-plan runs must reuse identical-packet responses and avoid treating small single-call confidence movement as evidence.
- [`experiences/evolution-confirmation-failure-denominators.md`](experiences/evolution-confirmation-failure-denominators.md): system metrics must keep frozen failures in the quality denominator rather than recomputing a cleaner score over successful rows.
- [`experiences/continuous-round-commit-marker.md`](experiences/continuous-round-commit-marker.md): multi-file continuous rounds need one atomic commit pointer so Ctrl+C cannot expose a staged round as resumable or branchable history.
- [`experiences/additive-reflection-fifo.md`](experiences/additive-reflection-fifo.md): layer original case, vertical Plan, and horizontal Round reflection additively inside one fixed-window FIFO entry without widening blind-prediction access.
- [`experiences/evolution-shared-data-readiness.md`](experiences/evolution-shared-data-readiness.md): shared case evidence must be prepared before Plan work and paused outside fitness/rejection semantics.
- [`experiences/evolution-control-plane-not-domain-validation.md`](experiences/evolution-control-plane-not-domain-validation.md): authorization and budget pauses must not inherit from domain validation errors that model/tool repair loops catch.
- [`experiences/legacy-artifact-raw-info-migration.md`](experiences/legacy-artifact-raw-info-migration.md): legacy case objects must be decomposed into point-in-time Raw Info, minimal Basic Info, and separately recomputed labels rather than copied wholesale.
- [`experiences/full-market-case-expansion-boundaries.md`](experiences/full-market-case-expansion-boundaries.md): full-market case expansion needs fixed dates, issuer/security identity gates, explicit sampling-bias disclosure, and a label-free handoff to data acquisition.
- [`experiences/historical-news-backfill-boundaries.md`](experiences/historical-news-backfill-boundaries.md): historical provider news needs exact label-free windows, publication-time availability, append-only summaries, quota-aware resume, and explicit saturation gaps.
- [`experiences/sec-company-facts-point-in-time-boundaries.md`](experiences/sec-company-facts-point-in-time-boundaries.md): current Company Facts responses must be decomposed by historical accession and cannot use accession prefixes as registrant identity.
- [`experiences/signal-result-evidence-invariants.md`](experiences/signal-result-evidence-invariants.md): unavailable Signals cannot retain placeholder evidence; audit literal, point-in-time, fingerprint-bound citations separately from semantic data absence.
- [`experiences/signal-learning-profile-cycle-freeze.md`](experiences/signal-learning-profile-cycle-freeze.md): version-bound Signal learning must preserve Plan-specific reasons, deduplicate case/input efficacy, and freeze dynamic profiles at the Fast-cycle start for restart equivalence.
- [`experiences/structured-role-boundary-exactness.md`](experiences/structured-role-boundary-exactness.md): only schema-valid empty results mean no-match; production role request preview, approval, hashing, and HTTP transport must share exact canonical bytes.

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
