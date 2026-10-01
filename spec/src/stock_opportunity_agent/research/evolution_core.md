# Evolution Core

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

Own immutable evolution records, validation, scoring, evaluation-dataset
selection, role protocols, and pure research helpers. It has no workspace or
Fast/Slow engine dependency.

## Invariants

- The research loop carries an improvised retrieval channel alongside
  frozen-policy Signal execution: every H_reflect call receives a bounded
  point-in-time `document_catalog` view (disclosure interface cards) and
  may spend at most two mid-call `fetch_documents` exchanges of two
  supplied catalog entries each — complete documents or exact sections,
  resolved through the disclosure interface with deduplication and
  journaling by ordinary caller persistence. Fetched views arrive in
  `document_channel` as citable evidence; Signals keep their frozen
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
  ticker, symbol, or exchange marker. This matches the outgoing transport guard
  and preserves ordinary text such as Gen Z, Q2, and AI. Full names and longer
  ticker aliases retain their existing identity handling.
  URL path/query identity matching remains case-insensitive for short tickers;
  the prose exception does not expose identities in source links.
  Derived single-word brands do not erase ordinary business vocabulary such
  as energy, green, life, travel or critical; complete company names and explicit
  supplied aliases retain their identity handling.
  Shared masking/projection helpers accept an explicit strict-inventory mode
  for aggregate Slow roles, avoiding repeated brand derivation. A bounded cache
  reuses compiled patterns for identical inventory/mode pairs.
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
