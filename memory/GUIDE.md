# Memory Guide

Do not read memory at session start. Use this guide only when prior project experience might apply, or when starting work on a specific module and doing the required quick trigger-map scan.

## Trigger Map

| Trigger | Experience | visit_times | Notes |
| --- | --- | ---: | --- |
| Changing filing visibility, window selection or source read navigation | [`experiences/nonvisible-source-content-consumes-readable-budget.md`](experiences/nonvisible-source-content-consumes-readable-budget.md) | 0 | Share source visibility before budget selection; directories expose usable raw body/section coordinates. |
| Changing local LLM repairs, structured reflections, memory indexes or context growth | [`experiences/incremental-repair-and-sourced-memory.md`](experiences/incremental-repair-and-sourced-memory.md) | 32 | Align prompt, validator and typed repair authority; preserve originals and budget actual consumer payloads with reachable source reads. |
| Masking, pseudonymizing, or projecting hash-bound persisted records before index/validator construction | [`experiences/masked-projection-breaks-content-hash-refs.md`](experiences/masked-projection-breaks-content-hash-refs.md) | 1 | Mask only at model-facing egress; entry-level masking of content-hash refs breaks verification and ref stability, and narrow fixture alias sets never reproduce it. |
| Reflecting on repeated self-evolution failures, preparing another Fast/Slow repair or successor, or claiming learning/quality gain | [`experiences/self-evolution-convergence-and-acceptance.md`](experiences/self-evolution-convergence-and-acceptance.md) | 35 | Separate execution, feedback consumption, and independent gain; replay real production composition and the affected cross-cycle lifecycle before extending complexity. |
| Adding provider, adapter, registry, or plugin-like extension point | [`experiences/provider-boundary-placement.md`](experiences/provider-boundary-placement.md) | 15 | Avoid coupling reusable providers to the first consumer module. |
| Running or changing formal cold start, blind LLM prompts, OpenRouter cold-start calls, or seed/formal entry points | [`experiences/formal-cold-start-blind-boundaries.md`](experiences/formal-cold-start-blind-boundaries.md) | 50 | Restate the execution contract, exact prediction unit, packet contents, anonymity boundary, and web-search boundary before using existing scaffolding. |
| Running Python tests, project scripts, formal cold-start pipelines, or validation commands | [`experiences/python-runtime-for-tests.md`](experiences/python-runtime-for-tests.md) | 62 | Use the project-compatible Python 3.11+ runtime instead of system Python. |
| Comparing paired blind-LLM information plans or interpreting small confidence deltas | [`experiences/paired-llm-comparison-noise.md`](experiences/paired-llm-comparison-noise.md) | 14 | Reuse responses for identical packet hashes and separate model sampling noise from information lift. |
| Computing evolution benefit with missing, failed, invalid, or abstained frozen cases | [`experiences/evolution-confirmation-failure-denominators.md`](experiences/evolution-confirmation-failure-denominators.md) | 8 | Keep the cohort fixed; positive technical failures are false negatives, negative failures are not true negatives, and missing rows make the report incomplete. |
| Interpreting F1 loss or factor rejection at correction, materialization, fixture, or capability boundaries | [`experiences/technical-failure-before-quality-attribution.md`](experiences/technical-failure-before-quality-attribution.md) | 4 | Replay the typed frontier first; transport no-progress can still hand off to deterministic fallback, and mixed modality is a split gap rather than an effectiveness verdict. |
| Changing continuous self-evolution persistence, resume, branching, or dashboard history | [`experiences/continuous-round-commit-marker.md`](experiences/continuous-round-commit-marker.md) | 44 | Treat round/cycle pointers as authoritative; case artifacts are exact checkpoints and debug events never prove completion. |
| Changing additive case/Plan/Round reflection or Plan FIFO meta-info | [`experiences/additive-reflection-fifo.md`](experiences/additive-reflection-fifo.md) | 9 | Preserve original, vertical, and horizontal layers in one whole FIFO entry; outcome-aware proposer memory never enters blind prediction. |
| Changing evaluation evidence gates, provider fallback, or shared missing-source handling | [`experiences/evolution-shared-data-readiness.md`](experiences/evolution-shared-data-readiness.md) | 5 | Prepare shared data before Plan work; unavailable Random candidates may rotate, while Anchor/snapshots stay immutable and shared gaps never become Plan fitness. |
| Adding authorization, budget, approval, pause exceptions inside evolution role/tool boundaries | [`experiences/evolution-control-plane-not-domain-validation.md`](experiences/evolution-control-plane-not-domain-validation.md) | 15 | Keep orchestration control flow outside bounded model-content correction. |
| Migrating legacy cold-start cases/documents/prices into the replacement evolution runtime | [`experiences/legacy-artifact-raw-info-migration.md`](experiences/legacy-artifact-raw-info-migration.md) | 4 | Separate source facts, Basic Info, and labels; recompute outcomes and keep Locked Test sealed. |
| Expanding the historical case library from a full-market price archive | [`experiences/full-market-case-expansion-boundaries.md`](experiences/full-market-case-expansion-boundaries.md) | 8 | Preserve all eligible issuers by default, balance only round snapshots, reject pre-IPO identity conflicts, and emit a label-free acquisition scope. |
| Acquiring historical company news or interpreting provider coverage | [`experiences/historical-news-backfill-boundaries.md`](experiences/historical-news-backfill-boundaries.md) | 2 | Preserve publication-time availability, title/summary scope, quota resume, and explicit provider-limit saturation. |
| Materializing historical SEC Company Facts | [`experiences/sec-company-facts-point-in-time-boundaries.md`](experiences/sec-company-facts-point-in-time-boundaries.md) | 4 | Group facts by accession, use conservative availability, and never infer registrant CIK from the accession prefix. |
| Auditing or changing SignalResult evidence validation and LLM Signal correction | [`experiences/signal-result-evidence-invariants.md`](experiences/signal-result-evidence-invariants.md) | 13 | Validate unavailable/evidence coherence before early returns and distinguish semantic unavailable from parser/validator failure. |
| Auditing deterministic SEC-fact factors or implausible deterministic values in blind contexts | [`experiences/sec-revenue-tag-mixing-breaks-deterministic-factors.md`](experiences/sec-revenue-tag-mixing-breaks-deterministic-factors.md) | 0 | Same-period multi-tag mixing (total vs partial/zero) plus cross-tag YoY pairing produce literal-cited garbage; guard value plausibility, not just evidence literalness. |
| Adding a harness/evaluation that needs realized labels, or auditing a scored-wrong prediction | [`experiences/hand-entered-ground-truth-single-door.md`](experiences/hand-entered-ground-truth-single-door.md) | 1 | Hand-entered outcome constants bypass every gate and feed fictitious lessons to the learning loop; derive from the global label store and fail closed on missing keys. |
| Changing Signal learning events, learned profiles, or Fast-cycle profile recovery | [`experiences/signal-learning-profile-cycle-freeze.md`](experiences/signal-learning-profile-cycle-freeze.md) | 6 | Separate Plan selection events from deduplicated observations and freeze dynamic profiles at the Fast-cycle start for restart equivalence. |
| Changing structured role correction, explicit empty results, or exact provider request auditing | [`experiences/structured-role-boundary-exactness.md`](experiences/structured-role-boundary-exactness.md) | 28 | Keep domain empty distinct from invalid output and make prompt, parser, persisted body, provider builder, and HTTP bytes one contract. |
| Changing H1 need ledgers, existing-Signal coverage, or bounded portfolio accounting | [`experiences/h1-unresolved-need-dispositions.md`](experiences/h1-unresolved-need-dispositions.md) | 3 | An unresolved need cannot become covered by citation alone; preserve measurable overflow explicitly and validate grouped updates per need. |
| Auditing a real evolution run's exact prompts, contexts, privacy boundaries, or token use | [`experiences/live-evolution-context-audit.md`](experiences/live-evolution-context-audit.md) | 36 | Join exact requests to attempts, pointers, fitness gates, invocation authorization, and snapshots; zero calls do not prove sampling stayed neutral. |
| Adding an evidence modality, candidate contract, or correction loop that spans controller, materialization, retrieval, and executor layers | [`experiences/llm-pipeline-layer-vocabulary-alignment.md`](experiences/llm-pipeline-layer-vocabulary-alignment.md) | 6 | Share one vocabulary at every validating boundary, persist modality separately from executor type, mask model-facing inputs, and feed back the judge's interpretation. |

## Experience Index

- [`experiences/incremental-repair-and-sourced-memory.md`](experiences/incremental-repair-and-sourced-memory.md): snapshot-bound partial repair, same-generation actionable briefs, stable provenance and actual bounded multi-stage consumption.
- [`experiences/masked-projection-breaks-content-hash-refs.md`](experiences/masked-projection-breaks-content-hash-refs.md): content-hash refs verify only over authoritative bytes; mask at model-facing egress and pin the masked-input path as rejected.

- [`experiences/self-evolution-convergence-and-acceptance.md`](experiences/self-evolution-convergence-and-acceptance.md): convert the accumulated failure trajectory into concrete acceptance evidence; keep committed cycles, fulfilled subgoals, promoted/used Signals, and independent gain distinct.
- [`experiences/provider-boundary-placement.md`](experiences/provider-boundary-placement.md): reusable provider registries should live at the capability boundary, not inside the first module that consumes them.
- [`experiences/formal-cold-start-blind-boundaries.md`](experiences/formal-cold-start-blind-boundaries.md): formal cold-start work must verify the single entry point, actual packet contents, blind anonymity boundary, web-search boundary, and explicit surge-candidate judgment schema before execution.
- [`experiences/python-runtime-for-tests.md`](experiences/python-runtime-for-tests.md): test and script commands should use the bundled Python 3.11+ runtime because system Python may be 3.9.
- [`experiences/paired-llm-comparison-noise.md`](experiences/paired-llm-comparison-noise.md): paired information-plan runs must reuse identical-packet responses and avoid treating small single-call confidence movement as evidence.
- [`experiences/evolution-confirmation-failure-denominators.md`](experiences/evolution-confirmation-failure-denominators.md): system metrics must keep frozen failures in the quality denominator rather than recomputing a cleaner score over successful rows.
- [`experiences/technical-failure-before-quality-attribution.md`](experiences/technical-failure-before-quality-attribution.md): replay exact technical frontiers before blaming research quality; duplicate-request guards may hand off to typed fallback, and mixed modality must be split before effectiveness evaluation.
- [`experiences/continuous-round-commit-marker.md`](experiences/continuous-round-commit-marker.md): multi-file continuous rounds need one atomic commit pointer so Ctrl+C cannot expose a staged round as resumable or branchable history.
- [`experiences/additive-reflection-fifo.md`](experiences/additive-reflection-fifo.md): layer original case, vertical Plan, and horizontal Round reflection additively inside one fixed-window FIFO entry without widening blind-prediction access.
- [`experiences/evolution-shared-data-readiness.md`](experiences/evolution-shared-data-readiness.md): shared case evidence must be prepared before Plan work and paused outside fitness/rejection semantics.
- [`experiences/evolution-control-plane-not-domain-validation.md`](experiences/evolution-control-plane-not-domain-validation.md): authorization and budget pauses must not inherit from domain validation errors that model/tool repair loops catch.
- [`experiences/legacy-artifact-raw-info-migration.md`](experiences/legacy-artifact-raw-info-migration.md): legacy case objects must be decomposed into point-in-time Raw Info, minimal Basic Info, and separately recomputed labels rather than copied wholesale.
- [`experiences/full-market-case-expansion-boundaries.md`](experiences/full-market-case-expansion-boundaries.md): full-market case expansion needs fixed dates, issuer/security identity gates, explicit sampling-bias disclosure, and a label-free handoff to data acquisition.
- [`experiences/historical-news-backfill-boundaries.md`](experiences/historical-news-backfill-boundaries.md): historical provider news needs exact label-free windows, publication-time availability, append-only summaries, quota-aware resume, and explicit saturation gaps.
- [`experiences/sec-company-facts-point-in-time-boundaries.md`](experiences/sec-company-facts-point-in-time-boundaries.md): current Company Facts responses must be decomposed by historical accession and cannot use accession prefixes as registrant identity.
- [`experiences/signal-result-evidence-invariants.md`](experiences/signal-result-evidence-invariants.md): unavailable Signals cannot retain placeholder evidence; audit literal, point-in-time, fingerprint-bound citations separately from semantic data absence.
- [`experiences/sec-revenue-tag-mixing-breaks-deterministic-factors.md`](experiences/sec-revenue-tag-mixing-breaks-deterministic-factors.md): same-period revenue-tag mixing and cross-tag YoY pairing produce confident garbage from literal facts; require same-tag pairs and plausibility guards, and audit what actually reached the blind context.
- [`experiences/hand-entered-ground-truth-single-door.md`](experiences/hand-entered-ground-truth-single-door.md): ground truth is derived from the global label store, never transcribed; wrong labels manufacture fictitious lessons and only external spot checks catch archive-level errors.
- [`experiences/signal-learning-profile-cycle-freeze.md`](experiences/signal-learning-profile-cycle-freeze.md): version-bound Signal learning must preserve Plan-specific reasons, deduplicate case/input efficacy, and freeze dynamic profiles at the Fast-cycle start for restart equivalence.
- [`experiences/structured-role-boundary-exactness.md`](experiences/structured-role-boundary-exactness.md): only schema-valid empty results mean no-match; production role request preview, approval, hashing, and HTTP transport must share exact canonical bytes.
- [`experiences/h1-unresolved-need-dispositions.md`](experiences/h1-unresolved-need-dispositions.md): H1 needs an explicit measurable-overflow state and per-need coverage basis so bounded portfolios do not erase unresolved demand.
- [`experiences/llm-pipeline-layer-vocabulary-alignment.md`](experiences/llm-pipeline-layer-vocabulary-alignment.md): every layer touching one concept must share the authoritative vocabulary, model-facing inputs are masked at the boundary, correction feedback carries the judge's interpretation, and empty 200 responses are retryable transport anomalies.

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
