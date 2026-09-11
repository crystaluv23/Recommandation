# Evolution Signal Roles

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
- Production H1 uses `signal-mining-hypothesis-v4`. The runtime supplies stable
  proposal refs, the fixed Discovery comparison, and the evidence lookback;
  the model supplies a structured measurement, canonical applicability,
  expected direction, retrieval intent, and falsifiers. Semantic validity must
  not depend on lexical overlap between an identifier, prose, and a query.
- Every supplied backlog need ref appears exactly once in a bounded H1
  disposition: new measurement, update existing, repair dependency, already
  covered, or not testable. Fast-derived Signal needs use
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
  disposition/rationale. A `no_hypothesis.need_refs` list is only a bounded
  explanatory subset and must not duplicate the complete disposition ledger.
  H1 receives the bounded, identity-masked, outcome-aware Fast meta-memory so it
  can form hypotheses from recurring prediction errors even when Fast supplied no
  new Signal need. It does not receive the Discovery candidate-case roster,
  positive/control membership for that roster, or full source excerpts. The
  absence of those direct H2/H3 inputs is therefore not, by itself, a valid reason
  to reject a measurement that can be defined from meta-memory, the demand
  backlog, and the available source catalog; local H2/H3 owns case feasibility
  and evidence testing.
- The controller also projects explicit vertical-reflection fields into stable
  runtime action refs. Each such ref must be dispositioned as a new measurement,
  an existing-Signal update, or a dependency repair; `already_covered` and
  `not_testable` are invalid because they would allow reflection to be present but
  operationally ignored. This routes action without granting permission to infer
  Discovery labels or source facts from retrospective reflection.
  At least one projected reflection ref must occur in a `new_measurement`
  hypothesis unless all projected reflection refs are `repair_dependency`.
  `update_existing` may describe a relationship but cannot by itself satisfy this
  gate because H1 disposition metadata does not invoke Update.
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
  attempts one typo at a time.
- H1's alternative-outcome guard is semantic rather than a bare horizon-word
  blacklist. Source-owned point-in-time measurements may preserve terms such as
  `short-term investments` and a contemporaneously disclosed statement that
  cash is sufficient for the next six months. A proposed measurement of future
  short-term returns, price performance, revenue growth, or another replacement
  outcome remains invalid.
- A no-hypothesis or `not_testable` rationale may not use H1's intentionally
  withheld Discovery case roster, that roster's positive/control membership,
  case evidence, or full source excerpts as its reason. This locally recognizable
  contract violation participates in the same aggregate correction, so the model
  must either state a valid measurement-level reason or return a structured
  hypothesis for H2/H3 testing.
- Exploration E2 accepts empty decisions only with a bounded `no_candidate`
  reason and the exact runtime-selected grounded induction refs. Non-empty E2
  portfolios require `no_candidate=null`; H3 keeps its existing decision shape.
  E2 decisions are cross-case portfolio hypotheses, never one decision per input
  case. When the model reports only case-level rejection/inconclusive rows, the
  correction obligation explicitly requires `decisions=[]` plus the structured
  `no_candidate` object rather than repeatedly reshaping those rows as candidates.
  An E2 no-candidate rationale must also agree with the supplied label inventory;
  for example, it cannot claim that unlabeled cases were considered when every
  selected signature has an explicit positive/control label.
- E1 summaries are untrusted interpretations and remain audit-only. Before E2,
  the controller emits only each validated document ref and exact source span
  with a deterministic literal description. A locally recognizable SEC cover or
  registration boilerplate span is not a comparison-ready observation. Empty E2
  outcomes distinguish a genuinely compared `no_measurable_pattern` from
  `insufficient_evidence`; projection loss, missing comparison-ready observations,
  and quarantined extraction failures cannot become a broad no-pattern conclusion.
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
  invalid update decisions. The complete vNext template also carries the stable
  version's non-empty executable fixtures. Update output must preserve those
  fixtures byte-for-byte; tests are not a model-editable path and may never be
  replaced by an empty array. Historical records remain readable without
  preserving a second active output contract.
- Every label-revealed Mining decision receives a runtime-derived sample basis
  in its persisted form. The basis names the exact positive and control packet
  or case refs used by that comparison, so a schema-valid association cannot be
  audited without its sample. This field is runtime-owned rather than copied by
  the model.
- Legacy v1/v2/v3 H1 and v1 Update records remain parseable only at explicit
  compatibility boundaries. New Slow execution requests H1 v4 and Update v2.
