# Evolution Research Validation

## Purpose

Validate point-in-time research state, evidence references, Signal results,
reflection transitions, and Predictor inputs after generic JSON parsing.

## Invariants

- Evidence must resolve to local immutable source spans.
- Outcome and target-identity leakage checks remain fail closed.
- State transitions preserve stable ids and cumulative research history.
- Temporal intent checks normalize underscore-separated words before matching
  cutoff clauses. Machine-style and prose spellings have the same meaning;
  this does not change persisted questions, source dates, or evidence validation.
- A partial-answer residual must retain the temporal scope of the need it
  narrows. When a persisted routing residual dropped the parent need's cutoff,
  the exact required residual representation restores the inherited as-of
  clause onto the residual instead of retaining the already answered parent
  need. Transition contracts, selection intents, need cutoff restoration, and
  transition validation derive that representation through one shared rule so
  the exact string H_reflect is told to write is always acceptable to both the
  transition and temporal guards.
- A legacy partial-answer residual that no bounded restatement can represent
  under the actual runtime prediction boundary (for example realized facts
  after the cutoff) is invalid routing state, not a removable obligation. The
  need-transition contract builder fails closed for it before any prompt
  exists, and transition validation never authorizes deleting the unresolved
  need: removal must be restored exactly, and no cutoff is fabricated for
  realized future facts.
- A need correction never carries a blanket dependency on unrelated state. A
  visible-answer or need-transition issue names only its own need path; it
  grants no authority over `current_beliefs` or any other collection. Belief
  edits during a correction must be authorized independently — by an actual
  linked-assertion dependency (same exact claim text) or an actual compaction
  obligation with exact removal scope — so a valid unrelated belief survives
  a need correction byte-for-byte.
- Need-transition feedback coordinates are unambiguous. Every user-visible
  correction instruction, validation error, and repair context targets the
  actual returned invalid path: when a partial-answer target survives at a
  shifted returned index (for example a residual inserted before a retained
  duplicate), the returned index is the correction target. A prior-state
  coordinate is kept only as explicitly labeled provenance
  (`prior_state_path`), never as an unlabeled `path`, so prose, typed
  paths, and metadata cannot disagree about which returned row must change.
- Need-transition validation is occurrence- and multiplicity-aware, never
  global text membership. Identical prior needs at different indices are
  distinct occurrences: every untargeted occurrence must be preserved
  byte-for-byte (a retained untargeted duplicate is never mistaken for the
  target), each targeted occurrence must carry its bounded residual
  (partial answer) or be removed (full answer), a selection binds every
  index it lists in `target_need_indices`, and one returned occurrence
  never satisfies two prior occurrences. Satisfying the guard by
  deduplicating prior needs or deleting unselected duplicate copies is
  invalid; the transition-contract construction already publishes one rule
  per prior index, and the deterministic need fallback likewise transitions
  exactly one occurrence per runtime-issued instruction so an untargeted
  duplicate survives its own preserve obligation.
- A runtime-owned evaluation input (the baseline, its date or price, the
  current or prediction-time price, the outcome definition) is rejected
  unless its anchor mention is clearly identified as reference use. Mention
  proximity only nominates candidate anchors; classification then fails
  closed. After underscore normalization like the temporal checks, one
  occurrence is reference use only when scanning left from the anchor across
  noun-phrase fillers reaches a closed reference construct: a reference
  preposition or reference phrase ("from / relative to / compared with /
  above ... the supplied baseline"), or "of" headed by a fixed-outcome noun
  ("a doubling of the adjusted share price"). Bare "with" is not a
  reference preposition: in a dative request ("provide / supply me with
  the baseline date") the "with" introduces the requested object, so the
  scan fails closed on the request verb; reference "with" is licensed
  only as an explicit reference phrase ("compared with", "with respect
  to"). Nomination enumerates every anchor-word occurrence inside each
  proximity span, not only the first: a proximity span may greedily
  cover repeated mentions across clauses, and an early reference mention
  never hides a later direct lookup of the same anchor ("Using the
  supplied baseline price, what is the baseline price?" rejects).
  Anything else fails closed: a
  request operator governing the anchor ("What is the exact baseline date",
  "Confirm the current share price"), an unrecognized governor ("the value
  of the baseline price", "please obtain the baseline date", "look up the
  baseline price"), an inverted or passive restatement with the operator on
  the right ("The baseline price is what?", "The baseline date and price
  must be identified"), or no governor at all. Unknown wording is never
  permission, and there is no request-verb list to keep growing: an
  issuer-evidence question anchors on a supplied input only through the
  recognizable reference constructs above. For the current-price trigger
  the classified anchor is the "current"/"prediction-time" word itself, so
  "move the adjusted share price above the current market level" stays a
  reference use while "what is the current adjusted share price" still
  rejects. Classification is per anchor occurrence and per paired keyword,
  so a mixed or repeated question that references one anchor while
  requesting another still rejects. Genuine baseline/date/current-price/
  definition and scalar price-lookup rejection, and all point-in-time
  future-fact rejection, keep their semantics.
- Reflect-phase raw validation is identity-aware for Basic Info evidence
  before tagged-ref construction: every returned `basic_info` row must
  reproduce byte-for-byte one prior-state Basic ref with the same
  `projection_id`. A mutated literal is reported as a typed obligation
  together with every other independently decidable raw issue (Basic
  quantity groups, quantitative assertion links) in the same initial
  correction feedback, so no independent defect stays hidden behind
  another until the correction budget is gone and only a plain
  construction error remains. When the prior state holds exactly one
  distinct literal for that projection, the obligation is replace-only
  and carries that exact prior literal as the restoration candidate;
  when it holds several distinct literals, or the projection is absent
  from the prior state — including a non-null prior state that carries no
  Basic refs at all, as can exist after the evidence lifecycle — no
  substitution is authorized and the only repair is removing that row —
  invented or ambiguous evidence is never
  accepted, and the deeper tagged-ref construction guard keeps its
  unchanged fail-closed semantics as the final boundary. The initialize
  phase (no previous state) stays outside this identity check.
- Quantitative assertion obligations describe exactly their machine
  authority: `replace` one assertion with one exact accepted claim or
  `remove` the unsupported numeric detail. They never suggest splitting
  one assertion into multiple rows; a one-to-many split is an append and
  requires its own explicit bounded add authority.

## Aggregated initial feedback and occurrence counts (round 19)

`_normalize_research_state_output` aggregates independently decidable issue
classes in the first feedback: a temporal (future-information) rejection is
raised together with the Basic quantity, quantitative assertion-link, and
Basic literal-identity issues computed from the same returned object
whenever the evidence shape makes those checks decidable, with the temporal
issues first so existing error ordering and contracts are preserved.
Aggregation changes feedback only; it never accepts a future fact, never
relaxes grounding or empty-state rules, and falls back to the temporal-only
rejection when the returned evidence shape is not decidable.

Occurrence-aware need-transition issues carry the exact runtime-issued
occurrence count of their required text (`required_need_occurrences`) in
their repair context, computed from the same per-obligation occurrence
arithmetic that validates preservation, so downstream deterministic
recovery can restore missing multiplicity without any whole-list rewrite
authority.
