# Evolution Benefit Confirmation

## Slow method-memory ablation

An offline ablation manifest may compare `no_memory`, `episodes_only`, and
`episodes_and_lessons` from the same frozen Fast/Registry start, seed, model,
data boundary, and budget. It records all generated Registry hashes and the
allowed paired comparisons before any confirmation result is revealed. One
confirmation reservation is bound to the complete comparison group and excludes
issuers, not only case ids, from reuse. Missing rows and technical failures stay
in the frozen denominator; insufficient or historically unverifiable issuer
isolation is reported as incomplete.

## Purpose

Provide a pure, offline confirmation boundary for the question “did the system
actually improve?” It consumes frozen case-level results created elsewhere. It
does not call a model or data provider, open Locked Test, promote a Signal,
change production gates, or reorder historical Plans.

## Protocol

`EvolutionBenefitProtocol` is immutable and has no inferred research defaults.
It must name:

- the exact confirmation case ids and opaque issuer groups;
- the exact independent candidate-Signal capability case ids and issuer groups;
- independent replicate ids and the current/maximum planned experiment look;
- baseline and candidate Plan hashes and Registry hashes;
- the shared model, budget, projection, and protocol identities;
- minimum case/issuer counts, primary F1 gain, issuer-cluster interval lower
  bound, maximum coverage loss, maximum failure rate, and optional maximum cost
  increase; and
- the minimum independent candidate-Signal fixture count and minimum measurement
  accuracy. A changed Registry requires at least one independent fixture; a
  fixed-Registry Plan-only protocol may explicitly set the count to zero.

Creating a protocol whose declared cohort or thresholds are incomplete is a
validation error. These values are review inputs, not defaults copied from the
small production Signal promotion gate.

## Four-arm system comparison

Every case and replicate has exactly these four arms:

1. baseline Plan + baseline Registry;
2. candidate Plan + baseline Registry;
3. baseline Plan + candidate Registry; and
4. candidate Plan + candidate Registry.

Each case result retains the prediction or technical failure, ground truth,
coverage, cost/usage, source-corpus hash, actual Plan/Registry hashes, exact
model/budget identities, model input hash, response invocation id, and the
executed/cited Signal refs. The evaluator rejects cross-arm corpus, identity,
label, or issuer drift. Missing arms remain in the frozen denominator and make
the report `incomplete`; they are never dropped before recomputing F1.

Within one replicate, arms with the exact same model input hash must reuse the
same response invocation. Distinct replicate ids must use independent response
invocations when a model call occurs. This separates paired response reuse from
sampling-variance experiments. One response invocation also has one prediction
and validation outcome; attaching different outputs to the same invocation is
invalid rather than evidence of arm lift.

The report contains confusion counts and F1, coverage, technical failure rate,
cost, paired improvement/regression counts, Plan-only lift, Registry-only lift,
combined lift, their interaction, and a deterministic issuer-cluster bootstrap
interval. Retrieval coverage and cost deltas remain visible; they cannot be
silently attributed to a Signal skill.

A received technical failure with a known positive label counts as a false
negative in Binary F1 instead of disappearing from the score. Failures on known
negative labels remain explicit confusion diagnostics and are bounded by the
separate failure-rate criterion; they are not counted as true negatives.

The overall result is `gain_confirmed`, `no_gain`, or `incomplete`. Every frozen
criterion must pass for `gain_confirmed`. A complete evaluable comparison that
misses any threshold is `no_gain`, even if a candidate was promoted.

## Signal capability confirmation

`CapabilityCaseResult` records independent and author-written fixtures
separately. It retains expected and actual canonical state, execution status,
contract validity, the actual supporting/counter literal evidence, evidence
validity, optional outcome label, source hash, and baseline/candidate variant.
A decisive measurement marked evidence-valid must retain at least one literal
`SignalEvidence` span. The report separately shows contract pass rate, evidence
pass rate, measurement accuracy, execution failures, and an explicitly named
outcome-association diagnostic. Author-written fixtures prove executability only
and never enter the independent measurement-accuracy claim.
When the candidate Registry differs from baseline, the overall system result
cannot be `gain_confirmed` unless the protocol's independent-fixture count and
measurement-accuracy criteria also pass. Missing or failed capability cases are
not replaced after results are observed.

An absent frozen capability case makes the report `incomplete`; an unplanned
independent candidate case is rejected instead of being used as a replacement.

## Lifecycle evidence

`EvolutionLifecycleEvidence` records whether an exact candidate was promoted and
whether the candidate Registry was later loaded, executed, and cited on named
case ids. The report keeps `promoted`, `used`, and independently
`benefit_confirmed` as different facts. A version/hash change alone is not use.

## Confirmation usage ledger

`ConfirmationCohortLedger` reserves opaque system and capability case ids for
one protocol in an append-only, crash-safe JSON record. Reusing any reserved
case under another protocol fails closed. Exact replay of the same
protocol/cohort is idempotent; changing the cohort for an existing protocol is
rejected. Locked Test requires its separate human-approved boundary and is never
implied by this ledger.

Reports are immutable by protocol/result hash. Exact rewrites are no-ops and
conflicting rewrites fail rather than replacing unfavorable evidence.

## Dependencies

This module depends only on shared artifact hashing/writes, core validation, and
Signal enums. Production Plan/Signal engines may write compatible results but do
not import or invoke the confirmation evaluator as part of promotion.
