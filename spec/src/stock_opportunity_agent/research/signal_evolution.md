# Signal and Dual-Loop Evolution

## V8 Slow Round self-evolution contract

The engine freezes `slow_input.json`, then appends or reuses one
`slow_memory.json`, then seals `slow_experiments.json` before staging validation.
All three artifacts are cycle-scoped, immutable, canonical-hash linked, and may
read only source artifacts reachable from committed Fast/Slow pointers. Raw
Signal usage events retain exact `signal_ref`; efficacy uses deduplicated
observation identity and does not infer causal credit from reflections.
For `slow_only`, the first target cycle also projects every namespaced artifact
listed by the validated Slow-history manifest from its local imported copy. The
source namespace is part of each feedback ref, and the source committed Slow
cutoff is carried into `slow_input.json`; importing only the Registry while
silently dropping committed search/validation outcomes is invalid.
Legacy monolithic validation/result files are projected as complete H, E,
Update, candidate and transition work units, each retaining the immutable source
artifact hash and JSON locator. A file larger than the role budget is never
string-truncated or treated as one permanently unreadable feedback unit.

The entry reflection is one bounded logical job over complete selected feedback
units plus historical pending units. No pending feedback means zero model calls
and a `reused` memory delta. Successful coverage alone advances
`processed_feedback_refs`; omitted or failed units remain pending. Raw episodes,
specific reflections, and evidence-linked method lessons coexist append-only.
Challenges qualify prior lessons through explicit refs and never overwrite them.
When the default complete-entry view defers sources, the role may make one typed
opaque-ref selection. Runtime validates scope and budget, replaces the default
batch with the selected complete entries, and keeps every unselected ref pending;
the final role call cannot request again. Selection and final request hashes are
both retained in the cycle audit.
Reflection output persists only each selected unit's top-level `feedback_ref`.
An out-of-scope Slow locator nested under exactly one selected unit is
deterministically rewritten to that owner ref, with the mapping retained in role
audit metadata and persisted under
`slow_memory.model_view_manifest.canonicalized_nested_refs`, with the provider
response unchanged; ambiguous or absent locators still fail. The persisted map
may point only to feedback refs processed by that memory delta. The adapter
aggregates every remaining invalid episode and lesson
row into one indexed correction frontier instead of consuming one retry per
malformed or out-of-scope ref.

Every cycle reserves one H batch when actionable and one independent E1/E2
batch. H failure, no hypothesis, or rejection cannot cancel E. E1 sees only PIT
development evidence; H1/H3/E2/Update receive role-scoped memory views through
one bounded source resolver. Each H1/H3 logical job, E1 microbatch, E2
comparison, Update target and candidate-validation state is retained as a
distinct experiment attempt, including no candidate and technical failure. A
model-backed attempt carries the ordered exact request hashes for its initial
request and every bounded correction; `usage_ref` points at the terminal request
while `request_refs` preserves the complete call chain. Pipeline summaries
cannot substitute for these work-granular attempts.

One frozen sampling manifest supplies issuer-disjoint dev/check identities to
H, E, Update, and effectiveness evaluation. Missing evidence does not substitute
another case. Candidate authoring and semantic review finish before candidate
hash and shared check corpus freeze. Validation adds definition-to-
implementation consistency, independent supporting/counter/unavailable
fixtures, and semantic duplicate checks without weakening existing gates.

`SlowLoopValidation` and `SlowLoopResult` bind the input, memory, experiment,
and sampling hashes. A result separately reports new candidate, validated new,
promoted new, and updated counts. Only committed promotions of new Signal ids
count toward `min_new_signals_per_cycle`.

## Purpose

Own Signal-learning aggregation, candidate validation/effectiveness, Slow
Update and Mining, and the finite dual-loop coordinator. It depends on
`evolution_core.py` and `plan_evolution.py`.

## Invariants

- Signal candidates validate before promotion. Paired effectiveness applies the
  same absolute directional-quality floor to new Signals and updates. Once a
  candidate has enough decisive observations, it cannot be promoted when its
  directionally correct count is less than or equal to its wrong count. An update
  must satisfy this floor before relative availability/correct/wrong improvements
  are considered; reducing errors only by abstaining does not turn a still-wrong
  candidate into an effective Registry version.
- Every Slow cycle runs bounded Signal Mining independently of whether the
  committed Fast boundary contains a new Signal need. H1 may use identity-masked,
  outcome-aware Fast meta-memory to propose error-driven measurements; the
  Exploration path independently extracts label-hidden point-in-time signatures
  and reveals the frozen positive/control labels only in E2. Fast demand augments
  this search but never gates it. A grounded `no_measurable_pattern` result is a
  semantic mining outcome, distinct from skipped work or technical failure.
  Slow sampling remains owned by the Discovery split. A separate identity-only
  inventory covers all approved non-Locked-Test development splits so a Fast
  backlog row originating from an Anchor case can still resolve its source owner
  and receive scoped brand masking. This inventory exposes neither outcomes nor
  evidence, and Locked Test is never loaded for identity masking.
- Update uses the same side-effect-free candidate checks during model correction
  and staging. Deterministic candidates may omit the optional null skill; LLM
  candidates still require a complete skill. Target identity, vNext and immutable
  definition constraints remain mandatory and visible in the request contract.
  The candidate schema exposes the complete version-owned retrieval policy rather
  than the legacy singular query alias. Update requests include a runtime-built
  complete vNext template copied from the stable spec, skill, and immutable
  non-empty executable fixtures plus the exact allowed `changed_paths`
  vocabulary. Candidate output preserves those fixtures byte-for-byte because
  tests are not a model-editable path. Candidate fixture execution uses the
  Registry audit's point-in-time defaults: when `published_at` is omitted,
  `available_at` is authoritative before falling back to the fixture `as_of`.
  Candidate retrieval fields overlay that
  baseline before parsing; omitted optional fields are therefore preserved.
  `changed_paths` must exactly match the effective mutable spec/skill differences.
  Candidate/diff correction may edit both coupled fields while preserving every
  unrelated decision field. Version and fixture changes are not substantive
  Signal changes and cannot create a staged candidate.
  The bounded correction path executes deterministic candidates against the
  immutable stable fixtures and reports all fixture failures as one candidate
  obligation. Soft-signal fixtures are not executed inside parsing because their
  provider usage must remain explicitly metered; they retain the normal staged
  validation boundary.
- Registry transitions remain version-bound and auditable.
- Slow-loop results and cycle completion preserve existing recovery semantics.
  If Mining or Update raises a locally handled validation failure, the engine
  emits a typed `slow_pipeline_failed` progress event with pipeline, error type,
  message, and usage before continuing the independent sibling pipeline. The
  failure remains in the durable validation audit; continuing Update must never
  make an earlier Mining failure invisible or look like the first Slow action.
  The same isolation boundary catches unforeseen ordinary exceptions without
  enumerating incident-specific corner cases: the affected memory or pipeline
  becomes a typed fail-closed result, consumes no unprocessed feedback, produces
  no candidate, and cannot promote a Signal, while an independent sibling may
  continue. Control-flow pauses, explicit client transport failures, process
  interrupts, and other `BaseException` states are never swallowed; they
  propagate so the frozen workspace can be resumed under its original budget
  and contract.
- The module never imports the `scheme_evolution.py` compatibility facade.
- H1 runtime fields are deterministic and cycle-bound. The committed audit
  stores the structured conclusion and an input fingerprint so a later cycle
  can distinguish changed evidence or search strategy from identical work.
  An identical prior `no_testable_hypothesis` or exhausted structured recovery
  suppresses the same H1 work; changed demand, visible capability, Registry,
  applicability inventory, visible Fast meta-memory, limits, contract, or model
  identity creates new work. H1 fingerprints the exact masked `meta_info` view
  it receives so new reflection cannot be suppressed by an older empty result.
  The fingerprint also includes the exact relevant point-in-time Raw Info
  identities, masked backlog, stable Registry, role protocol, and model work
  identity, while excluding cycle and proposal ids. A technical H1 failure is
  never semantic exhaustion and remains eligible after recovery under the
  existing attempt and cost ceilings. H1's complete runtime need set is the union
  of Fast `signal_need_items[*].need_ref` values, ordinary capability-backlog
  `items[*].request_id` values, and stable controller-derived action refs from
  retained vertical reflection. Reflection actions come only from explicit
  misleading-signal, repeated-failure, missing-information, and next-exploration
  fields. H1 classifies each action honestly: Signal-scoped work uses
  `new_measurement`, `deferred_measurement`, `update_existing`,
  `repair_dependency`, or an intrinsically
  justified `not_testable`; a retrieval, analysis, or prediction-policy action
  uses `fast_plan_action`. That last disposition is valid only for a projected
  reflection action because the same original reflection already flows directly
  through meta-memory to the next Fast proposer. Ordinary Signal/capability needs
  cannot be diverted out of Slow with it.
  The bounded projection records available/projected/omitted counts and orders
  explicit next explorations before diagnostic fields so a field-order cap cannot
  silently discard every proposed action. Reflection presence never forces a
  fabricated factor: when H1 has no honest new measurement, the independent
  E1/E2 positive/control comparison remains the Slow discovery path.
  Ordinary backlog rows must not be dropped merely because they are provider,
  retrieval, or existing-Signal coverage gaps.
  The role adapter may use deterministic compact need aliases on the wire, but
  committed H1 audit always restores the original need refs and includes the
  local alias map. Thus downstream H2/H3 audit and Fast-to-Slow provenance never
  depend on model-facing transport identifiers.
- Exploration extraction runs in bounded microbatches keyed by stable case refs.
  A failed microbatch cannot discard valid sibling signatures or become a
  domain observation. The full frozen E1 cohort, failed refs, and usage remain
  visible; E2 runs only if both fixed groups still meet the configured grounded
  evidence floor, without replacing validation cases.
  E2 receives only the runtime-selected grounded induction signatures. A
  semantic zero-candidate result records its limited reason and exactly those
  considered refs; unrelated E1 pool members and holdout cases remain absent.
  E2 decisions describe repeated cross-case patterns rather than case-by-case
  acceptance. A model response containing only per-case rejection rows is a
  correctable output-shape failure, not a technical claim that mining found a
  candidate and not a locally invented semantic result. Locally checkable claims
  about the supplied cohort, including whether any selected case is unlabeled,
  must match the actual E2 payload before an empty result is persisted. The same
  guard rejects rationale or observable-difference claims about sector,
  industry, business model, market-cap class, geography, or listing venue when
  that attribute vocabulary is absent from the literal source-owned signatures;
  bounded correction preserves the decision/no-candidate intent while removing
  or grounding only the unsupported claim.
  A rationale that names a concrete missing, absent, truncated, partial, or
  unavailable source input is grounded only when it is a canonical
  `[case_ref] <verbatim evidence_gaps item>` citation from the selected E2
  signatures. An uncited or paraphrased source-gap assertion is a correctable
  semantic failure. A generic insufficiency conclusion that does not claim a
  particular absent input does not require such a citation.
  After bounded model correction, E1 may quarantine invalid observations while
  preserving independently validated observations and sibling signatures. It
  never clips or invents source text. Quarantine reasons remain technical audit
  metadata, including when a case has no surviving observations; they are not
  evidence that the source or measured condition is absent.
  E2 never receives E1's model-authored summaries as evidence. The controller
  replaces them with a deterministic literal-only view before labels are
  revealed; the original summaries remain in E1 audit only. For an observation
  that maps unambiguously to a supplied SEC Company Facts record, this view keeps
  the source-owned taxonomy, concept, label, and unit beside the literal span and
  deterministically adds the other supplied period for that concept when the
  selected span identifies exactly one record. This bounded companion is source
  projection, not a model-authored observation.
  Queryless extraction prefers a same-concept two-period pair before unrelated
  one-period structured facts. Generic filing
  cover/legal boilerplate is not a comparison-ready observation and is
  quarantined like any other locally invalid E1 observation.
  Source-owned SEC Company Facts context retains each concept's original
  `label` as metric semantics; the transport guard distinguishes this exact path
  from retrospective outcome labels. A runtime budget exception during E1 is
  propagated unchanged to the cycle controller and is never converted into an
  E1 validation failure or masked by a missing exception binding.
  Queryless E1 considers the resolver's exact available source-type catalog; it
  must not discard filings or transcripts through plural aliases that do not
  exist in that catalog. Its bounded evidence selector prefers the most recent
  document from a previously unseen semantic source family before selecting a
  second document from the same family. This keeps filing, transcript, news,
  Company-Facts/financial, and market evidence complementary without increasing
  the document ceiling. Within a queryless Company Facts document, the bounded
  projection ranks recent members of a frozen catalog of broadly comparable
  operating, balance-sheet, investment, and capital-structure concepts ahead of
  stale or arbitrary concepts, then uses deterministic tie-breakers. Exploration
  receives a larger bounded projection than query-directed H3. Queryless filing
  windows deterministically prefer substantive business, results, liquidity,
  risk, and outlook language over cover-page boilerplate; queryless JSON windows
  start at a complete record boundary.
  This changes evidence projection only: it does not define a Signal or use
  labels. Query-directed H2/H3 ranking retains its query-coverage semantics.
- Update evidence packets separate label-free source observations from the
  locally computed outcome relation. Model diagnostics must cite a supplied
  document ref and literal span for every fact before an update draft can be
  considered; source facts are stored as literals without a model-authored
  claim. Mining decisions persist the runtime-derived positive/control sample
  basis used for their statistical association.
- Mining anonymizes persisted meta reflections, backlog prose, and prior Slow
  work before assembling the guarded model context. Persisted originals remain
  unchanged; the outgoing identity guard remains mandatory.
  One- and two-character ticker aliases require an explicit dollar, ticker,
  symbol, or exchange marker in prose; standalone letters and quarter notation
  are not issuer identities. Full company names remain masked.
  Candidate validation uses the same case-preserving strict matchers as outgoing
  contexts: an ordinary lowercase word must not become an uppercase ticker merely
  because the complete candidate was case-folded. Full names retain case-insensitive
  matching; explicit ticker and symbol markers retain their existing treatment.
  Exploration first applies expanded identity masking for its one local case and
  then the strict aggregate guard. This masks a natural one-token brand derived
  from a formal legal name without teaching an aggregate role to treat ordinary
  one-token vocabulary as identities. All Slow contexts (meta, profiles,
  H3/Exploration source projections, and Update packets) consume the strict
  aggregate inventory without deriving new first-word brands. Local case masking
  keeps its own alias expansion. Repeated
  identical inventories reuse a bounded compiled-matcher cache; literal source
  checks and final identity scans remain in place.
- Ordinary Fast-to-Slow demand comes from the final unresolved needs of every
  trajectory in committed Plan records, with stable need refs, exact source
  round/fingerprint provenance, and the real terminal reason. Technical Signal
  execution failures are separate diagnostics and never domain learning.
  Mining receives the complete retained, masked meta FIFO; blind extraction,
  Signal execution, and prediction do not receive retrospective meta.
- Update induction buckets accept only successful execution and explicit domain
  unavailability. Provider, parser, budget, and other technical failures retain
  their usage and audit records but never become unavailable learning. Explicit
  misleading targets prefer wrong Discovery cases and may use sourced domain-
  unavailable Discovery cases for applicability or retrieval diagnosis when the
  wrong pool is insufficient; Validation cases never refill that pool and the
  issuer-disjoint holdout minimum remains unchanged. Machine counts derive from
  structured evidence verdicts and outcome relations, not rationale prose.
  Update work keys use the full role/model identity. A substantive committed
  `no_change` may suppress identical work, while defer and technical obstruction
  remain eligible for a later bounded retry.
- Update assigns opaque document refs before masking source text, so the current
  result and its executed evidence resolve to the same supplied document. Literal
  facts have no field-length ceiling; exact source membership and the existing
  response transport budgets remain required. A long valid quote is not a missing
  evidence error. Runtime outcome relations remain authoritative.
- Every staged Slow validation records a `search_input_fingerprint` over the
  input Registry, relevant point-in-time Raw Info identities, Discovery case
  identities, capability backlog, meta context, Mining limits, and Mining/Update
  model identities. Cycle ids and model-authored proposal ids are excluded.
  This fingerprint diagnoses repeated search separately from changed-input
  retries; it does not turn a no-candidate result into a domain failure.
- Each H3 hypothesis comparison also records a cycle-independent work
  fingerprint over the structured hypothesis without its runtime proposal id,
  the exact visible induction packets, frozen validation case identities,
  Registry input, Mining protocol, and model identity. A committed terminal
  `refine`, `rejected`, `inconclusive`, evidence-unavailable, or locally invalid
  candidate result suppresses only the identical comparison in later cycles.
  Changed evidence, cohort, Registry, model, protocol, or structured hypothesis
  creates new work; unaffected sibling hypotheses continue in the same batch.
  The model-facing H3 payload nests those exact packets under their owning
  comparison; no global packet pool is exposed. E2 likewise receives bounded
  runtime-owned decision slots and must bind each supported candidate to explicit
  positive and control refs from the supplied grounded cohort. The persisted
  sample basis is that validated binding, while holdout selection remains local
  and hidden. E1 audit gaps do not globally force `insufficient_evidence` after
  both fixed groups have enough surviving comparison-ready signatures.
