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
initialization must materialize this runtime structure. The seed catalog
contains 16 auditable definitions across financial, market, customers,
management, orders, product, risk, and catalyst categories; 14 are enabled in
the executable snapshot and two remain disabled.

Seed and runtime manifests carry an explicit enabled status. Structurally
unsupported definitions remain auditable but disabled and are omitted from
category/card/spec disclosure. They may be enabled only after the capability
audit below passes; absence of case-specific data remains a normal DataGap and
does not structurally disable an otherwise executable Signal.

## Progressive Disclosure

The Registry exposes:

1. category names;
2. compact Signal cards with current version, type, description, and observed
   policy statistics; and
3. full versioned `SignalSpec` only when selected.

`freeze()` returns one immutable definition snapshot and hash. Stats may keep
accumulating while frozen, but stable definitions and versions cannot change
until the fast-loop group ends.
Freezing an empty Registry is invalid: a v4 run must contain at least one
enabled, capability-audited stable Signal and the normal seed initialization
contains all 11 enabled definitions.

Before freeze, `SignalCapabilityAudit` validates every enabled Signal against
its registered deterministic function or LLM skill, supported source routing,
and a fixture in the actual Raw Info schema. The enabled-only snapshot and audit
hash are bound by the run contract. `market_cap` and `pilot_to_volume` remain
disabled until reliable historical inputs and adapters exist.

## Seed Hard-Signal Defaults

The hard-signal seed is intentionally small. It supplies reproducible primitive
measurements that complement, rather than replace, the LLM Signals and adaptive
Information Plan. Three additional primitives cover material gaps in the
original seed:

- `operating_cash_flow_margin` divides the latest point-in-time operating cash
  flow by revenue from the exact same reported duration. The default state is
  positive at `>= 10%`, negative at `<= 0%`, and neutral between them. Missing
  matched periods or non-positive revenue is `unavailable`. This is a
  size-normalized cash-conversion proxy, not a complete accrual model; sector
  differences and working-capital timing remain for the Plan to interpret.
- `net_share_retirement_yoy` is `1 - current weighted-average shares / prior
  comparable weighted-average shares`. Positive therefore means net share
  retirement and negative means dilution. The default state is positive at
  `>= 2%` retirement, negative at `<= -5%` (at least 5% dilution), and neutral
  between them. The executor prefers comparison facts from the same filing so
  stock-split restatements remain comparable, and otherwise fails closed when
  it cannot form a valid year-over-year pair.
- `price_momentum_126d` is the total return across the latest 126 intervals in
  the chronological adjusted-close series. It requires 127 daily observations;
  the name denotes trading observations, not an exact calendar-six-month
  interval. The default state is positive at `>= 20%`, negative at `<= -20%`,
  and neutral between them.

These cutoffs are explicit, reviewable seed heuristics, not values claimed by
the underlying empirical papers. A future promoted version may change them
only through the normal candidate validation and exact-hash automatic-promotion
boundary.
The cash-flow and issuance literature motivates the measurements, while the
project vision's early-market-confirmation requirement motivates momentum. The
system does not yet have a peer-relative execution context, so the momentum
seed uses absolute return and leaves relative-strength comparison to the
cross-sectional Plan/evaluation layer.

## Execution and Evidence

`SignalExecutor.execute_batch()` retrieves only documents satisfying
`available_at <= as_of`, executes all selected Signals, validates evidence, and
returns one `SignalBatchResult`. Batch reflection happens later in the research
controller.

Within one case, executor identity is `(signal_ref, sorted document_id/hash
fingerprint)`. Re-selecting the same Signal with an unchanged fingerprint is a
no-op and does not consume another Signal call. A changed oracle fingerprint may
be executed again. Financial deterministic Signals parse both scoped SEC
Company Facts API JSON and accession-scoped
`sec-company-facts-document-v1`; derived evidence cites the exact serialized
fact rows used in the calculation.

When evidence policy requires it, each non-unavailable result must cite a
document in the actual input set, the cited timestamp cannot exceed the as-of
time, and the exact span must literally occur in the cited document.
Aggregate deterministic Signals cite every input document that contributed to
the aggregate, using a span containing a matched term when the result depends on
literal term counts; they do not cite an unrelated first document merely
because it was present in the batch.

An LLM Signal result that fails schema, identity, source, timestamp, or exact-
span validation receives at most one corrective model call with the validation
feedback and failed output. The correction is subject to the same strict
validator. If it also fails, execution returns a canonical `unavailable` result
with no evidence rather than accepting or fabricating a citation. Provider and
unexpected runtime failures still propagate so external-call recovery remains
explicit.

Complete Raw Info documents remain the local lineage, fingerprint, and final
evidence-validation boundary; they are not copied into an LLM Signal request or
into `SignalResult`. Before an LLM Signal executes, the runtime deterministically
projects its resolved documents into literal source windows using the Signal
description and versioned skill. The model-facing payload contains only minimal
document lineage plus `start`, `end`, and `exact_text` for those windows. It is
capped at 24,000 source characters per Signal execution, uses 2,000-character
windows with 200-character overlap, and selects the best matching window from
each resolved document before filling the remaining budget by relevance. The
projection is an execution context, not a claim that omitted text is absent;
when the visible windows cannot support a conclusion, the LLM Signal must return
`unavailable`. Returned evidence is still validated against the complete local
documents, so a bounded request cannot weaken source identity, point-in-time, or
literal-span guarantees.

Required Signal-result objects and evidence-policy booleans are type-strict;
missing coverage, string booleans, string-as-array evidence, and non-finite
confidence values are rejected rather than normalized by generic Python
coercion. The only conservative normalization remains the documented
`state.value=unavailable` narrowing to unavailable coverage.

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

Candidate drafts are immutable once validated. An exact replay reuses its saved
validation. If a rejected `vNext` is later repaired, the rejected draft is moved
under the candidate archive by its content/origin hash before the replacement
draft occupies the active `vNext` path; this preserves audit history without
permanently blocking that stable Signal from ever proposing the same next
version. An already promoted ref returned by a later agent is ignored as
already stable rather than revalidated or promoted twice.

An update creates `vNext`; it never overwrites a stable version. Machine
validation writes the exact candidate hash over spec, skill, and tests. The
Slow-Loop orchestrator durably stages the complete validated batch before any
stable file changes, then automatically promotes every passing exact hash.
There is no separate per-candidate human approval step inside this loop.

Before the first stable file is changed, the whole batch is prevalidated for
unique Signal ids, exact hashes, successful validation, and valid next-version
progression. Promotion is identified by the cycle transition id and is
idempotent: restart may reconcile an exact partially materialized version,
advance the Registry version at most once, verify the output snapshot, and
finish the same transition. A changed candidate, unrelated stable mutation, or
invalid later item fails closed. Empty passing batches leave the version/hash
unchanged.

## Testing

Cover progressive disclosure, immutable version registration, frozen snapshot
behavior, deterministic and LLM execution, bounded exact-window LLM context,
exact evidence validation against complete Raw Info, unavailable state,
observed-policy counts, candidate isolation, executable candidate fixtures,
alias-aware leakage rejection, exact-hash automatic batch promotion,
partial-transition recovery, and versioned promotion.
