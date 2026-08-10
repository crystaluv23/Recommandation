# Signal Library

## Status

Started

## Purpose

Own the versioned Signal Registry used by adaptive Information Plans. A Signal
is one reusable analysis capability:

```text
Signal = Schema + ExecutionPolicy + EvidencePolicy
```

This module is separate from `signals.py`, whose existing rules measure fixed
`ResearchPacket` features for the older cold-start path.

## Signal Types

- `deterministic`: calls a registered pure function over point-in-time Raw Info.
- `llm`: runs a versioned extraction skill over point-in-time Raw Info through
  a supplied no-label executor.

Every Signal produces a `SignalResult` with:

- canonical state: `positive`, `neutral`, `negative`, or `unavailable`;
- confidence from 0 to 1;
- rich interpretation text for the Predictor;
- supporting and counter-evidence spans; and
- coverage status.

Canonical state is the statistics interface. Rich interpretation and evidence
remain available to the research runtime.

## Registry Layout

A runtime registry uses category folders and immutable version folders:

```text
signals/<category>/<signal_id>/
  manifest.json
  stats.json
  versions/v<N>/
    spec.json
    skill.md          # required for LLM Signals
    tests.json
signals_candidates/<category>/<signal_id>/v<N>/...
```

The source-controlled v1 seed catalog may be compact JSON, but workspace
initialization must materialize this runtime structure. The first seed catalog
contains 12 manually defined Signals across financial, market, customers,
management, orders, product, risk, and catalyst categories.

## Progressive Disclosure

The Registry exposes:

1. category names;
2. compact Signal cards with current version, type, description, and observed
   policy statistics; and
3. full versioned `SignalSpec` only when selected.

`freeze()` returns one immutable definition snapshot and hash. Stats may keep
accumulating while frozen, but stable definitions and versions cannot change
until the fast-loop group ends.

## Execution and Evidence

`SignalExecutor.execute_batch()` retrieves only documents satisfying
`available_at <= as_of`, executes all selected Signals, validates evidence, and
returns one `SignalBatchResult`. Batch reflection happens later in the research
controller.

When evidence policy requires it, each non-unavailable result must cite a
document in the actual input set, the cited timestamp cannot exceed the as-of
time, and the exact span must literally occur in the cited document.

An LLM Signal result that fails schema, identity, source, timestamp, or exact-
span validation receives at most one corrective model call with the validation
feedback and failed output. The correction is subject to the same strict
validator. If it also fails, execution returns a canonical `unavailable` result
with no evidence rather than accepting or fabricating a citation. Provider and
unexpected runtime failures still propagate so external-call recovery remains
explicit.

## Observed Policy Statistics

For each canonical state maintain actual occurrence counts against `surge` and
`non-surge`, plus retrieval, execution, unavailable, token, and latency/cost
totals when known. The statistic is explicitly observational under the current
adaptive retrieval policy; it is not causal credit and does not count mere Plan
membership as a Signal occurrence.

Every occurrence uses a stable observation id derived from Plan, case,
research round, result position, and Signal version. Reconciliation after
restore is idempotent so a committed trajectory cannot be counted twice.

## Candidate and Promotion Boundary

Mining and update agents write only under `signals_candidates/`. A candidate
can be promoted only after checks for:

- schema validity;
- a non-empty point-in-time fixture set executed through the real candidate
  executor with expected canonical states;
- obvious future/label leakage;
- required evidence traceability;
- semantic duplication against stable Signals; and
- valid version progression for updates.

An update creates `vNext`; it never overwrites a stable version. Machine
validation writes a candidate hash and a `pending_human_approval` result. A
separate human approval artifact must name the reviewer and the exact candidate
hash. `promote_candidate` fails closed without that approval or if spec, skill,
or tests changed afterward. Approved promotions are applied as one batch, then
the Registry version advances once.

## Testing

Cover progressive disclosure, immutable version registration, frozen snapshot
behavior, deterministic and LLM execution, exact evidence validation,
unavailable state, observed-policy counts, candidate isolation, executable
candidate fixtures, alias-aware leakage rejection, exact-hash approval, and
versioned promotion.
