# Evolution Signal Roles

## V8 reflection and source-read roles

`signal_mining_reflect` consumes complete, runtime-selected committed feedback
units and returns only new episode reflections and lesson additions. Runtime
preassigns episode/lesson refs and validates complete source coverage and the
lesson reference graph. `appended`, `no_new_lesson`, `reused`, and `failed` are
distinct terminal states; invalid structured output is never converted to a
research-empty result.
Only top-level `feedback_units[*].feedback_ref` values are persisted as output
citations. Source locators nested inside a feedback unit remain immutable audit
data; the model cannot promote them into independent episode or lesson refs
merely because their strings are visible. When an out-of-scope nested Slow ref
occurs inside exactly one selected feedback unit, the adapter deterministically
canonicalizes it to that owning top-level `feedback_ref`, deduplicates the
resulting ref list, and records the old-to-owner mapping in role metadata. The
raw provider response remains immutable. Ambiguous or absent nested refs are not
repaired. All remaining invalid episode and lesson rows are reported together as
indexed, path-scoped correction obligations, so bounded recovery does not
discover one bad ref per attempt. The same correction frontier includes the
complete set of selected top-level feedback refs omitted by otherwise-valid
episodes; coverage is validated inside the adapter before success, rather than
being discovered only by the engine after the bounded correction opportunity.
Coverage correction is slot-aware: when unused episode slots remain it may add
an episode, while a full slot set may only merge omitted refs and their existing
model-authored reflection into a supplied slot. After both bounded corrections,
the final catch may deterministically merge an otherwise-valid overflow episode
into an existing valid episode, preserving both reflection texts, questions and
source refs. It never invents reflection text or marks an absent ref processed;
anything less remains a failed memory delta and stays pending.

Reflection, H1, H3, E2, and Update may make at most one typed
`read_source_refs` request per logical job. The runtime resolves opaque refs only
within the role scope and whole-entry budget, records included/deferred refs and
hashes, and then asks for the final output. The selection request sees only the
role name plus opaque refs, hashes and current included/deferred membership; it
does not receive hidden source contents. A non-empty valid selection replaces
the default bounded view as one complete-entry batch, and every unselected
default item remains explicitly pending. An empty selection retains the default
view. There is no second selection round. E1, SignalExecutor, and blind
Predictor have no such access. Prompt, parser, work identity, persisted request,
provider body, and wire bytes advance together to their v8 protocol versions.
The transport appends every canonical request hash to an invocation trace. Role
adapters attach the slice produced by that logical job to successful
`AgentStep.metadata`; exhausted structured recovery attaches the same slice to
`CandidateExecutionRejected.details`, so experiment sealing cannot lose failed
or correction calls.

H1 may propose autonomous hypotheses with no Fast need ref and may route an
exact, per-need `update_existing` basis into the bounded Update queue. Unselected
or measurable-overflow needs remain pending. E2 receives the same allowed method
context and stable Signal catalog so it can avoid duplicates, but it must retain
fixed missing cases and cite the literal E1 evidence used for comparison.
H1 performs an exact wire-size reservation before transmission. If its complete
bounded payload exceeds the frozen per-request ceiling, it raises a typed local
candidate-execution rejection with zero usage and the required/limit sizes.
This is not an external transport failure or run-wide budget exhaustion: the
Slow controller records the H attempt as technical failure and continues the
independent Exploration sibling.

## Purpose

Implement structured adapters for deterministic/LLM Signal execution, Signal
mining, and Signal update proposals.

## Invariants

- Candidate execution is evidence-backed and cannot promote a Signal.
- Mining and update output remains bounded by the frozen contract.
- Promotion authority stays in the Slow engine after machine validation.
- Update candidate shape and immutable-field checks run inside the existing
  bounded correction loop, using the same validator as staging. E1's terminal
  fallback removes only observations that fail independent source validation;
  remaining signatures pass the full parser again and carry quarantine metadata.
- Shared soft-Signal source projections rank chunks by each Signal's versioned
  retrieval query and declared evidence phrases, not extraction-instruction prose.
  Selection alternates between Signals and prefers an unseen eligible document
  before another chunk from the same document. The shared character budget,
  deterministic ordering, exact raw-span lineage and per-Signal citation scope
  remain unchanged. A bounded view cannot prove absent data; unavailable results
  must remain distinct from technical failures and negative domain observations.
- Every shared payload declares each Signal's own eligible projection refs.
  Initial validation isolates omitted, cross-Signal, edge, and shape failures;
  its sole correction contains only failed Signals, their eligible evidence,
  and their feedback, while accepted siblings are retained without re-execution.
  A semantically unavailable result may consume that same single correction only
  when a declared comparison need or a truncated projection makes one bounded
  local re-projection meaningful. Exact request estimation and the original hard
  token ceiling apply before the correction; unchanged insufficient input remains
  unavailable rather than entering another retry loop.
- Production H1 uses `signal-mining-hypothesis-v7`. The runtime supplies stable
  proposal refs, the fixed Discovery comparison, and the evidence lookback;
  the model supplies a structured measurement, canonical applicability,
  expected direction, retrieval intent, and falsifiers. Semantic validity must
  not depend on lexical overlap between an identifier, prose, and a query.
- Every supplied backlog need ref appears exactly once in a bounded H1
  disposition: new measurement, update existing, repair dependency, already
  covered, not testable, or (for projected reflection actions only) Fast Plan
  action. Fast-derived Signal needs use
  `signal_need_items[*].need_ref`; provider, retrieval, and required-coverage
  backlog rows use their supplied `items[*].request_id` as the H1 need ref.
  Referenced existing Signals must be in the stable catalog. H1 may still return
  a structured `no_testable_hypothesis`, including for pure dependency failures,
  but must explain every need and remains distinct from malformed output or
  execution failure. All H1 rationale fields are non-empty arrays of short
  strings. A defined measurement is retained for H2/H3 even when its data
  dependency is presently unavailable. The frozen H1 output ceiling must be
  large enough to serialize the complete runtime need set; new contracts use
  8,000 output tokens and direct the model to group refs that share one
  disposition/rationale only when one measurement or one dependency reason
  genuinely addresses every grouped ref; semantically unrelated needs may not be
  pooled merely to shorten the ledger. `measurement.value_kind` is one of
  `boolean`, `ordinal`, `numeric`, or `categorical`. A measurable gap omitted
  from the current bounded hypothesis portfolio uses `deferred_measurement`;
  this is not a claim that the gap is untestable, already covered, or resolved,
  and the unchanged backlog remains eligible in a later cycle.
  `update_existing` and
  `already_covered` each cite exactly one stable Signal per disposition row;
  `new_measurement`, `deferred_measurement`, `repair_dependency`, `not_testable`, and
  `fast_plan_action` cite none. A
  `no_hypothesis.need_refs` list is only a bounded
  explanatory subset and must not duplicate the complete disposition ledger.
  H1 receives the bounded, identity-masked, outcome-aware Fast meta-memory so it
  can form hypotheses from recurring prediction errors even when Fast supplied no
  new Signal need. It does not receive the Discovery candidate-case roster,
  positive/control membership for that roster, or full source excerpts. The
  absence of those direct H2/H3 inputs is therefore not, by itself, a valid reason
  to reject a measurement that can be defined from meta-memory, the demand
  backlog, and the available source catalog; local H2/H3 owns case feasibility
  and evidence testing.
  Aggregate masking globally protects ids, tickers, and unambiguous multi-token
  formal names. A Fast backlog row with an explicit source case receives an
  additional case-scoped distinctive-brand mask before its source ref is made
  opaque; ordinary research and canonical contract words are excluded. The row
  and final assembled H1 payload are each checked against their own guard scope
  before transmission.
  The union of hypothesis `need_refs` exactly equals the refs dispositioned as
  `new_measurement`; needs outside the bounded portfolio use another honest
  disposition. Mismatch feedback reports ledger-only and hypothesis-only refs.
  Measurements, queries, and falsifiers use facts available at or before each
  prediction time; explicit post-series, post-cutoff, or after-prediction
  acquisition is invalid even though the resolver would later fail closed.
- The controller also projects explicit vertical-reflection fields into stable
  runtime action refs. Each such ref must be dispositioned as a new measurement,
  an existing-Signal update, a dependency repair, an intrinsically
  `not_testable` measurement with a specific measurement-level reason, or
  `fast_plan_action` when it changes retrieval, analysis, threshold calibration,
  magnitude, or another prediction policy rather than defining a reusable
  observable factor. `fast_plan_action` is rejected for ordinary backlog rows;
  the original reflection remains in meta-memory and is already a direct input to
  the next Fast proposer. `already_covered` remains invalid because it would allow
  reflection to be present but operationally ignored. Reflection alone never
  forces a `new_measurement`; when H1 has no honest factor hypothesis, the
  independent E1/E2 comparison remains responsible for discovery.
- H1 projects every runtime need ref to a deterministic compact alias before it
  crosses the model boundary. The outgoing backlog and every correction use only
  those aliases; after validation, the adapter maps the disposition ledger,
  no-hypothesis subset, and per-hypothesis need refs back to their original refs
  and persists the local alias map for audit. The search fingerprint remains over
  the original masked backlog, and the projection version is part of the model
  work identity. This projection is an identity transport aid, not aggregation:
  every original need remains independently accountable.
- Before detailed H1 candidate parsing, locally decidable need-ledger failures
  are reported together: unknown refs, duplicate refs, missing coverage, a
  no-hypothesis conclusion that still declares a new measurement, and disagreement
  between new-measurement dispositions and hypothesis need refs. One bounded
  correction therefore sees the complete obligation set instead of consuming its
  attempts one typo at a time. This aggregation includes unknown or duplicate
  refs in `no_hypothesis.need_refs`; when the same out-of-scope history locators
  contaminated disposition rows and the terminal reason, correction may remove
  them from both places without violating scoped-repair preservation.
- A row whose source kind is `unmatched_signal_need` cannot use
  `already_covered`: that would erase an explicitly unresolved Fast demand
  without creating either a Signal measurement or an action. Such a row may use
  `update_existing` only when every need in the row independently matches a
  version-owned `routing_answer_need_phrases` entry on the one cited stable
  Signal. A backlog row that already carries that exact `signal_ref` is also an
  explicit update basis. Arbitrary token overlap with an id, description, or
  query is never coverage evidence. The H1 card projection therefore includes
  only these bounded version-owned answer phrases. Grouped rows are checked per
  need so one relevant need cannot launder unrelated siblings.
- H1 row-shape failures are indexed structured obligations. After all bounded
  model corrections, a deterministic fallback may remove only a redundant
  legacy singular `signal_ref` when its value exactly equals the sole accepted
  `signal_refs` entry. The complete H1 parser and semantic validator must then
  pass; no missing, conflicting, or semantically unsupported field is repaired
  this way.
- H1's alternative-outcome guard is semantic rather than a bare horizon-word
  blacklist. Source-owned point-in-time measurements may preserve terms such as
  `short-term investments` and a contemporaneously disclosed statement that
  cash is sufficient for the next six months. A proposed measurement of future
  short-term returns, price performance, revenue growth, or another replacement
  outcome remains invalid.
- A no-hypothesis or `not_testable` rationale may not use H1's intentionally
  withheld Discovery case roster, that roster's positive/control membership,
  case evidence, or source excerpts as its reason. A phrase such as “the H1
  candidate roster and source excerpts are absent” is the same violation even
  when an independent valid empty-backlog reason appears elsewhere. This locally recognizable
  contract violation participates in the same aggregate correction, so the model
  must either state a valid measurement-level reason or return a structured
  hypothesis for H2/H3 testing.
- Exploration E2 accepts empty decisions only with a bounded `no_candidate`
  reason and the exact runtime-selected grounded induction refs. Non-empty E2
  portfolios require `no_candidate=null`; H3 keeps its existing decision shape.
  The runtime supplies a bounded ordered `decision_slots` inventory. Every
  non-empty E2 row has exactly `hypothesis_id`, `disposition`, `rationale`,
  `contrast`, and `candidate`: it copies one unused slot, uses
  `disposition=supported`, carries a complete candidate with exactly `spec`,
  `skill`, and `tests`, and provides `contrast` with non-empty, label-correct
  `positive_case_refs`, `control_case_refs`, and one observable-difference
  statement. The adapter validates those refs against the actual labeled cohort
  and persists them as the decision's sample basis instead of silently assigning
  every supplied case to every candidate. E2 decisions are cross-case portfolio
  hypotheses, never one decision per input case. When the model reports only
  case-level rejection/inconclusive rows, the
  correction obligation explicitly requires `decisions=[]` plus the structured
  `no_candidate` object rather than repeatedly reshaping those rows as candidates.
  An E2 no-candidate rationale must also agree with the supplied label inventory;
  for example, it cannot claim that unlabeled cases were considered when every
  selected signature has an explicit positive/control label. E2 rationale and
  observable-difference text may not infer unsupplied issuer-profile attributes
  such as sector, industry, business model, market-cap class, geography, or
  listing venue. A profile attribute is usable only when its literal vocabulary
  appears in the supplied source-owned signature projection; a violation is a
  structured correction obligation over only the offending rationale or
  observable-difference path.
  E2 rationale may describe a specific missing, absent, truncated, partial, or
  otherwise unavailable source input only by copying one supplied
  `evidence_gaps` string verbatim as its own rationale item, prefixed exactly by
  `[case_ref] `. Generic conclusions such as “the supplied evidence is
  insufficient to establish a recurring contrast” remain valid without a gap
  citation because they do not assert that a particular input is absent. The
  adapter rejects a specific absence claim that is not one of these canonical
  gap citations and scopes correction to the offending rationale path. This
  prevents E2 from converting an observed value or unrelated catalog context
  into an invented data gap while keeping E1's source limitations auditable.
  The E2 prompt says that signatures were frozen while hidden but their supplied
  positive/control labels are now visible. A rationale cannot claim those labels
  remain hidden, unavailable, or uncomparable. The adapter persists the exact
  runtime-owned positive/control ref arrays in no-candidate audit metadata and
  rejects free-text rationale that combines any case ref with a group label;
  mappings therefore come only from structured runtime state, not prose. Exact
  canonical gap citations remain valid. It also identifies signature
  summaries as deterministic source projections rather than model-authored
  interpretations, so E2 receives one coherent provenance contract.
- E1 summaries are untrusted interpretations and remain audit-only. Before E2,
  the controller emits only each validated document ref and exact source span
  with a deterministic literal description. When the span belongs unambiguously
  to one supplied SEC Company Facts record, that description also preserves only
  its source-owned taxonomy, concept, label, and unit so E2 knows what the literal
  number measures; it never restores an E1-authored claim. Queryless E1 is directed
  to prefer two available comparable periods of the same structured concept before
  unrelated one-period facts, making direction observable within the existing
  evidence and output bounds. The deterministic Company Facts projection pairs
  instant facts across distinct dates and duration facts only across like-duration
  or like-fiscal-period records; it never presents a quarter and a full year as a
  two-period trend. When no comparable predecessor exists, it exposes one period
  rather than manufacturing a direction. A locally recognizable SEC cover or
  registration boilerplate span is not a comparison-ready observation. Empty E2
  outcomes distinguish a genuinely compared `no_measurable_pattern` within the
  explicitly supplied grounded cohort from `insufficient_evidence`. An unrelated
  source gap or a quarantined sibling observation does not make the whole cohort
  evidence-limited once both fixed groups meet the grounded floor; only a technical
  loss that leaves the selected comparison itself below that floor may force
  `insufficient_evidence`. The prompt and correction contract spell out the exact
  E2 row shape so a schema error cannot erase a semantically useful candidate
  proposal and be misreported as a domain-empty result.
- Queryless E1 must not stop after the first locally sufficient document. Before
  labels are revealed, the runtime requests a bounded, source-diverse packet with
  both a narrative filing family and a structured financial family whenever both
  capabilities are available. It also derives a value-free comparison-concept
  inventory from concepts present across multiple selected cases. Each microbatch
  receives that same neutral inventory and is directed to prefer exact records for
  recurring concepts (including two periods when visible) over issuer-specific risk
  boilerplate. The inventory contains source-owned taxonomy/concept/
  `source_display_name`/unit and case-frequency only; it contains no values,
  identities, evaluation labels, returns, or candidate hypothesis, so it improves
  comparability without choosing cases for a desired result. If either source
  family cannot be materialized, the ordinary
  resolution gap remains visible and E1 still fails closed.
- H3 nests the exact evidence packets inside each comparison. It never sends one
  global packet array plus indirect refs that permit a rationale for one hypothesis
  to count a sibling hypothesis's packets. The adapter derives labels and query
  readiness only from that comparison-local packet list, and the prompt requires
  every rationale and candidate to use only its own nested evidence.
- Production Signal Update uses `signal-update-decision-v2`. Each case first
  records a source-cited evidence verdict; outcome relation is a separate field.
  Facts contain only a supplied `document_ref` and literal `exact_span`; the
  runtime does not treat a model-authored paraphrase as source fact. A label is
  never accepted as evidence that an event or source fact exists. New Update
  output also declares `changed_paths`: the exact mutable execution fields that
  differ from the supplied stable baseline. The runtime supplies both a complete
  vNext template and the exhaustive allowed path vocabulary. `spec.version`,
  `spec.definition`, whole-section aliases, and `tests` are never declared as
  changes. A candidate/diff validation failure grants the bounded correction
  authority over both `candidate` and `changed_paths`, because either side of
  the assertion may be wrong; all unrelated output remains frozen. The runtime
  overlays partial `raw_retrieval` edits on the stable policy and uses one shared
  validator during bounded correction and staging. Unknown, missing, or surplus
  path declarations and candidates whose only changes are version or tests are
  invalid update decisions. After the bounded model corrections are exhausted,
  runtime may replace only `changed_paths` with the exact diff deterministically
  recomputed from the otherwise valid stable/candidate pair. It then reruns the
  complete parser and fixture validator. This final bookkeeping normalization
  cannot alter the candidate, evidence diagnostics, fixtures, disposition, or
  rationale; any other invalidity still fails closed. The complete vNext template also carries the stable
  version's non-empty executable fixtures. Update output must preserve those
  fixtures byte-for-byte; tests are not a model-editable path and may never be
  replaced by an empty array. The clone-only argument schema accepts the same
  optional document id, company id, and publication timestamp fields as the
  fixture executor, so the supplied stable template is itself schema-valid and
  never needs mutation merely to satisfy the prompt. For deterministic updates,
  the engine binds the same side-effect-free fixture validator into the response
  parser: a retrieval or parameter change that turns an immutable expected result
  into `unavailable` is a correctable candidate error, not a staged candidate that
  is rejected only after the role has ended. LLM fixture execution remains in the
  later audited validation phase so hidden external usage is never introduced
  inside parsing. Historical records remain readable without
  preserving a second active output contract.
- Every label-revealed Mining decision receives a runtime-derived sample basis
  in its persisted form. The basis names the exact positive and control packet
  or case refs used by that comparison, so a schema-valid association cannot be
  audited without its sample. This field is runtime-owned rather than copied by
  the model.
- Legacy H1 and v1 Update records remain parseable only at explicit
  compatibility boundaries. New Slow execution requests H1 v7, reflection v2,
  and Update v2.
