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
    learning/
      events.jsonl    # append-only committed Fast observations
      profile.json    # rebuildable bounded routing summary
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

`freeze()` returns one immutable definition snapshot/hash plus a separately
hashed snapshot of the current learned profiles. Definitions and learned
profiles therefore have distinct identities: observations do not create a new
stable Signal version, but changing a profile changes the exact Fast execution
input and prevents stale trajectory reuse. Stats and learning events may keep
accumulating after a snapshot is frozen; that Fast group continues to see its
original profile snapshot, and stable definitions cannot change until it ends.
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

Revenue aliases include both `RevenueFromContractWithCustomerExcludingAssessedTax`
and `RevenueFromContractWithCustomerIncludingAssessedTax`; a company changing
between those standard concepts must not make a current case fall back to an older
legacy `Revenues` fact. For every duration/balance financial primitive, the newest
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
proof of diversified adoption.

A shared soft-Signal provider call deduplicates source text across at most two
Signals, but document eligibility remains per Signal. Each model-facing Signal entry
therefore includes `eligible_projection_ids`; evidence mapping rejects any citation
outside the matching list even when that projection is visible because the peer
Signal contributed it. Shared context is a transport optimization, not an expansion
of either Signal's Raw Info boundary.

`unavailable` is a coverage state, never evidence that the measured condition
is absent. The complete model-returned interpretation remains durable in the
canonical `SignalResult` for audit, but every downstream model-facing view
(routing history, H_reflect, Predictor/post-hoc, critic/meta, and Slow inputs)
replaces it with one deterministic coverage statement: visible evidence was
insufficient for a canonical conclusion and this is not evidence of absence.
An unavailable Signal cannot create a supporting/counter claim or resolve a
research question.

A Signal version may declare a small `routing_need_phrases` string array inside
`parameters`. These phrases are conservative direct matches, not fuzzy search
terms. They are exposed on the compact card and used only to reject an empty
selection once for model correction; runtime still never chooses the Signal.
The seed `guidance_acceleration:v1` declares `guidance` because an explicit
request for guidance updates is a direct match even though the versioned ref has
only two semantic words. Unmatched empty selection remains valid.

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
the Signal. A stable event id makes restore reconciliation idempotent.
`observation_key = (case_id, signal_ref, input fingerprint)` deduplicates the
state/outcome effectiveness matrix across Plans, while each Plan's selection
reason remains in the raw event stream. No event from an uncommitted round may
enter this ledger.

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

Candidate drafts are immutable once validated. An exact replay reuses its saved
validation. If a rejected `vNext` is later repaired, the rejected draft is moved
under the candidate archive by its content/origin hash before the replacement
draft occupies the active `vNext` path; this preserves audit history without
permanently blocking that stable Signal from ever proposing the same next
version. An already promoted ref returned by a later agent is ignored as
already stable rather than revalidated or promoted twice.

An update creates `vNext`; it never overwrites a stable version or edits the
old version's learning history. Machine
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

Candidate validation has three durable dispositions. `promoted` means both the
candidate contract and the independent paired effectiveness gate pass.
`provisional` means the contract passes and induction evidence is directionally
supportive, but independent point-in-time availability or decisive support is
below the existing promotion floor; the draft remains isolated under
`signals_candidates/` and may be re-ranked or re-evaluated in a later Slow
cycle. `rejected` means the contract fails, independent evidence contradicts
the expected direction, or an update regresses/fails to improve once evidence
is sufficient. Provisional never mutates the stable Registry and never weakens
the promotion threshold.

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
