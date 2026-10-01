# Evolution Research Validation

Temporal detection ignores only a closed, trailing exclusion such as “without
requiring contents or results published after the prediction time.” The stored
question remains unchanged. The positive main clause is checked independently;
a positive future-actual request cannot become valid by appending an exclusion.
Unknown negation grammar remains subject to the normal fail-closed checks.

An actionable question cannot request complete calendar-quarter actuals at
the midnight cutoff on that quarter's last day: the period has not completed.
Explicit requests for facts between the prediction date and the end of the
forward horizon are also post-cutoff requests, even without a literal future
end date. Existing cutoff-bounded disclosure/schedule exceptions still apply;
future actuals are corrected by typed local LLM edits, never silently rewritten.

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
- The as-of-bounded allowance for disclosed future schedules and expectations
  is grammatical-number agnostic. Its bounded expectation-or-schedule
  vocabulary matches the explicit plural of each countable noun it already
  covers (dates, schedules, timelines, milestones, forecasts, targets,
  goals, releases, reports, openings, construction plans, projections)
  exactly as it matches the singular, and its clear adjectival equivalents
  (expected, anticipated, projected) share one allowance. All matching uses
  whole-word boundaries with no stemming or broader substring matching. The
  as-of bound itself accepts the equivalent stricter prior-to and before
  spellings beside by/as of/through, both symbolic ("before/prior to the
  prediction time") and with an explicit date. Nothing else about the
  allowance widens: an explicit as-of bound at or before the prediction date
  is still required (a before/prior-to cutoff after the prediction date
  grants nothing), open-ended after/since windows still reject, and realized
  results, actuals, or other post-cutoff contents are still rejected —
  projected wording never converts realized-future results into admissible
  evidence.
- A partial-answer residual must retain the temporal scope of the need it
  narrows. When a persisted routing residual dropped the parent need's cutoff,
  the exact required residual representation restores the inherited as-of
  clause onto the residual instead of retaining the already answered parent
  need. When the parent need is validated bounded forward guidance, the as-of
  bounded allowance also requires expectation/schedule framing, so the shared
  rule inherits the parent's noun-form expectation/schedule marker (guidance,
  outlook, forecasts, targets, goals, schedules, timelines, milestones, dates,
  timing, releases, reports, openings, commentary, construction plans,
  projections —
  matched with the same case-insensitive handling as the temporal guard's
  expectation vocabulary) as
  explicit parent-owned framing whenever restoring the cutoff clause alone is
  not representable. Realized results, actuals, or how-much/how-many requests
  never inherit that framing, and a parent without its own validated bound or
  framing lends no permissions, so the rule still returns no representation
  for them. Transition contracts, selection intents, need cutoff restoration,
  and transition validation derive that representation through one shared rule
  so the exact string H_reflect is told to write is always acceptable to both
  the transition and temporal guards.
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
  above ... the supplied baseline"), "of" headed by a fixed-outcome noun
  ("a doubling of the adjusted share price"), or a temporal-boundary
  preposition ("by / before / through / prior to") whose own next external
  governor is an evidence-availability participle from a closed set
  (disclosed / reported / filed / announced / published / available /
  released / provided / furnished / communicated / posted / stated /
  said / guided / submitted / listed / recorded), because
  "guidance disclosed by the prediction time" bounds an issuer-disclosure
  window instead of requesting the anchor. A temporal-boundary
  preposition governed by anything else — a request verb or scalar
  lookup ("what was the share price by the prediction time", "give me
  the baseline price by the prediction time") — still rejects. Bare
  "with" is not a reference preposition: in a dative request ("provide /
  supply me with the baseline date") the "with" introduces the requested
  object, so the scan fails closed on the request verb; reference "with"
  is licensed only as an explicit reference phrase ("compared with",
  "with respect to"). Nomination enumerates every anchor-word occurrence
  inside each proximity span, not only the first: a proximity span may
  greedily cover repeated mentions across clauses, and an early reference
  mention never hides a later direct lookup of the same anchor ("Using
  the supplied baseline price, what is the baseline price?" rejects).
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

## Evaluation anchor restatements

When the evaluation context carries an `evaluation_anchor` block (status
available), every authored state text row — current_beliefs,
contradictions, resolved_questions, open_questions, and supporting_evidence
claims — is scanned with the same price-restatement pattern family as the
predictor baseline check. A number labeled as the current or
prediction-time baseline that differs from the anchor mean raises
`research_state_anchor_value_invalid`; a number presented as a multiple of
the baseline that differs from the derived threshold raises
`research_state_anchor_arithmetic_invalid`. Both name the exact row path,
carry the anchor-derived correct value in repair context, and aggregate
with the other independently decidable raw issues. Correct verbatim copies
of anchor numbers pass; the check constrains restated numbers only, never
probability or causal judgments.

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

## Incremental correction authority

The ResearchState owning parser emits typed field/member obligations for raw
shape and enum failures, invalid evidence tuples, retained evidence changes,
research/evaluation boundary violations, cosmetic need updates, and terminal
decision failures. Independently decidable issues retain their typed scope when
aggregated; diagnostic prose never becomes write authority. An invalid Signal
tuple permits only its coordinate fields and explicitly removing that evidence
member, plus exact-claim linked assertions when needed. A retained Signal claim
permits restoring that claim or removing its member, never changing another
source identity. Evidence shape failure permits replacing/removing only that
invalid member; deeper evidence semantics wait for a well-formed member.

Removing an invalid sole remaining next-information need can require changing
`decision` to `finalize`; that dependency is issued explicitly. It does not
authorize adding a new unrelated need. Every merged delta is rechecked against
the unchanged provenance, PIT, need-ownership and complete-state invariants.

The live Plan proposal boundary accepts canonical `B`, `H_init`, `H_reflect`,
`H_analyse` only. Its raw validator issues typed add/remove/replace operations
for missing, unexpected and malformed fields before normalization can erase
their coordinates. `B.requests` contains one to eight request objects with the
documented required id, description, source-types and max-documents fields,
plus optional lookback-days/query. Historical record normalization stays a
separate compatibility concern. Blank optional query keeps its existing
normalize-to-omitted behavior; other wrong types cannot be coerced into validity.
The existing canonical forbidden-outcome-field predicate is reused on original
request coordinates, so outcome-data rejection remains exact and correctable
without diagnostic-text parsing or a second definition of the rule.
