# Signal Library

## Admission/tracking migration: Registry foundation implemented

Technically valid research Signals may enter the callable Registry while effect
remains unverified, per the 2026-10-02 user decision. The owning migration must
use the independent exact-version admission identity/status described below, preserve all
effect evaluations and existing atomic transition/recovery invariants, disclose
status in frozen model views, and connect target evaluation producers to actual
committed observations. Legacy evaluation v2/v3 and frozen runs retain their
original paired-admission semantics; setting effectiveness.accepted=true to
simulate technical admission is forbidden.
See [the approved Slow design](../../../reports/slow-signal-system-design-20261002.md).
Registry records, atomic publication/recovery and frozen status now exist.
Production Slow decisions now use this independent authority. Continuous target
tracking requires separate producer/consumer verification; no benefit is asserted.

### Technical admission record and atomic publication

The first migration step adds `signal-candidate-admission-v1`, independently of
legacy effectiveness evaluations. Its key hashes the exact candidate content,
input Registry hash, validator policy hash, sorted research targets and complete
contract validation result. An admitted result requires literal accepted=true,
no reasons and every non-empty staged fixture actually executed. Rejected
technical records remain diagnostic; they cannot authorize publication.
The record contains no effectiveness acceptance or assertion of benefit.
New production records also hash-bind optional `research_provenance` in their
identity: generation/induction case ids, origin and source-input hash. This is
research lineage, not effect evidence; old v1 identities without it stay valid.
Published admission carries the same lineage, while model status never discloses
case ids. Subsequent studies must exclude generation/induction cases and retain
unknown provenance explicitly rather than inventing an independent cohort.

The existing keyed evaluation directory/pointer and atomic transition carry
this record, preserving old v2/v3 evaluations unchanged. Transition prepare,
apply and recovery recheck the admission identity, candidate bytes and exact
input Registry hash, then repeat the stable executable-surface audit. Publication
copies the exact admission record into the immutable version before freezing the
output. Missing/corrupt admission metadata fails closed; no mutable candidate
pointer can change the status of a published version.

`FrozenSignalRegistry.research_status` and current compact cards expose only
exact-version technical status, research targets and effect_status=unverified.
This metadata is bound into learning_hash independently of definition hash;
historical snapshots without admission records preserve their prior identity.
`record_candidate_effectiveness` writes independent keyed observations under
`effects/` with exact candidate/evaluation identity; a separate effect pointer
never changes `validation.json` or a published admission. Observation payloads
remain retrospective and may include failure diagnostics. Legacy evaluation
readers continue to read original v2/v3 records without translation.

## V8 Slow feedback use

New `signal-learning-event-v2` use identities bind the canonical immutable
`PlanRecord` hash, case, exact Signal version and original round/result positions.
The event stores that source hash and position; the constructor verifies its id.
Different records may reuse round/Plan names without colliding. Canonical reload,
exact copying and restart reproduce the same identity; paths are not relocated
inside authoritative records. Version 1 events retain their exact serialization
and ids on import and multi-hop export. Frozen old runs stay read-only under new
code; this is not an in-place rewrite or duplicate re-derivation of their ledgers.
New source-bound events preserve selection history while physical observation
keys and target evaluation identities retain their existing deduplication.
Same-id/different-content rejection remains mandatory.

Slow method learning reads the append-only `SignalLearningEvent` ledger by exact
Signal version and committed cutoff. `event_id` preserves distinct Plan routing
reasons while `(case_id, signal_ref, input_fingerprint)` defines independent
observation identity for efficacy. Pending outcomes, no later use, domain
unavailability, technical execution failure, directional error, and explicit
reflection attribution remain separate facts. Candidate work ids remain outside
the usage ledger until an exact version is promoted and actually selected.

## Status

Started

## Purpose

Own the versioned Signal Registry used by adaptive Information Plans. A Signal
is one reusable analysis capability:

```text
Signal = Schema + ExecutionPolicy + EvidencePolicy
```

`raw_retrieval` is a version-owned policy, not only a list of provider source
types. It also stores bounded query terms, an optional lookback, an optional
human-readable comparison requirement, and structured source/period/observation
completeness requirements. The executor copies this policy into `RawInfoRequest`;
it never asks an LLM to invent provider aliases. Legacy definitions that omit
query terms receive a deterministic default from the complete `signal_id`, and
the normalized policy is included in every newly serialized spec and candidate
hash. A long natural-language description is not silently reused as the query.
The structured fields gate execution and authorized acquisition; the comparison
text remains an auditable explanation and is never parsed as executable logic.

This module is separate from `signals.py`, whose existing rules measure fixed
`ResearchPacket` features for the older cold-start path.

## Source-owned numeric measurement contract

A newly computed deterministic numeric result carries an optional `measurement`
object, owned by its executing function: finite `value`, `unit`, a bounded
`formula` description, and optional exact reported `period` (`end`, optional
`start`). Units distinguish fraction (percent display), fraction_difference
(percentage-point display), dimensionless ratio, count, months, and the reported
three-letter currency. The calculation, thresholds and canonical adoption string
are unchanged. This additive field supplies meaning that previously had to be
reconstructed from prose. It is absent from unavailable/non-numeric results;
legacy results with no field retain their original serialization and hashes.
A model must omit this field; the LLM Signal boundary rejects model-authored
measurements exactly as it rejects model-authored execution status.

The producer supplies units/formula/primary period at its calculation site, never
through a consumer mapping keyed to Signal id or a name guessed from prose.
Available views retain the measurement with numeric sign, categorical state,
and explicit percent versus percentage-point display. Evidence views retain
exact source dates separately; period labels cannot shorten cumulative duration.
No missing legacy field is fabricated. Routing remains conclusion-only.
The result validator checks that any declared period occurs in its cited original
numeric facts and that numeric metadata agrees with the canonical adoption string.
The existing execution/evidence/PIT checks remain mandatory.

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

Each canonical result also carries a runtime-owned execution status. `success`
and `domain_unavailable` are domain observations. `validation_failed`,
`transport_failed`, `permanent_failed`, `budget_blocked`, and
`authorization_blocked` are execution outcomes. They may use the same safe
unavailable-shaped value for downstream continuity, but they are not data
unavailability and are excluded from Signal observation, learning-profile, and
directional-effectiveness statistics. Their diagnostics remain in the canonical
record; downstream model views receive only a generic unknown-result summary and
the status. The model does not author execution status.

Batch execution isolates failures by exact Signal ref. A valid sibling remains
accepted and is not regenerated merely because another row fails validation or
cannot afford its correction. Only failed rows receive the bounded correction;
the complete local parser and evidence validator run again. A failed occurrence
does not consume the observation id, so a later validated recovery can be
recorded exactly once.

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
    learning/
      events.jsonl    # append-only committed Fast observations
      profile.json    # rebuildable bounded routing summary
signals_candidates/<category>/<signal_id>/v<N>/
  evaluations/<evaluation_key>.json
  validation.json    # pointer to the latest immutable evaluation
```

`stats.json` is a mutable runtime aggregate, not part of Registry identity
hashes. Registration initializes it empty, and a Registry materialized from
definition files only (Slow-history import) may lack it until the first
observation; `load_stats` treats absence as empty observed state rather than
corruption.

A candidate `signal_id` is unique across categories: candidate refs resolve by
`signal_id` and version alone, so staging the same `signal_id` under a second
category is rejected at the write with a correction-actionable error (choose a
distinct `signal_id`), never allowed to make later loads ambiguous.

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
2. compact Signal cards with current version, type, description, and one
   bounded learned routing profile; and
3. full versioned `SignalSpec` only when selected.

Progressive disclosure is an information boundary, not a requirement for one
provider call per level. The current small Registry supplies all eligible
compact cards in one Signal-selection call after deterministically omitting refs
already executed in the same case trajectory. Category remains card metadata;
the executor alone loads the selected full specs. The selection role may combine
those cards with a bounded label-free ResearchState applicability view, but never
with Basic/Signal literal source payloads or a full Signal spec. No eligible card or a valid
empty selection terminates retrieval without an additional model call.

`freeze()` returns one deeply immutable definition snapshot/hash plus a separately
hashed snapshot of the current learned profiles. Definitions and learned
profiles therefore have distinct identities: observations do not create a new
stable Signal version, but changing a profile changes the exact Fast execution
input and prevents stale trajectory reuse. Stats and learning events may keep
accumulating after a snapshot is frozen; that Fast group continues to see its
original profile snapshot, and stable definitions cannot change until it ends.
`committed_learning_events(ref, round_cutoff=..., imported_events=...)` selects
local cutoff events plus exact imported events, rejecting missing or changed
Registry copies of any authorized import for that version. `freeze` accepts
the same explicit imports alongside its local cutoff; it never rebases source
rounds or uses an imported maximum as local commit authority. Imported events
are supplied by the contract-bound tracking reader, not inferred from ledgers.
Freezing validates all imported exact versions and their ledger copies, including
immutable historical versions absent from the current stable-card menu. Only
current stable definitions enter the snapshot, with each profile selected from
that exact version's events; prior-version uses never transfer to vNext.
`list_version_refs()` enumerates readable immutable versions with path/identity
and uniqueness checks. Slow feedback and committed history export share this
inventory, then apply the same committed-event selection; enumeration itself
grants neither event authority nor Fast routing eligibility.
`load_committed_learning_profile` rebuilds the routing derivative from that same
selection for Update and bounded freezing; mutable full-ledger profiles are not
the committed-input contract.
`snapshot_from_refs(version, refs)` reconstructs only immutable definitions and
skills in their explicit order, recomputing the definition hash. It is used to
verify prior inputs after valid publication; callers must compare with their
frozen contract and cannot use it to invent commit authority or learned profiles.
Freezing an empty Registry is invalid: a v4 run must contain at least one
enabled, capability-audited stable Signal and the normal seed initialization
contains all 11 enabled definitions.
Nested spec parameters and learned profile values are immutable inside the
snapshot. Serialization returns detached mutable JSON values, so caller mutation
cannot alter executor behavior or silently separate a snapshot from its hash.

Before freeze, `SignalCapabilityAudit` validates every enabled Signal against
its declared research modality, registered deterministic function or LLM skill,
supported source routing, and a fixture in the actual Raw Info schema. New
specifications must persist `modality` as either `structured` or `narrative`.
`structured` means the value is fully determined by typed point-in-time fields
and parameters and therefore requires a registered deterministic callable;
`narrative` means the value depends on semantic interpretation of source text
and therefore requires an LLM skill. A mixed proposal must be split into a
structured measurement and a narrative predicate before either is admitted.
Specifications created before this contract may omit `modality` so immutable
historical Registry hashes remain readable, but such a legacy omission is not
accepted for a newly staged candidate or vNext version. The enabled-only
snapshot and audit hash are bound by the run contract. `market_cap` and
`pilot_to_volume` remain disabled until reliable historical inputs and adapters
exist.

### Legacy Registry modality migration

An existing Registry with legacy specs that omit `modality` is classified by a
declarative migration plan bound to the exact source Registry version and hash.
The plan must cover every current stable ref exactly once and declare its
research modality. The migration runs into a separate successor Registry; it
never edits the source Registry or its historical versions.

For a Signal whose executor already matches its research identity, migration
creates the next immutable version with the explicit modality and otherwise
preserves its spec, skill, and executable fixtures. A legacy numeric formula
stored as an LLM Signal must declare the registered deterministic function and
may replace its description, parameters, and fixtures. A narrative Signal must
retain an LLM skill. The successor advances the Registry version once for the
whole classification batch, passes the complete capability audit, and emits a
manifest containing source and target hashes plus every source-to-target ref.
Missing, duplicate, stale-hash, mixed, or non-executable classifications fail
closed. Runtime statistics and learning events are not copied into this
definition-only successor; they remain attached to their exact historical
Signal versions.

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
- Market-series numeric results cite complete original price-bar records for
  their calculation anchors (drawdown peak/trough and series endpoints;
  momentum window endpoints). Raw adjusted-close-or-close values must match
  the supplied metadata series before anchors are cited. Legacy metadata-only
  fixtures retain their literal source evidence; no price records are invented.
  This changes evidence provenance, not window or classification semantics.
- `price_momentum_126d` is the total return across the latest 126 intervals in
  the chronological adjusted-close series. It requires 127 daily observations;
  the name denotes trading observations, not an exact calendar-six-month
  interval. The default state is positive at `>= 20%`, negative at `<= -20%`,
  and neutral between them.

These cutoffs are explicit, reviewable seed heuristics, not values claimed by
the underlying empirical papers. A future promoted version may change them
only through the normal candidate validation and exact-hash automatic-promotion
boundary.

### Canonical basis and the plausibility gate (2026-09-30)

Every financial duration factor consumes the per-issuer canonical series
resolved under the Execution and Evidence contract, so a year-over-year pair or
a revenue-matched margin always shares one measurement basis; evidence citation
of the exact serialized fact rows is unchanged. Literal evidence validates
inputs, not the semantic validity of a composed measurement, so numeric factors
additionally declare a plausible magnitude bound: revenue growth and revenue
acceleration `|x| <= 5`, gross-margin change `|x| <= 2`, operating-cash-flow
margin `|x| <= 1.5`, net share retirement `|x| <= 1`, and 126-interval price
momentum `|x| <= 50`. A value beyond its bound keeps its computed canonical
state but is downgraded to partial coverage at 0.5 confidence with an
`implausible_value` marker in the interpretation, because a small number of
genuinely extreme observations exist and must stay visible rather than be
silently clipped; the bound is overridable per Signal version through the
`plausible_abs_max` parameter. Levels, drawdown (structurally within `[-1, 0]`),
and cash-flow-derived ratios are not magnitude-gated. A repository-wide sweep
script (`scripts/audit_deterministic_signals.py`) executes every deterministic
financial factor over the local Raw Info oracle and reports downgraded and
unavailable rates so basis regressions surface without waiting for a live
Fast round.
- `cash_to_current_liabilities_ratio` divides the latest cash and equivalents
  instant fact by current liabilities from the same period end and reported
  currency. Non-positive liabilities, missing matched facts, or stale current
  facts are `unavailable`.
- `cash_burn_rate_elevated` is the structured numeric component of the legacy
  mixed Signal: for the latest operating-cash-flow duration it divides negative
  operating cash flow by the closest cash instant at or before that duration's
  end. Non-negative operating cash flow has a burn ratio of zero. The default
  positive threshold is `0.10`; a below-threshold observed burn is neutral and
  non-negative cash flow is negative. Narrative statements about burn are a
  separate narrative predicate and cannot act as a fallback for this measure.
- `liquidity_runway_months` is the structured numeric component of the legacy
  mixed Signal: latest matched cash divided by absolute average monthly negative
  operating cash flow over the reported duration. It is positive at no more
  than six months, negative at at least twelve months, and neutral between;
  non-negative operating cash flow is negative evidence of low runway (an
  effectively unbounded burn runway), while missing matched inputs are
  `unavailable`. Narrative denials or plans require a separate narrative Signal.

The three legacy v1 Signals above were historically stored as LLM Signals.
Their artifacts remain immutable. A corrected deterministic v2 may be activated
only after a frozen-input replay verifies exact document ids and hashes,
point-in-time availability, literal evidence, availability behavior, and state
differences. Replay results are diagnostic artifacts and do not mutate a
Registry or count as a completed evolution cycle.
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

A non-empty but contract-incomplete Raw Info resolution is not executed. The
executor retains its document fingerprint for restart/recovery and emits a
domain-unavailable result for that Signal only. Complete siblings continue, so
one missing period or source cannot erase a valid batch.
Provider/configuration, budget, authorization, and materialization gaps map to
their runtime execution statuses instead of becoming domain observations.
Provider no-data, historical unavailability, no matching document, and an
otherwise valid but incomplete comparison remain domain-unavailable evidence
states.

Within one case, executor identity is `(signal_ref, sorted document_id/hash
fingerprint)`. Re-selecting the same Signal with an unchanged fingerprint is a
no-op and does not consume another Signal call. A changed oracle fingerprint may
be executed again. Financial deterministic Signals parse both scoped SEC
Company Facts API JSON (`us-gaap`, or `ifrs-full` when US GAAP is absent) and accession-scoped
`sec-company-facts-document-v1`; derived evidence cites the exact serialized
fact rows used in the calculation.

Financial duration primitives never mix reporting bases. For each additive flow
concept (revenue, gross profit) the executor resolves one canonical per-currency
series per issuer from the point-in-time fact set. The canonical basis is the
coverage-ranked tag (latest period end, then distinct period count, then the
declared tag order), so an issuer's ongoing basis wins over both legacy tags and
restatement crossovers. A period key covered by the canonical tag keeps the
canonical fact; a same-period value at least 3x smaller (or zero beside a
nonzero total) marks its whole tag as a disaggregation partial that is excluded
entirely, including periods the canonical tag does not cover, while remaining
trusted tags fill only uncovered keys so a tag switch or a percent-level
restatement crossover stitches into one series. Company Facts routinely
co-locates a total under
`Revenues` next to a partial slice or a zero under
`RevenueFromContractWithCustomer(Including|Excluding)AssessedTax` (the local
oracle has ≥2 co-locating revenue tags for 52% of issuers, diverging more than
3x for ~10%), so static tag priority is not a valid truth ordering; the tag
order in the alias lists (`RevenueFromContractWithCustomerExcludingAssessedTax`,
`RevenueFromContractWithCustomerIncludingAssessedTax`, `Revenues`,
`SalesRevenueNet`, `Revenue`; IFRS: `RevenueFromContractsWithCustomers`,
`RevenueFromSaleOfGoods`) remains only as the deterministic tie-breaker when
agreeing tags carry the same value. Cash instant dedupe never lets a zero-valued
fact from a preferred tag displace a nonzero same-period balance. Use one
reporting namespace per raw document to avoid mixing accounting bases; do not
infer gross profit from a different metric. All period, currency, freshness,
filing cutoff, and literal-evidence checks remain unchanged. For every duration/balance financial primitive, the newest
fact used as the current period must end no more than 550 calendar days before the
case as-of date. This accommodates one annual reporting cycle plus filing lag and a
bounded buffer while making an otherwise valid but years-old concept `unavailable`.
Older comparison periods may still support a fresh current year-over-year result.

The adaptive Information-Plan runtime treats the prepared Raw Info view as
fixed for one case trajectory and therefore removes already executed refs before
its next selection request. The executor keeps fingerprint-based no-op behavior
as a second correctness boundary and for direct callers whose Raw Info view may
change between batches.

When evidence policy requires it, each non-unavailable result must cite a
document in the actual input set, the cited timestamp cannot exceed the as-of
time, and the exact span must literally occur in the cited document.
An `unavailable` result must carry neither supporting nor counter-evidence:
`unavailable` means the visible inputs did not support a canonical conclusion,
not a weaker conclusion accompanied by irrelevant placeholder citations. The
model/parser boundary rejects this combination and sends the exact invariant
failure through the one bounded correction path.
Aggregate deterministic Signals cite every input document that contributed to
the aggregate, using a span containing a matched term when the result depends on
literal term counts; they do not cite an unrelated first document merely
because it was present in the batch.

A deterministic Signal's canonical `interpretation` is a locally computed,
validated derived record rather than source prose. Downstream ResearchState claims
may quote a numeric value from that interpretation only byte-for-byte (for example,
`revenue_growth_yoy=-0.087244`); the Signal ref and one valid source-evidence index
then preserve the calculation's provenance. The role may not round it, convert it
to a percentage, or introduce raw input quantities absent from the cited evidence.

An LLM Signal result that fails schema, identity, unavailable/evidence
coherence, source, timestamp, or exact-span validation receives at most one
corrective model call with the validation feedback and failed output. Feedback
identifies the exact evidence group/index when one citation failed, and states
the deterministic repair for an evidence-free available state. The correction
is subject to the same strict validator. If it also fails, execution returns a
canonical `unavailable` result with no evidence rather than accepting or
fabricating a citation. Provider and unexpected runtime failures still
propagate so external-call recovery remains explicit.

An LLM Signal version may also declare a small
`result_required_evidence_phrases` array inside `parameters`. For every
non-`unavailable` result, at least one version-owned phrase must occur
case-insensitively in the exact supporting or counter-evidence spans cited by that
result. This is a conservative measured-object gate, not a replacement for the
version skill: if the visible cited evidence does not name the measured object, the
result must be `unavailable` rather than attaching a canonical state to an unrelated
transaction or disclosure. `guidance_acceleration:v1` uses this gate for explicit
guidance/outlook/forecast/expectation language, so a financing or sale-leaseback
disclosure without such language cannot become guidance evidence. A failure names
the Signal ref and required phrases in the existing one-correction feedback.

LLM extraction skills also own an explicit applicability boundary. In
particular, `commercialization_status` measures the transition of a previously
non-commercial technical product or technology from demonstration/pilot into
real delivery and repeatable sales. Ordinary output, throughput, cost, or
guidance from an already mature mine, utility, financial institution, or
established service is not a commercialization milestone and must produce
`unavailable` for this Signal unless the visible source explicitly identifies a
distinct previously non-commercial product or technology and its commercial
transition. The compact routing card states the same boundary so the selector
can avoid an irrelevant paid execution; the full skill remains the final
semantic boundary if it is nevertheless selected.

A Signal version may additionally declare a small
`routing_excluded_context_tags` array inside `parameters`. Every value must come
from the frozen routing-tag vocabulary. The compact card exposes these exclusions,
and a selector output is internally contradictory when the excluded tag appears
either in the current batch or in that selector's earlier accepted classifications
for the same case. It receives the one bounded routing correction. Runtime does not
infer a case tag, remove a tag to force acceptance, or choose another Signal; it
acts only on the selector's own explicit current/prior classification plus the
version-owned exclusion. `commercialization_status:v1` excludes
`mature_operations`, matching its skill boundary without turning general routing
tags into universal hard rules.

The same measured-object rule applies to `customer_concentration:v1`: it is
eligible only when accepted needs/state already name a customer, client, buyer,
offtake, backlog, order, or customer program. A selector cannot introduce customer
concentration in its own reason as generic context for commodity prices, operating
diversification, or profitability. The extraction skill's existing semantic boundary
still controls the result: silence about customer identity is `unavailable`, never
proof of diversified adoption. Its available results also require cited evidence to
name a customer/client/buyer/offtake/backlog/order/account/program object; strength
across sales or distribution channels alone is not customer diversification.

Applicability and directly answering a need are separate. A Signal version may
declare `routing_answer_need_phrases` in addition to its broader applicability
phrases. When the selector returns `reason_code=answer_need`, at least one of those
version-owned phrases must already occur in the one need identified by its required
single `target_need_indices` value; occurrence in another need, elsewhere in
ResearchState, or in newly authored selector prose does not count. Non-answer reasons
may carry zero or one valid index to preserve which need the context supports, but
that association never means the need was answered and cannot authorize H_reflect to
remove or narrow it. On direct-answer failure, the selector must change the reason to
an accurate contextual code such as `combine_evidence`, or remove the selection.
`customer_concentration:v1` therefore
directly answers only concentration/dependence/diversification needs, not a request
to enumerate recent customer contracts merely because both contain “customer.”

A shared soft-Signal provider call deduplicates source text across at most two
Signals, but document eligibility remains per Signal. Each model-facing Signal entry
therefore includes `eligible_projection_ids`; evidence mapping rejects any citation
outside the matching list even when that projection is visible because the peer
Signal contributed it. Shared context is a transport optimization, not an expansion
of either Signal's Raw Info boundary.
If only one shared row fails or is omitted, its single correction request is
rebuilt from that Signal's eligible projections only. Valid sibling results and
their usage are retained. A comparison-oriented semantic unavailable or a
truncated highest-ranked window may use the same one correction slot to expose a
bounded re-projection; the executor never adds a second retry mechanism, treats
arbitrary retrieved documents as sufficient measurement evidence, or changes a
successful sibling's result.

`unavailable` is a coverage state, never evidence that the measured condition
is absent. The complete model-returned interpretation remains durable in the
canonical `SignalResult` for audit, but every downstream model-facing view
(routing history, H_reflect, Predictor/post-hoc, critic/meta, and Slow inputs)
replaces it with one deterministic coverage statement: visible evidence was
insufficient for a canonical conclusion and this is not evidence of absence.
An unavailable Signal cannot create a supporting/counter claim or resolve a
research question.

Available evidence-consuming views carry a runtime-owned `measurement_context` inside
`interpretation`: categorical states describe the version's measured condition,
not the stock's forecast direction. For numeric canonical interpretations, exact
JSON evidence rows with a dated reported value also disclose bounded
`source_observations` (`evidence_group/index`, raw `start/end/val` or `value`, or dated
adjusted-close anchors). Reporting-period labels cannot replace actual duration
boundaries; a cumulative duration must not be relabeled as an individual quarter.
This is a projection of existing validated literals, not a new calculation or
canonical SignalResult field. Missing/invalid/undated rows stay absent; source
records, results, thresholds and scoring remain unchanged. H_reflect retains
this context even when it suppresses repeated numeric evidence text, and final
Predictor assembly receives the same interpretation context.
Routing history stays conclusion-only: it excludes source observations and this
evidence-context envelope, so selection does not gain citation authority or
replay accumulated evidence through prior results.

A Signal version may declare a small `routing_need_phrases` string array inside
`parameters`. These phrases are conservative direct matches, not fuzzy search
terms, and each phrase contains at least two normalized words so a bare topic noun
cannot force a Signal merely because the need uses it as a benchmark or qualifier.
They are exposed on the compact card and used only to reject an empty selection once
for model correction; runtime still never chooses the Signal. The seed
`guidance_acceleration:v1` declares explicit update/revision constructions such as
`guidance updates` and `revised guidance`. A need that merely compares operating
results with existing guidance does not trigger this mandatory non-empty boundary,
although the selector may still choose the Signal under its ordinary applicability
contract. Unmatched empty selection remains valid.
For Signal ids with at least three normalized words, runtime may also use the complete
id as the conservative empty-selection phrase; it must not generate prefix, suffix, or
interior n-grams. `operating_cash_flow_margin:v1` separately declares the same full
measured object as its direct-answer phrase, so a request about cash-flow funding uses
contextual routing or no match rather than pretending it asked for a margin.

Complete Raw Info documents remain the local lineage, fingerprint, and final
evidence-validation boundary; they are not copied into an LLM Signal request or
into `SignalResult`. Before an LLM Signal executes, the runtime deterministically
projects its resolved documents into normalized readable text with stable
projection ids and raw-offset mappings. SEC HTML tags and repetitive per-row
market `retrieved_at/source/symbol` fields are absent from the model view while
the unmodified original remains durable. At most two selected LLM Signals in
one routing batch share one deduplicated projection capped at 32,000 source
characters and one structured call. If that complete bounded projection cannot
pass the exact remaining-request reservation, runtime retains the largest
deterministic subset that does fit, in the existing relevance order, while
preserving at least one eligible projection per selected Signal whenever that
minimum itself fits. The payload records whether this budget-only trimming
occurred and its actual visible-source size. This is a transport choice only
relative to refusing the entire Signal request: complete documents remain local,
omitted text is never treated as absence, and no citation or semantic validator
is relaxed. Results remain separately keyed, parsed, validated, learned, and
versioned. A bad result degrades only that Signal to `unavailable` after the
single correction boundary. Model evidence cites a projection id and literal
projected text; local code requires a unique mapping back to an original Raw Info
span and stores the original literal span in `SignalEvidence`. The projection is
an execution context, not a claim that omitted text is absent; ambiguity, absence,
or insufficient visible evidence fails closed.
When an initial shared call contains both valid and invalid Signal rows, accepted
rows remain independent. If the invalid rows' sole correction cannot pass its
pre-send reservation, only those pending rows become canonical `unavailable`; the
runtime retains the paid initial usage, accepted siblings, exact request-ready audit,
and ordinary downstream reflection. It never accepts the invalid rows or converts
the correction refusal into loss of a valid sibling.

Required Signal-result objects and evidence-policy booleans are type-strict;
missing coverage, string booleans, string-as-array evidence, and non-finite
confidence values are rejected rather than normalized by generic Python
coercion. The only conservative normalization remains the documented
`state.value=unavailable` narrowing to unavailable coverage.

## Version-Bound Learning Ledger

Every valid Signal selection returns the exact ref, a bounded reason code, a
short selection reason, an applicability hypothesis, an expected role, and
up to four coarse context tags from a fixed identity-free taxonomy covering
evidence coverage, company stage/business shape, sector, size, volatility, and
catalyst timing. The selected Signal is then executed unless a hard
contract, authorization, point-in-time, or runtime guard rejects it. An
unchanged `(signal_ref, input fingerprint)` may reuse the executor's existing
no-op cache; that is still a recorded selection, not an omitted decision.

After the round commit pointer advances, each exact Signal version receives an
append-only event for every Plan selection. The event records the reason and
coarse context, result/coverage and document fingerprint, realized outcome,
prediction correctness, and whether post-hoc reflection explicitly attributed
the Signal. The full routing decision remains in the execution trajectory. The
learning event receives an explicit stable projection containing only the
selection fields consumed by learning; routing-control fields such as answer
scope and residual need do not implicitly widen the ledger schema. A new field
is added to that projection only when the learning contract explicitly adopts
its semantics. A stable event id makes restore reconciliation idempotent.
`observation_key = (case_id, signal_ref, input fingerprint)` deduplicates the
state/outcome effectiveness matrix across Plans, while each Plan's selection
reason remains in the raw event stream. No event from an uncommitted round may
enter this ledger.

Repeated executions may disagree on result or coverage even with identical
case/input fingerprints. Preserve every event, but exclude the entire disputed
observation from state/outcome, directional and recurring-context effectiveness
counts; report its bounded `disputed_observations` count instead. Do not choose
the first result or reinterpret disagreement as unavailable/missing data.
Selection reasons and reflection attribution remain observational audit counts.
Identity, outcome and input-fingerprint conflicts remain hard integrity errors.
Replay rebuilds the profile even when all event IDs already exist, recovering
an interruption between durable event append and derived-profile publication.

`profile.json` is a deterministic derivative of those events for one exact
version. It contains only bounded counts, confidence, the complete
positive/neutral/negative/unavailable by surge/non-surge matrix, explicit
attribution counts, unavailable-with-input versus missing-input counts, and at
most a few recurring context patterns supported by
multiple observations and issuers. It contains no company/case/Plan identity,
literal evidence, or free-form reflection. It uses observational language and
does not claim causal Signal credit. Full events stay local for audit and Slow
Update. The older per-Signal aggregate `stats.json` remains an audit/cost
compatibility view and is not the selector's learned signature.

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

Candidate definitions are immutable once an evaluation is recorded, while the
same exact candidate may have multiple immutable evaluations. Each evaluation
is stored under a content-derived `evaluation_key` binding the candidate hash,
baseline, issuer-disjoint cohort, relevant Raw Info manifest, projection and
validator versions, model identity, and sampling protocol. An exact replay of
the same key reuses its saved result; a changed source manifest or protocol
creates a new record and preserves every earlier provisional or rejected result.
`validation.json` is only the replaceable latest-evaluation pointer and is never
the audit record itself. If a rejected `vNext` is later repaired, the rejected draft is moved
under the candidate archive by its content/origin hash before the replacement
draft occupies the active `vNext` path; this preserves audit history without
permanently blocking that stable Signal from ever proposing the same next
version. An already promoted ref returned by a later agent is ignored as
already stable rather than revalidated or promoted twice.

An update creates `vNext`; it never overwrites a stable version or edits the
old version's learning history. Machine
validation writes the exact candidate hash over spec, skill, and tests. The
Registry exposes the immutable fixture set for an exact stable ref so an Update
vNext can inherit it without reaching into Registry paths. Stable and candidate
fixture readers both reject malformed non-object rows; the Update layer adds the
non-empty requirement before model correction and staging. The
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
The prepared transition binds each candidate hash to one exact successful
evaluation key. Recovery may complete only that identity; a later evaluation,
even for the same candidate definition, cannot be substituted into an existing
transition.
While any transition is `prepared`, ordinary Registry reads fail closed instead
of exposing a mix of input and partially materialized output versions. Only the
promotion recovery path, after verifying the same transition identity, may read
that intermediate state and reconcile the remaining files, Registry version,
output hash, and applied marker.

Historical v2/v3 validation had three durable dispositions. `promoted` meant both the
candidate contract and the independent paired effectiveness gate passed.
`provisional` means the contract passes and induction evidence is directionally
supportive, but independent point-in-time availability or decisive support is
below the existing promotion floor; the draft remains isolated under
`signals_candidates/` and may be re-ranked or re-evaluated in a later Slow
cycle. `rejected` means the contract fails, independent evidence contradicts
the expected direction, or an update regresses/fails to improve once evidence
is sufficient. Those historical provisional records remain unchanged. New publication uses
independent technical admission and explicit unverified effect; bounded legacy
revalidation produces a new admission record rather than revising old verdicts.

The effectiveness audit records induction case refs separately from evaluation
case refs. The two sets must be issuer-disjoint. Case relevance ranking is
label-hidden; local code overlays outcomes, reserves later unused relevant cases
for evaluation, and may deterministically fill the remaining evaluation slots
from the Discovery pool without reusing an induction issuer.

## Testing

Cover progressive disclosure, immutable version registration, frozen snapshot
behavior, deterministic and LLM execution, bounded exact-window LLM context,
exact evidence validation against complete Raw Info, unavailable state,
version-bound append-only learning, cross-Plan observation deduplication,
identity-free bounded profiles, observed-policy compatibility counts,
candidate isolation, executable candidate fixtures,
alias-aware leakage rejection, exact-hash automatic batch promotion,
partial-transition recovery, and versioned promotion.


### Input compatibility and complete price windows

IFRS aliases include `CashAndCashEquivalents`, basic `WeightedAverageShares`, and
fallback diluted `AdjustedWeightedAverageShares`. These map to existing cash and
weighted-average-share concepts; instant shares are not substituted for duration
shares. The [ESMA taxonomy](https://www.esma.europa.eu/sites/default/files/2024-05/ESMA32-2009130576-3011_Final_Report_amending_RTS_on_ESEF_-_2024.pdf)
defines the two weighted-average share concepts separately.

Dimensionless revenue growth/acceleration and margin calculations accept monetary
facts in reported three-letter currency units. Match currency as well as duration
on every ratio and comparison; never mix or convert currencies. When multiple
complete currency views end on the same date, USD is preferred deterministically.
Absolute cash thresholds retain their USD requirement. Per-share units are not
revenue amounts.

Market calculations choose the latest declared series endpoint, independent of
input tuple order. At the same endpoint prefer the longest history only when all
shorter histories are identical suffixes. Conflicting same-endpoint prices fail
validation; neither arbitrary document ordering nor merging incompatible adjusted
series may select a result. Legacy metadata lacking an endpoint uses the document's
availability date. Existing resolver PIT filtering and numeric checks still apply.

## Executable function descriptions

The registered deterministic callable owns its input, measurement and parameter
description in its docstring. `deterministic_signal_function_contracts` projects
those descriptions for the actual supplied registry, including overrides; it
never substitutes a built-in description merely because the function name
matches. Missing documentation is explicit. These descriptions do not change
execution, thresholds, point-in-time checks, or candidate validation.

## Multi-target evaluation statistics (implemented for magnitude_ge3_v1)

Approved design direction (2026-09-21 action plan, gated behind the magnitude
data gate): Signal observation statistics remain direction-keyed and unchanged
— `SignalStats` state counters, `surge_rate`, observation identity, learning
events, and learned profiles keep their exact current semantics for the
`surge_direction` target. Any additional research target (for example a
magnitude-class contrast) gets a separate, version-bound target-evaluation
namespace: records are keyed by Signal version × target × evaluation protocol,
never mixed into the direction `surge` buckets. One physical Signal execution
accounts once for execution count, tokens, and cost; any number of target
evaluations may reference that same observation with their own evaluation
identity and result. Observation deduplication and target-evaluation
deduplication are separate idempotency rules, including across restarts.
Records that predate a target are unknown for it — never zero-filled and never
counted as support. The ge3 target passed its data gate on 2026-09-21 (user-confirmed thresholds
plus the post-backfill PIT re-audit), so its implementation is active:
`SignalTargetEvaluation` records (fields: evaluation_id, signal_ref,
target_id, evaluation_protocol, observation_key, result in
supported/contradicted/inconclusive/insufficient_evidence, created_at) are
appended idempotently by exact evaluation_id to the registry-level
`target_evaluations.jsonl`; `SignalRegistry.load_target_evaluations` filters
by exact Signal version and optional target; `target_support` summarizes a
target's records and returns None — unknown, never zero — when a Signal has
none. Direction statistics and surge_rate are untouched, and recording
evaluations never mutates SignalStats. Other targets remain unimplemented
until their own gate records pass; see `signal_evolution.md`.


### Committed-use target persistence

The tracking bridge appends `committed-use-observation-v1` protocol records for
committed exact-version executions. `inconclusive` describes observed use without
validated benefit; unavailable is `insufficient_evidence`. Independent paired
`supported` records are a separate protocol and keep their own meaning.
Batch target writes validate all types/refs and exact duplicate-id contents before
an atomic JSONL replacement preserving original rows. A late invalid item or an
interruption cannot leave a partial batch or silently replace an earlier verdict.
Learning-event duplicate ids likewise require exact content; duplicate physical
outcomes include realized multiple in conflict detection.


Shared soft-Signal batching preserves independently selected per-Signal evidence
views and citation scopes. Overflow splits retain single-Signal coverage; each
result and call has actual usage accounting. Unavailable after explicit limited
visibility remains distinct from a negative measurement. Whole-document fingerprints
remain the within-case no-op identity; cross-Plan observational conflicts do not prove
identical model-facing views or technical failures.
