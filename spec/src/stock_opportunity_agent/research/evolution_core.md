# Evolution Core

The pure bounded-portfolio helper preserves routing order while applying the
existing per-round total and LLM Signal caps. Production and direct-stage
diagnostics share it; raw routing decisions remain separately auditable.

Final-context construction validates every complete SignalResult against the
actual prediction instant before producing model-facing summaries, measurements
or citations. Known bad results reject construction as typed technical/PIT
input failure; accepted state scope does not override this. Compact result
cards retain only an ephemeral `input_evidence_available_at` list copied from
the validated canonical evidence, bound by the existing `signal_ref`. This is
runtime provenance for subsequent temporal revalidation, not a new canonical
Signal schema, source-authenticity verdict or trust/signature system. Existing
completed artifacts remain immutable.

## Actual answer-scope provenance (2026-10-19)

Successful Reflect steps may carry `need_dispositions` metadata with a canonical
`prior_state_hash` and validated `items` (including `prior_need`). Runtime appends
that metadata to the corresponding ordinary or terminal `state_deltas` entry.
Trajectory serialization/reload preserves it, and the existing final-context
`state_evolution` block forwards it unchanged. Compact posthoc and Plan-critic
case views retain the same actual answer dispositions so Routing's expected
scope cannot replace what Reflect accepted. Legacy trajectories without this
metadata remain readable and receive no invented historical dispositions.

This is additive audit metadata, not a ninth permanent ResearchState field,
an altered completion pointer, or proof that the authored answer is correct.

## Committed Signal use identity

The shared producer derives v2 learning events from the canonical serialized
immutable Plan record hash and original case/Signal/result positions. It records
source binding separately from the unchanged physical observation key. Hashing
JSON formatting is irrelevant; canonical record reload must reproduce identities.
Only pointer-reachable records are eligible for production publication. Import
of existing events preserves their version and bytes; a new read-only committed
Fast bootstrap derives source-bound events without rewriting the source ledger.

Runtime passes the exact frozen Signal research status to controllers that expose
`set_signal_research_status`. Current-batch Reflect and actual-result Predictor
views carry version-bound technical/effect status, with no retrospective labels
or effect examples. The final-context assembler accepts optional status metadata
and includes it only for actually executed refs; preflight and transmission use
the same assembled view. Existing canonical SignalResult and ResearchState stay
unchanged. Generic controllers without this optional interface remain valid.
Actual-result status is recursively projected to independent plain JSON before
Predictor assembly, preserving the deep immutability of its Registry source.
Final Signal cards retain each round's runtime-owned `execution.status` from
that round's result, alongside domain coverage. Technical execution failure is
distinct from domain-unavailable evidence. Later execution of the same version
must not overwrite earlier round cards; archived originals remain unchanged.

`CaseReflectionEvidence.recorded_signal_execution_failures` is optional runtime
audit metadata carried into Plan/round meta and Slow source reads. Each entry
contains the actual one-based Signal round, exact `signal_ref`, and technical
`status`; success and domain-unavailable results are not failure entries. Runtime
derives entries from immutable trajectory results, never reflection prose.
Missing legacy metadata stays unknown. An empty list means no recorded failure,
not proof of error-free historical execution. This metadata changes neither
case outcome attribution nor scoring and does not discard valid domain results.
Trajectory reconstruction emits this metadata only when its saved final-context
Signal cards explicitly record all corresponding round/ref execution statuses.
An older final context without those records keeps the field absent, even if
typed SignalResult rows can now be inspected separately. Otherwise reconstructing
old source units changes content hashes (and legacy case membership), breaking
already-authored references. New runtime contexts provide the complete status
records; restart/archive projections preserve that producer evidence exactly.

Final Basic Info cards retain the upstream `document_id` and `available_at` beside
the complete literal and stable projection id. Final context explicitly includes
the actual `prediction_time`; consumers must not infer it from optional price
cards. Missing legacy metadata stays missing, never invented. The near-tautological
recent-close/doubling-threshold ratio is omitted from newly computed baseline
blocks; mean, threshold and the dated recent close remain unchanged. This does
not change outcome labels or the registered distance computation tool.

The fixed Predictor price baseline is computed from complete, hash-verified,
point-in-time market documents selected by Basic Info resolution. Source excerpts
and model projection budgets affect presentation only, never its five-row window.

## Purpose

`InformationPlan.experience_usage` is optional runtime audit metadata containing
the exact disclosed-view `snapshot_hash` and explicitly adopted `item_refs`.
It is persisted with staged proposals, Plan records and additive meta, but is
excluded from the four-part canonical strategy/embedding. Absent legacy metadata
is unknown consumption; an explicit empty list is known non-adoption. Refs are
bounded content-addressed Experience identities and never contain outcome prose.

Optional `PlanRecord.knowledge_signal_refs` is the exact frozen callable version
menu for the evaluation. Runtime owns it; legacy absent menus stay unknown and
cannot be treated as unused controls. It is audit metadata, not a fitness term.

Own immutable evolution records, validation, scoring, evaluation-dataset
selection, role protocols, and pure research helpers. It has no workspace or
Fast/Slow engine dependency.

## Invariants

- The research loop carries an improvised retrieval channel alongside
  frozen-policy Signal execution: every H_reflect call receives a bounded
  point-in-time `document_catalog` view (disclosure interface cards) and
  may spend at most two mid-call exchanges shared by catalog paging,
  document fetching and deterministic computation. `inspect_document_catalog`
  takes an integer `cursor` in the existing catalog's eligible range; a copied
  `next_cursor` advances sequentially and another valid offset addresses a
  later page directly within the same budget. Fetches contain at most two
  supplied entries each — bounded views of documents or exact sections,
  resolved through the disclosure interface with deduplication and
  journaling by ordinary caller persistence. Fetched views arrive in
  `document_channel` with content-addressed provenance and reach the final
  Predictor unchanged. Reading does not mint a ResearchState evidence kind or
  projection: State citations still require existing Basic Info or Signal refs.
  The provider enforces both the case company and cutoff on every fetch before
  persisting any views. Catalog pages and fetched views survive ordinary semantic
  correction; mechanical-only correction exposes no read actions. Signals keep their frozen
  retrieval policies for cross-case comparability.
- The assembled final context is a typed append-only artifact:
  `basic_info.projection_cards` preserve every bootstrap projection already
  disclosed to the controller, with its complete visible text and stable ID.
  The upstream projection budget still limits source disclosure; final assembly
  must not apply a second prefix/tail cut that loses already-visible evidence.
  `context_contract.assembly_blocks` records the typed block
  order and restricts numeric decision inputs to computed blocks. A
  `state_evolution` block appends each round's deterministic state delta —
  added/removed rows per field, evidence added by stable ref key with its
  claim, removed keys, and decision transitions — so every authored number
  and belief is attributable to the round that introduced it; the
  trajectory persists the same per-round deltas.

- Computation before interpretation: the case runtime derives one evaluation
  anchor block from complete point-in-time market documents (five-day mean
  adjusted close plus deterministic derived facts — doubling threshold,
  most recent close and date, ratio to threshold). The anchor is disclosed
  verbatim in the H_init and H_reflect payloads as control data and reused
  in the assembled final context; the research-state validator rejects
  authored text that restates a different baseline value or derives a
  wrong multiple of it, with the same pattern family as the predictor's
  baseline arithmetic check but running before prediction.

- Persisted Jev probability distributions yield deterministic per-case
  calibration feedback and derived cross-case summaries. Legacy trajectories
  whose saved Jev feedback predates the calibration sub-block remain loadable;
  every supplied legacy value must still exactly match the deterministic legacy
  projection. New serialization emits the enriched record. These diagnostics do
  not change labels, fitness, parent selection, or promotion.

- Queryless filing windows rank distinct substantive term coverage, not repeated
  mentions of generic business/risk words. The existing filing source-family
  catalog owns alias handling, including foreign and current-report forms.
  Projection preserves literal text and point-in-time boundaries.
- `AgentStep` may carry bounded, non-authoritative role metadata alongside its
  value and usage. Controllers persist only the metadata fields defined by the
  owning role contract; metadata never changes domain success or commit state.
- A rejected candidate role may attach structured diagnostic details for
  persistence. These details explain failed work and its input identity; they
  never convert the rejection into a domain result or widen recovery scope.
- Stable-item correction may add one explicitly missing item only when its
  structured issue names the runtime-owned item ID and grants `add`. Existing
  siblings are copied from the failed response, so a correction cannot rewrite
  them while filling the omission.

- Point-in-time and identity masking rules remain fail closed.
  One- and two-character ticker aliases in prose require an explicit dollar,
  ticker, symbol, or exchange marker. Securities-table order also qualifies:
  a known short code immediately before a named US exchange (optionally with
  a /preferred-series suffix) and Trading Symbol(s) labels are explicit identity
  positions. Only the identity literal is projected in table order; surrounding
  security terms and exchange wording retain their meaning. Unmarked ordinary
  abbreviations remain untouched. This matches the outgoing transport guard
  and preserves ordinary text such as Gen Z, Q2, and AI. Full names and longer
  ticker aliases retain their existing identity handling.
  Explicit identity fields and `known_aliases` array members always project exact
  known identities, including short tickers; the exception is limited to prose.
  URL path/query identity matching remains case-insensitive for short tickers;
  JSON metadata embedded in a source string is also explicit: known short values
  of ticker/symbol/company_id project case-insensitively. Preserve the surrounding
  key, delimiters, whitespace and numbers rather than parsing or rewriting source
  JSON. Non-identity fields with the same abbreviation remain ordinary text.
  the prose exception does not expose identities in source links.
  Derived single-word brands do not erase ordinary business vocabulary such
  as energy, green, life, travel or critical; complete company names and explicit
  supplied aliases retain their identity handling.
  Shared masking/projection helpers accept an explicit strict-inventory mode
  for aggregate Slow roles, avoiding repeated brand derivation. A bounded cache
  reuses compiled patterns for identical inventory/mode pairs.
  In expanded case scope, brands derived from multi-token formal company names
  match prose case-insensitively even when the source name is all caps and the
  brand is five letters or fewer. Exact ticker-only aliases keep their existing
  case-sensitive prose rules; strict aggregate inventories do not derive brands.
- Each execution injects the actual timezone-aware prediction time into both
  controller and Signal retrieval adapters that expose the optional
  `set_evaluation_context` hook, before any role call. Reusing adapters across
  cases replaces that context; adapters without the hook remain compatible.
  Routing never substitutes a fabricated date or infers it from need wording.
- Record serialization stays explicit and schema-compatible.
- Scoring and fitness rules remain deterministic.
- When an already executed, reflectable batch cannot fit an ordinary reflection
  into the adaptive budget, consume any paid usage and attempt that same batch
  once in terminal mode with the remaining budget after protecting the actual
  Predictor reservation. Reapply the existing
  mandatory-finalize validation; never fabricate a finalized state. A failed
  terminal reservation remains budget-exhausted, without another retry. This
  fallback does not apply when no batch exists or when already in terminal mode.
- A Predictor with `estimate_prediction_tokens(context)` estimates the same
  composed, anonymous request used for actual prediction. Recompute this
  reservation before routing, execution and reflection from the complete current
  evidence closure. Adaptive research protects that reservation plus the existing
  finalization floor; terminal reflection protects the Predictor reservation
  itself. No source is cropped to fit, no limit is increased, and an unsendable
  terminal reflection preserves the paid batch and records budget exhaustion.
  Adapters without an estimator retain the existing fixed-floor behavior.
  If a later routing preflight or loop limit stops a still-continuing collection
  after a completed ordinary reflection, attempt the retained batch once in
  terminal mode. No stale selection owns the current needs: this closure uses
  empty selection intents and preserves unresolved needs. An already attempted
  terminal reflection is never repeated. Complete ordinary validators still
  require a real finalized model state; failure remains unfinalized.
  A budget-skipped posthoc reflection still consumes any paid usage carried by
  the exception; its diagnostic fallback cannot erase spent calls or cost.
- The final assembly also retains bootstrap computed metrics and runtime-acquired
  document/compute views from the bounded reflection channel. These case-local
  views keep their PIT provenance; failed or repeated calls never reset them.
  They are included in the same budget estimate, masked at egress and persisted
  in the final context. No controller-authored numerical substitution is used.
  Case initialization resets optional controller compute context even when the
  bootstrap has no usable market metric, preventing cross-case window reuse.
- The module may depend on Raw Info and Signal contracts, but not on Plan or
  Signal engine implementations.

ResearchEvidenceRef claims require nonempty text and have no hard character ceiling.
Length is presentation guidance; evidence validation and transport budgets remain
independent. Existing serialized record shapes are unchanged.

Predictor's 24KB display target is advisory; complete validated state and citation
material cross this boundary unchanged, with target overflow explicitly recorded.
Hard request/case/cost limits remain enforced by transport. Original meta entries
and case reflections remain archived in full. Optional structured reflection
items and unchanged lower-item selections are additive fields; legacy artifacts
retain their original serialized shape. Meta memory exposes a separate bounded
brief catalog and exact reference-read API through `evolution_reflection_memory`.
Consumers mask and scan approved views, enforce their byte/read budgets, and use
exact request reservation. Deferred items remain visible in the manifest rather
than being treated as processed or silently dropped. The full archival view stays
available as `archive_view()` for persistence and offline audit; `model_view()`
returns the bounded brief dictionary. Blind roles cannot read the index.

For the supported SEC Company Facts response shape, model-facing document views
preserve taxonomy concept, provider label, unit, and up to the latest necessary
distinct reporting periods together. Every visible record carries its complete
literal raw JSON span and raw start/end offsets; wrapper fields explain meaning
but are not independently citable facts. Ambiguous raw matches, future-filed
records, unknown shapes, and budget omissions remain explicitly partial. The
combined structured view, including parent fields and record literals, stays
inside the existing document character bound and does not alter Raw Info.
After ordinary target aliases are masked, a proper-name phrase explicitly described
as a division, subsidiary, brand, business, unit, or segment of the masked target is
also masked in model-facing evidence. This relation-based rule covers target
affiliates absent from Basic Info without suppressing unrelated third-party names.

## Fixed Slow priors follow active role ownership

Human-maintained fixed Mining/Update priors describe the structured runtime,
not the retired model-owned tool workflow. Runtime owns sampling, stage-specific
label visibility, staging, fixtures, holdouts and promotion. Mining roles propose
measurements or decisions appropriate to their stage; Update returns one of
no_change/defer/update for the supplied target. Models do not return invented
staged refs. All Mining stage payloads carry the same fixed Mining prior. Changes
to this code-owned prior require a freshly frozen priors hash and workspace.


Bounded evidence windows end at a complete whitespace-delimited token when the
character budget would otherwise split a word or numeric amount. The excerpt
remains a contiguous source substring; no text is synthesized and the original
truncation marker remains true. This avoids literal-but-incomplete token evidence.

## Daily boundary and Basic Info visibility

The fixed five-close baseline uses observation dates strictly before the UTC
day of the aware prediction instant. Offset spelling cannot change its window.
This does not change the five-session definition, doubling threshold or source
availability filtering.

Basic Info has two bounded presentation stages: resolver context selection and
normalized model projection. Runtime model rows record separate
`source_context_truncated` and `projection_context_truncated` booleans (null
means unknown), plus their three-valued `effective_context_truncated`. Any
known omission or omission marker makes the effective value true; false
requires both stages explicitly false. Existing projection counts describe
only the normalized projection candidates, never all source observations. A
visible row with known upstream omissions is `partial_context_budget`; absent
upstream knowledge cannot produce a `complete` claim (`visibility_unknown`).
Source status, data gaps and current-level counts retain their distinct meaning.

A shared compact visibility projection preserves those flags, counts, status,
projection ids and bounded `omitted_context_markers` through final source index,
both posthoc input forms, and saved-trajectory critic views. Markers remain
discovery hints rather than evidence/citation authority and pass existing
identity masking. No complete source body is copied into these summaries.
Legacy saved rows retain unknown stage fields; old archives are not rewritten.

## Runtime termination disclosure

New core-produced final contexts carry a runtime-owned `runtime_termination`
block with exactly phase, stop_reason and termination_trigger. Phase is
`research_in_progress` for prediction-token reservation views; both enum fields
are null there even though the loop's internal stop_reason initially defaults
to finalized. Phase becomes `prediction_ready` only after actual collection and
terminal reflection end; stop_reason is then the actual RuntimeStopReason value
and termination_trigger retains its independent actual enum value or null.
ResearchState.decision remains a separate controller decision: a finalized state
can retain unanswered needs or have been prompted by no-match/round/budget
limits. A continuing state forced to predict by a limit can also be ready.
No completion/outcome/need-closure inference follows from this block.

The private assembler accepts an optional validated block. Omitted legacy
arguments/contexts remain without it (unknown), and archived contexts are not
rewritten. The core supplies it directly rather than an observer deriving it.
Modern posthoc compaction retains the block exactly; legacy compaction does not
invent it or change legacy source identity. Critic keeps its already recorded
trajectory stop reason and trigger without a duplicate context block.

A shared pure runtime_termination_view validator requires the exact three-key
shape, a recognized phase, and existing enum values/nulls. Explicit in-progress
blocks are accepted for estimation but rejected before actual Predictor or
Posthoc dispatch. Present malformed/null blocks fail on the typed
RuntimeTerminationInputRejected control-flow boundary, bypassing content
correction, Plan rejection and research conclusions. Missing legacy blocks
remain compatible unknowns.

New bootstrap execution uses the shared [orientation compiler](basic_info_orientation.md)
before resolving any Basic Info. Stored legacy Plan decoding remains separate
from admission to a new run. Runtime uses fixed compiled recipes, never a free
Plan query; raw source/request primitives remain available to deep research.
