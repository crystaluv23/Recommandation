# Research / Information-Plan and Signal Self-Evolution

## Status

Ready - bounded-context v6 cumulative dual-loop specified

## Purpose

Evolve how the system researches and organizes information, while gradually
improving the reusable Signal Library. The active system has two coupled time
scales:

```text
Fast Loop: Information Plan Evolution
Slow Loop: Signal Mining and Signal Update
```

The evolved object is not one prediction prompt. An `InformationPlan` learns
what basic information to bootstrap, how to formulate initial information
needs, how to reflect over a batch of Signal results, and how to assemble final
context. The Signal Library learns which reusable real-world concepts deserve
observation and how to extract them reliably from Raw Info.

## Supersession

This contract replaces the former active `SchemeGenome + A/B/C + external
proposal dashboard` engine. Old `scheme_evolution_*` implementation modules,
its CLI configuration, and its test contract are removed rather than supported
in parallel. The older Ralph information-plan experiment remains an isolated
retrospective source/acquisition diagnostic; it is not a second active
self-evolution engine.

## Durable State

A workspace contains:

```text
plans/                 # Plan Archive records
signals/               # stable Signal Registry
signals_candidates/    # slow-loop staging only
experiments/            # complete trajectories and round checkpoints
meta/                   # FIFO plan-round reflections
cache/                  # exact reusable model/tool outputs
state.json              # authoritative last_completed_round
cycle_state.json        # authoritative completed/active Fast+Slow cycle
```

The three logical cores are the Plan Archive, Signal Registry, and one global
Raw Info oracle stored outside the workspace. The run contract binds the oracle
identity and its initial inventory hash for diagnostics, but later oracle growth
is allowed. A workspace stores document references and resolution events, never
a private Raw Info copy. Experiments and meta-info preserve auditability; cache
is an optimization and never evidence that a round completed.

## Information Plan

```text
S = (B, H_init, H_reflect, H_analyse)
```

- `B`, Basic Info Policy: up to eight analyst-style retrieval requests describing
  which original sources to inspect and within what range. Each request contains
  `request_id`, information-purpose `description`, `source_types`, optional
  `lookback_days` and literal `query`, and `max_documents` up to ten. It does
  not define a fixed company-profile schema and cannot set `as_of`.
- Every current `B` request is routed under the target `company_id`; it is not a
  cross-issuer news or peer database query. An automatic Plan therefore cannot ask
  for general competitor/peer/rival actions as though the resolver will search those
  other issuers. It may ask for the target issuer's own disclosures or company-scoped
  news that explicitly discuss competitive position. Proposal validation names the
  exact offending request fields and uses the existing single correction before any
  case data or H_init call is spent.
- The fixed `H_P` proposal boundary requires every automatically proposed Plan
  to retain one compact point-in-time market backbone request: canonical
  `market_data`, a positive lookback no longer than 60 days, and one source
  document. This gives every case recent price/volume evidence without exposing
  the future label or letting one long price archive consume the Basic Info
  budget. The remaining `B` requests and all three research skills remain
  evolvable. Missing this backbone is a proposal-validation error with the same
  single bounded correction as other malformed Plan content.
- `H_init`: turns Basic Info into hypotheses and natural-language information
  needs, not hard-coded Signal ids. Every supporting-evidence `claim` contains
  1-400 characters; this bound is part of the role's visible output contract rather
  than a hidden parser constraint. Every numeric quantity in a supporting claim
  must be present in the union of exact Basic literals attached to that same claim;
  explicit thousand/million/billion/trillion words and standard adjacent suffixes
  are compared by exact decimal scaling without tolerance or rounding. Multi-span
  facts use multiple refs instead of an unsupported composite claim. A quantitative
  assertion in `current_beliefs` or `contradictions` must also occur byte-for-byte as
  the `claim` on its supporting evidence refs. This explicit link prevents a year or
  amount from an unrelated claim from accidentally grounding the assertion; the role
  may instead split the assertion or remove unsupported numeric detail. A temporal
  quantity from projection metadata, a neighboring projection, or general document
  context is not literal support. Initial instructions say this explicitly, and the
  sole correction aggregates every locally decidable missing-quantity and assertion-
  link path before the call; deletion from the named claim and linked assertion is the
  minimal repair when no same-claim literal contains the quantity.
  A grouped assertion-link obligation also gives each invalid assertion path up to
  three lexically nearest byte-exact claims from evidence refs that have no separate
  reported defect. These are copy candidates, not a runtime-selected repair; H_init
  may choose one, remove the assertion, or repair another evidence claim and copy its
  final claim exactly before the same validators rerun.
  When the same invalid claim appears on several Basic refs, missing-quantity feedback
  names every same-claim evidence path plus its linked assertions, and excludes all of
  those refs from unchanged-valid copy candidates. Every retained ref must use the
  same repaired claim string.
  Feedback includes both normalized groups and the exact numeric substrings found in
  the claim so correction does not need to infer how a scaled value was written. A
  comparison losing one endpoint is narrowed to one grammatical supported observation.
  The same raw prevalidation rejects an open question or next need asking for the
  runtime-owned evaluation baseline date/price or the definition/terms of the fixed
  outcome. This is not issuer evidence; feedback names only the exact offending path
  and requires deletion rather than inventing a source answer.
  A same-state resolved/need overlap must contain a semantic topic; a shared period
  marker such as `Q2 2025` alone never makes two otherwise different questions
  contradictory.
  The two-word fallback also abstains when both occurrences begin with the same
  title-cased entity token after possessive normalization, so `Kinross revenue` does
  not conflate a historical-revenue answer with a gold-price sensitivity question.
  Generic subject words including `company` and `issuer` are removed before matching,
  so `company revenue` cannot treat a quarter comparison plus EBITDA need as answered
  by a broad recent-revenue question.
  Because Predictor receives the compact frontier rather than complete Basic text,
  H_init retains the smallest material direct expectation support/counter-evidence
  (for example a visible price target, guidance item, or issuer catalyst) that bears
  on the fixed outcome. It still does not enumerate every request or source.
- `H_reflect`: consumes the complete current research state plus one whole
  Signal batch and returns beliefs, supporting evidence, contradictions,
  resolved/open questions, next needs, and `continue` or `finalize`. Its
  `finalize` decision ends evidence collection only; `H_reflect` cannot define,
  name, or choose a replacement prediction-class ontology. The fixed Predictor
  alone owns `likely/possible/unlikely/insufficient_information` and magnitude.
  A Plan may explicitly preserve this boundary (for example, keep the fixed
  four-way judgment intact or continue without altering the Predictor ontology);
  negative guard language is not itself an ontology definition.
- `H_analyse`: supplies only evidence-organization and weighting instructions
  for assembling Basic Info, important Signal results, counter-evidence, and
  final state into the label-free Predictor context. It cannot calculate event
  probabilities, classify a Signal as the final answer, change the fixed
  horizon/label/four-way judgment, or itself generate a prediction.

Automatically proposed `H_*` values must be executable role instructions, not
schema placeholders or descriptions that merely say to provide/complete an
instruction. `H_init` must name hypothesis formation plus unresolved information
needs/questions; `H_reflect` must name evidence-based belief updating plus the
continue/finalize or next-need decision; and `H_analyse` must name evidence
organization/weighting plus counter-evidence or uncertainty handling. Runtime
rejects a copied output-contract example, placeholder-like wording, or a field
missing its role semantics through the same single bounded proposal correction.

The retrieval path is therefore created at runtime. Candidate Plans may change
only these four fields plus their own id and parent references.

## Runtime Roles

Research Controller answers: “What information is needed next?” It owns
`H_init` and `H_reflect`.

Signal Retrieval Agent answers: “Which existing Signals can answer that need?”
For the current compact Registry, the runtime deterministically removes refs
already executed in the same case trajectory, then supplies every remaining
compact Signal card, including its category, in one selection request. The selector
also receives a bounded label-free applicability view of the current ResearchState:
hypotheses, beliefs, contradictions, resolved/open questions, and accepted evidence
claims, but no Basic/Signal literal evidence or provenance payload. Information needs
alone are not enough to distinguish, for example, a mature operator from a genuinely
pre-commercial product; the applicability view exists only to decide whether a card
fits the current case and must not be treated as a new source. Full
specs remain executor-only disclosure after selection. An empty `signal_refs`
array is a valid `no_signal_match` result when no remaining card can answer the
need and consumes no correction call. Before accepting empty, runtime performs
one conservative semantic contradiction check: if an information need repeats
at least three consecutive normalized words from an available `signal_ref`
(for example, “operating cash flow”), empty receives the same one correction
with the directly matching refs. This check does not select a Signal, require a
particular matching ref, or use fuzzy/single-word similarity; any non-empty batch
that answers the need remains the model's decision. A malformed container,
duplicate ref, ref outside the supplied cards, or still-empty contradicted result
receives at most one correction call with the exact allowed set. If the correction
remains invalid, the agent raises a
usage-bearing candidate-execution rejection; it must never convert model/schema
failure into `no_signal_match` or guess a category or Signal on the model's
behalf.
For non-semantic formatting only, runtime deterministically deduplicates refs,
trims reason/applicability strings to 240 characters, normalizes/deduplicates
context tags, drops values outside the frozen tag vocabulary, caps retained tags
at four, and preserves model order while trimming a batch to four Signals of which
no more than two may be LLM Signals. Tag values are auxiliary routing metadata;
visible card categories such as `catalysts`, `risks`, or `product` must not reject
an otherwise valid selection merely because they are not context-tag enum values.
The sole semantic exception is version-owned applicability: a Signal may expose
`routing_excluded_context_tags`, and selecting that Signal while the selector itself
attaches one of those tags now or attached it in an earlier accepted selection for
the same case is a direct contradiction that receives the one bounded correction.
It may also expose `routing_required_research_phrases`; at least one normalized exact
phrase must already occur in the supplied information needs or bounded accepted
ResearchState projection. The selector may not manufacture the required object by
analogy in its own reason/applicability text. This is used narrowly for constructs
such as `order_quality`, whose customer-order/backlog measurement must not be applied
to an unrelated financing or share-sale transaction merely because both have terms
that may be called binding or material. `commercialization_status` similarly requires
existing product/technology/prototype/commercialization wording; a mature mine or
ordinary operating project is not a technical-product transition merely because the
selector omits the `mature_operations` tag.
Runtime neither infers tags from case content nor substitutes another Signal. The
correction must remove the incompatible selection, or return a genuinely different
supported applicability classification; merely dropping a prior case classification
to pay for a Signal whose own hypothesis says it is inapplicable is not allowed.
Unknown refs, missing fields, and invalid reason/role enums remain semantic failures
with the single correction boundary. Zero-observation routing profiles are
omitted per card; one top-level statement defines the absent profile as “no
committed observations.” Prior compact Signal conclusions may be supplied to
help choose complementary evidence, but document fingerprints and content hashes
remain local executor state. The selector cannot interpret those hashes, already
executed refs are absent from its cards, and the executor independently enforces
fingerprint no-op after selection.
Because routing has only one correction, runtime evaluates every structurally usable
returned selection against target-index shape/bounds, reason/role enums,
version-owned tag exclusions, required research phrases, and direct-answer phrases
before raising the initial validation error. All independently decidable failures are
reported together with their selection index/ref. Fixing a target array must not
consume the correction and reveal an already-visible applicability analogy afterward.
Malformed items that
cannot be safely interpreted are named and skipped during this diagnostic pass; no
invalid item is accepted or locally repaired.
One shared soft-Signal call uses a batch-specific output contract. Each outer
row returns the exact supplied versioned `signal_ref`, while the nested result
returns the matching unversioned `signal_spec.signal_id` and integer version.
The prompt contains no conflicting single-result example; identity correction
names returned versus expected values and runtime never fixes the semantic id.

An `EvidenceResolver` serves both bootstrap and Signal paths. It queries the
global Raw Info oracle first, optionally performs separately authorized and
bounded data acquisition, appends complete provider responses, and immediately
re-queries. Unknown or unavailable capabilities produce structured DataGaps.

All model-facing records enforce JSON types before domain construction. In
particular booleans must be JSON booleans (the string `"false"` is invalid),
list fields must be arrays rather than strings or objects, and required nested
objects/fields cannot be filled by Python truthiness or iterable coercion.
Malformed ref containers follow the bounded correction path instead of escaping
as `TypeError` or being interpreted character by character. The selection role
must not force a non-empty answer after the eligible card set is exhausted.

Basic Info is an ordered `BasicInfoBundle` of exact original spans plus complete
lineage. The complete bundle remains durable. `H_init` receives each request's
purpose and a deterministic model projection capped at 32,000 normalized
characters: SEC HTML becomes readable text and repetitive per-row market
metadata is removed. News associated with the issuer only through provider
ticker metadata is filtered before this view; its visible title/body must name
the issuer when the case identity supplies aliases. Structured market spans are
row-aligned before normalization, so removed metadata cannot survive as a
cross-chunk key or value fragment. Each projected span has a stable projection id and raw
offset mapping; it is a view, not a summary or new source. Signal Executor asks the same
resolver for complete point-in-time documents and then runs deterministic
functions or LLM extraction skills. Signal results remain derived trajectory
records and are never appended to Raw Info.
The model projection applies the same request-fair boundary as the durable span
selection: it first keeps one highest-ranked non-empty projection per resolved
request and then fills remaining capacity in request order. It never clips a span to
fit the final bytes. Each request separately exposes source resolution `status` and
`projection_status` (`complete`, `partial_context_budget`,
`omitted_context_budget`, `no_context_spans`, or `unavailable`) plus available,
visible, and omitted projection counts. Thus `status=resolved` never implies that
H_init actually saw evidence that was omitted by a context ceiling. These compact
coverage fields also survive in the Predictor source index; they are diagnostics,
not evidence and cannot be interpreted as absence of the requested fact.
One/two-LLM-Signal batching sends one shared bounded `source_projection`. If strict
validation requires the sole correction, its system prompt is byte-identical to the
initial call and the dynamic `validation_feedback` is appended only at the end of the
user payload. The complete shared projection and every pending Signal spec/skill stay
visible; this is provider-prefix reuse rather than context removal. Conservative
pre-send budgeting still assumes a cache miss, while provider-reported cache usage is
persisted for live verification.

`H_init`, `H_reflect`, and compact Signal routing use the same correction-prefix discipline.
Each role's initial and correction calls have a byte-identical system prompt that
always explains the optional `validation_feedback`. The initial user payload carries
the complete stable role context plus `validation_feedback=null`; correction changes
only that final field to the failed output and exact local error. No Basic projection,
research skill, information need, card, learned profile, or prior Signal result is
removed. This is provider-prefix reuse only; conservative request budgeting still
assumes a cache miss and the same strict parser validates the corrected output.
Semantic `ValidationError` feedback must retain its original field/item path instead
of being rewrapped as though every returned top-level key were invalid. Correction
changes every actually named invalid item and any explicitly named linked assertion,
while preserving unrelated valid fields/items byte-for-byte. For a quantity-invalid
evidence claim, feedback names both the evidence index and each identical quantitative
belief/contradiction that must be changed to the corrected claim.
For an empty or over-400-character evidence claim, pre-domain validation aggregates
every invalid `supporting_evidence[index].claim`, reports its actual character length,
and names each identical `current_beliefs`/`contradictions` path. The correction must
shorten the claim to at most 400 characters while retaining its provenance, or remove
the evidence item; an identical linked assertion must copy the corrected claim
byte-for-byte or be removed. Unrelated valid fields and evidence remain unchanged.

ResearchState is a bounded decision frontier, not a second summary of every Basic
projection or Signal result. Provider output keeps only the smallest non-redundant set
needed for the active hypothesis, evidence, counter-evidence, unresolved uncertainty,
and next retrieval decision. The default per-field ceilings are three hypotheses,
eight beliefs, eight evidence refs, four contradictions, six resolved questions, six
open questions, and six next information needs; the combined arrays contain at most
24 items, every non-evidence text item contains at most 300 characters, and the compact
canonical JSON contains at most 6,000 UTF-8 bytes. During initialize, a Basic
`exact_text` literal contains at most 800 characters and must be the shortest complete
literal that supports its claim. Full Basic projections, Raw Info, Signal batches, and
trajectories remain durable locally, so these limits remove repeated source summary
rather than evidence coverage.

Reflect remains backward compatible with committed states created before these
ceilings. For each field, combined item count, and serialized byte size, its effective
ceiling is the larger of the default and the prior state's observed value. An already
over-limit field therefore cannot grow; retained overlong legacy text may remain
byte-for-byte, while newly authored text obeys the current 300-character ceiling.
This permits all-unavailable terminal reflection to preserve an old state exactly and
lets an evidence-bearing reflection replace or compact stale frontier items without
silently truncating them. Runtime aggregates every count, item-length, Basic-literal,
and total-byte violation before the sole correction; it never locally drops a returned
item. An incomplete JSON object that reaches its frozen output-token ceiling receives
explicit truncation feedback, so the correction spends its one attempt on a compact
complete object rather than guessing which semantic field failed.
The default per-case model ceiling is 160,000 tokens with a separate 36,000-token
finalization reserve. Admission still uses the conservative exact request-byte plus
output reservation, and the higher ceiling changes no role context/output/call/cost
cap; it prevents a paid 32,000-character soft-Signal attempt from making its own sole
correction unreachable solely because prior H_init and routing consumed their normal
reported tokens.
Correction feedback retains the exact aggregated error text and also projects its
semicolon-delimited error segments into numbered `obligations` with named field paths.
The role must satisfy every row rather than stopping after the first easy shape fix.
This is diagnostic structure only: runtime does not author a replacement value, drop
an invalid item, or skip the unchanged parser and semantic validation pass.
For an aggregate item-count overflow, correction feedback also reports the exact
current total, maximum total, minimum removals, and alternative arrays. If the rejected
object contains mechanically provable duplicate items, that obligation may add bounded
`structurally_redundant_remove_paths`: a later byte-identical item in one array, or an
`open_questions` item byte-identical to a `next_information_needs` item. These are
preferred but non-binding removal candidates. Runtime does not infer semantic
redundancy or mutate the state; the model may choose another removal combination, and
the unchanged count and semantic validators rerun after correction.

The fixed six-month adjusted-price-doubling outcome is an evaluation definition,
not an issuer statement, contractual target, or missing source. `H_init` may ask
for issuer-specific evidence that bears on its feasibility, but must not ask for
the "terms", "definition", baseline date, or baseline price of that fixed outcome;
those are runtime-owned evaluation inputs. When a market projection is
structured as JSON rows, a Basic-Info citation must copy one complete visible row,
including every field between its braces; constructing a shorter JSON object from
selected fields is a non-literal citation and follows the correction path.

In v6, `ResearchState.supporting_evidence` contains tagged references rather
than free strings. A Basic-Info reference carries
`projection_id + exact_text + claim`; a Signal reference carries
`signal_ref + supporting|counter + evidence_index + claim`. Initialize may
create only references into the current Basic-Info projection. Reflect may
retain existing references or add references into the current Signal batch.
Finalize may retain existing provenance only; it may restate `claim`, which is
interpretation rather than source identity. Basic provenance is
`projection_id + exact_text`; Signal provenance is
`signal_ref + supporting|counter + evidence_index`. Projection citations must map
uniquely to an original Raw Info span. If `exact_text` has exactly one contiguous
match across the current projections, local code canonicalizes a mismatched
projection id without another model call. Ellipses, paraphrase, reordered JSON,
non-contiguous joins, ambiguity, or no match receive one index-specific correction
and then fail closed.
For an absent literal that still shares a substantial contiguous span with its named
projection, that correction may quote one bounded exact source window around the
overlap. This diagnostic makes dropped company names, punctuation, and prefixes
visible next to the rejected value. It never replaces model output, changes the
canonical projection, or bypasses full byte-for-byte validation of the corrected ref.
When an LLM Signal quote touches an internal projection edge, correction feedback
also names its evidence group/index, the rejected projection id, which edge was
touched, and every overlapping projection id for the same source boundary. The full
unchanged projections remain visible; the model must copy a complete clause from one
of them or return unavailable. Runtime does not extend the quote or choose evidence.
The correction instruction makes the required state transition explicit: each
provenance item named by the validation error must be replaced by a valid visible
reference or removed. Returning the same rejected provenance is not a correction.
This remains a model correction followed by the same local evidence validator; the
runtime never repairs, drops, or guesses an evidence reference on the model's behalf.
When a reflect response supplies every canonical Signal-ref field but also copies
legacy `projection_id`/`exact_text` fields, local code drops only those redundant
fields before validating the canonical ref against the current batch. Missing or
invalid canonical fields still consume the one correction and then fail closed.
The model-facing batch explicitly supplies the versioned `signal_ref`. If a response
returns only an unversioned `signal_id`, local code expands it only when exactly one
current-batch result matches; absent or ambiguous ids remain invalid.
The reflect payload also carries a deterministic `signal_evidence_ref_catalog`
listing, for every current-batch `signal_ref`, the exact valid zero-based
`supporting` and `counter` evidence indices. When validation rejects an index, the
single correction message names the exact `supporting_evidence[index]`, returned
`signal_ref`, group, index, and valid indices for that ref/group. The model must
select an exact catalog tuple or remove the citation; runtime never clamps, swaps,
or guesses an evidence index, and a still-invalid correction fails closed.
The model-facing `signal_batch` is a deterministic compact view, not the durable
canonical `SignalResult`: it carries state, interpretation, stable evidence indices,
timestamps, and normalized bounded evidence text. It omits document ids/hashes and
never sends canonical Raw Info `exact_span` back to H_reflect. HTML and repetitive
market `retrieved_at/source/symbol` fields are removed; each evidence text is capped
at 1,200 characters and the batch evidence text at 8,000 characters. The complete
canonical Signal batch remains in the local trajectory and is still the only input
to literal/index/quantity validation. For locally validated deterministic numeric
Signals, the result row carries one top-level `exact_claim_if_adopted` containing the
exact canonical `metric=value` interpretation. It replaces the same string formerly
repeated in every evidence row and the generic interpretation projection is omitted
for that deterministic row. If H_reflect cites that result, both the evidence
`claim` and any quantitative belief copy this one value byte-for-byte; readable
rounding or unit conversion is still a different unsupported claim. Indexed canonical
evidence remains local and is still required for the ref.
When a `continue` reflection adds a current-batch Signal evidence ref, it must not
change an information need merely to demonstrate motion. If the batch did not answer
a need, the role retains that need byte-for-byte. If the batch answered it fully or
partly, the role removes or genuinely narrows it and classifies resolved/open
questions consistently. This preserves useful evidence without forcing an invented
resolution.
The reflection input carries a compact executed-selection projection with only ref,
reason code, reason, and target index, plus a deterministic
`need_transition_contract`. Its one `need_rules` row per prior need names the exact
text, available direct-answer refs, unavailable direct-answer refs, and contextual
association refs. The rule is conditional on actual evidence adoption: if H_reflect
adds evidence from an available `answer_need` ref, it removes or genuinely narrows
that exact target; otherwise it preserves the need byte-for-byte. Context-only and
unavailable refs never authorize a transition. This local projection removes
applicability prose, roles, and tags already consumed by routing rather than adding a
second semantic decision.

The current selector contract carries exactly one `target_need_indices` entry for
`reason_code=answer_need` and classifies `answer_scope=full|partial`. A partial answer
also persists one 1-300 character `residual_need` containing only the unanswered
facets; a full answer carries null residual. Non-answer reasons may carry zero or one
valid association index but carry null answer scope/residual, and the association
never implies resolution. At most one direct-answer selection may target a given need
within one routing round; other useful refs use contextual reason codes. Old committed
selections without these fields remain readable through the prior generic transition.
After adopting a current scoped answer, H_reflect removes a full target or replaces a
partial target with the exact persisted residual. Returning the old target, omitting
the required residual, substituting a cosmetic residual, or deleting an unrelated
need is invalid in either continuing or terminal reflection. This boundary does not
guess which need was answered or manufacture a resolution: the selector names the
scope before execution, local validation and the transition contract use the same
persisted selection plus current result coverage, and correction preserves every
untargeted need byte-for-byte.
Routing may use `answer_need` only for a need facet directly covered by the card and
must not claim coverage of other facets; contextual selections use an accurate other
reason code. A version-owned `routing_answer_need_phrases` boundary may make this
locally decidable: an `answer_need` selection must match one such phrase in the actual
information-needs array, not elsewhere in state or in selector-authored prose, while
the same Signal may remain applicable under a contextual reason. Evidence selected
only for confirmation, contradiction,
applicability, or combination does not trigger this progress requirement.
For a partial answer, a `selection_reason` phrase shared with `residual_need` is a
direct scope contradiction. Matching first uses an ordered three-word phrase; if word
order differs, at least three shared non-temporal content terms are also sufficient.
Correction feedback names the reason path and carries the normalized residual-only
phrase plus `remove_terms_from_selection_reason`; correction must remove every listed
residual-only term from that reason and name only the narrower answered facet, or
remove the selection. This is correction-only diagnostic context: normal routing
prompts do not pay for it, runtime does not author replacement prose, and the unchanged
scope validator reruns.
H_init likewise emits only unresolved needs: a fact already present in Basic Info or
the returned evidence/beliefs is not asked again, and a partly answered compound
question retains only its unresolved facets. Runtime aggregates two directly
decidable violations into the same bounded correction as structural defects: a need
that shares a high-confidence normalized answer signature with one visible Basic Info
projection, and a need that repeats an ordered three-word content phrase from the
same state's `resolved_questions` (or a non-titlecase two-word topic phrase when no
three-word phrase remains). Possessive remnants and current/recent/latest boilerplate
are excluded, and a title-cased two-word issuer name is never treated as a resolved
topic. The first gate requires broad term coverage and a
shared distinctive phrase, reports the exact need path, matching projection id,
matched terms, and a bounded visible excerpt, and otherwise abstains; it never
rewrites a question or attempts general semantic entailment. The correction must
remove the answered need or retain only genuinely unresolved facets. This prevents a
known answer from causing a useless Signal-routing call while keeping ambiguous
partial matches model-authored.
When the number of needs has not decreased, runtime rejects any changed need that
contains at least 90% of a prior need's normalized word set; appending a qualifier
to the whole old question is not progress. Exact retention remains valid because it
explicitly means “still unanswered.” A shorter list may likewise retain unanswered
prior needs after removing answered ones.
To catch an internally contradictory stale need without pretending to understand
general evidence semantics, runtime compares only newly added resolved questions.
If one contains the same ordered content phrase of at least three words as an exact
retained need after question boilerplate/function words are removed, the need must
be removed or narrowed. Signal-claim quantity errors and this directly decidable
need-transition error are returned together in the one correction, so fixing the
citation cannot reveal a second already-visible defect after correction is spent.
Unavailable Signal rows in this and every other model-facing role use only the
canonical coverage statement. They cannot be treated as evidence of absence,
added as a belief, or used to resolve a question; their original interpretation
remains local for audit.
Runtime enforces that rule independently of need-text adaptation: a newly resolved
question naming an unavailable Signal topic is invalid, as is a newly added belief
that names that topic using absence, unknown, insufficient, or unavailable language.
The same topic may remain in open questions or hypotheses because a data gap is a
valid uncertainty, not a finding.
When every result in one persisted Signal batch is canonical `unavailable`, runtime
keeps the complete `SignalRound`, fingerprints, usage, and coverage diagnostics but
normally does not call `H_reflect`: such a batch has no evidence that can support a
belief, resolve a question, or change the ResearchState. The exact state remains
unchanged and the controller proceeds to routing over the still-unexecuted cards,
subject to the normal round/call/token guards. The exception is a partial mixed
selection whose soft subgroup fails pre-send reservation after the deterministic
subgroup completed entirely as `unavailable`: that boundary is terminal, so one
H_reflect receives `must_finalize=true`. Its output must preserve every research
field/item byte-for-byte and may change only `decision` from `continue` to `finalize`;
one correction applies. Mixed batches and every ordinary batch with at least one
available result still receive exactly one H_reflect call. This optimization cannot
hide Signal execution cost. If routing then exhausts eligible cards or explicitly
returns no useful match, `no_signal_match` is a normal end of evidence collection,
not an unfinished research assertion: runtime copies the exact state and changes only
its control field from `decision=continue` to `decision=finalize`, without another
model call. Every hypothesis, belief, evidence ref, contradiction, question, and need
remains byte-for-byte, and `termination_trigger=no_signal_match` stays durable.
The prior `research_state.supporting_evidence` array is itself the canonical,
position-stable inventory for retained refs. Before constructing `ResearchState`,
the role boundary validates each tagged-ref shape and reports the exact output index,
missing fields, unexpected fields, and the four-key Basic or five-key Signal shape.
Because a role has only one correction, this pre-domain validation aggregates every
tagged-ref shape error in the returned array and every Basic claim-quantity mismatch
that is already decidable from its raw `claim + exact_text` fields. It must not make
the model spend its sole correction on `kind` only and reveal an already-present
unsupported quantity afterward.
For a malformed retained Basic ref, correction must copy `projection_id` and
`exact_text` from an indexed prior ref byte-for-byte, may restate only `claim`, or
remove the ref. Runtime does not reconstruct a missing literal or silently discard
unexpected semantic fields.
Legacy string evidence remains readable only in v1-v5 artifacts.

Every quantitative `current_beliefs` or `contradictions` item must be identical to
at least one accepted `supporting_evidence.claim`. This rule is applied after the
claim-to-literal or claim-to-Signal quantity checks, so an exact text match cannot
launder unsupported numbers. Hypotheses and unresolved/resolved question text are
not subject to this assertion rule because they may state counterfactual horizons or
name a reporting period without asserting that it occurred.

Blind Predictor consumes only the assembled label-free context. The same
Predictor adapter later receives its saved original context, saved prediction,
uncertainty, and revealed truth to produce post-hoc self-reflection.
`PredictionSelfReflection` retains `decision_drivers` in addition to failure,
misleading-Signal, ignored-evidence, missing-information, and Plan-issue fields.
When the immutable framework judgment is correct, at least one concrete
source-backed decision driver is required; an all-empty “nothing failed” object is
not useful original-layer learning and receives one correction. Older read-only
artifacts without this field deserialize it as empty, while every new artifact writes
the field explicitly.
When the framework judgment is incorrect, at least one concrete failure-attribution
item is likewise required across `why_prediction_failed`, `misleading_signals`,
`ignored_evidence`, `missing_information`, or `plan_issues`. Merely copying
`prediction_outcome.correct=false` with every diagnostic array empty is invalid and
receives the same one bounded correction.
The Predictor packet is a separate deterministic projection capped at 24,000
canonical UTF-8 payload bytes so its exact wire request plus the 2,000-token output
ceiling fits inside the frozen 36,000-token terminal reserve even under the
byte-for-token conservative preflight. It does not repeat complete Basic projections
or full Signal evidence arrays. Instead it contains the Basic request/source/DataGap
index, the complete final ResearchState, compact state/interpretation/coverage for
each executed Signal, and exact evidence material only for Signal tuples cited by
the final state. Basic literals are already carried by their tagged final-state refs.
It also carries a deterministic `prediction_baseline` computed only from the last
five complete adjusted-close rows strictly before `prediction_time` in the already
resolved point-in-time Basic market projection. This is a runtime-owned definition
input, not issuer evidence or a revealed outcome. Predictor instructions require this
mean whenever prose names the current or baseline price; local validation rejects a
different historical observation mislabeled as current and gives the model one
correction. The same compact baseline is retained in post-hoc context so a
framework-correct label cannot turn an arithmetically inconsistent original reason
into accepted learning.
Complete Basic Info, Signal rounds, lineage, and Raw Info remain durable locally.
If the deterministic projection cannot fit without dropping these semantic layers,
the case fails before a Predictor attempt; runtime never weakens the byte-level
preflight or silently truncates cited provenance.

Before Predictor handoff, direct identity fields are removed and company id,
current name/ticker, and the caller's source-derived alias inventory are masked
recursively across Signal interpretations, evidence spans, and document refs.
Composite formal names are split, terminal legal suffixes are removed, and a
distinctive leading brand token is retained to derive ordinary references such
as `Kinross Gold` and `Kinross` from
`Kinross Gold Corp / KINROSS GOLD CORP`. The assembled context is then scanned
again for this current case's expanded target aliases and fails closed before a
Predictor request if any remain. Third-party companies, publishers, and source
identities remain legitimate evidence: aliases from unrelated dataset cases are
not target-identity leaks and must not be scanned at the Predictor boundary.
The full unmasked trajectory remains inside the controlled experiment artifact;
the blind context is the only Predictor input.

## `execute_information_plan`

```text
Company routing identity -> B -> resolve Raw Info -> exact-span Basic InfoBundle
-> H_init -> information needs
-> select and execute Signal batch -> H_reflect
-> repeat until finalize or a runtime guard fires
-> H_analyse -> label-free final context -> blind two-stage prediction
-> persist prediction -> reveal label -> Predictor self-reflection
-> complete ExecutionTrajectory
```

Exact durable Basic Info spans use fixed 2,000-character chunks with 200-character
overlap and a 48,000-character per-case budget. The model projection is capped
at 32,000 normalized characters. Query requests rank literal
token hits deterministically; non-query requests rank by recency. Selected
spans are never partially truncated and must remain literal Raw Info substrings.

The prediction sink is mandatory and runs before the ground-truth provider is
called. A trajectory preserves Basic Info, every need, each selected Signal ref
with its reason code, short reason, applicability hypothesis, expected role,
and coarse context tags, Signal result, evidence, local resolution query,
API/cache result, appended
document ref, DataGap, Signal-consumed document id/hash, reflection state, final
context, prediction, ground truth, self-reflection, usage, and stop reason. Each completed case trajectory
is also written independently under
`experiments/trajectories/<plan_id>/<case_id>.json` with an exact input hash
covering the Plan, case, frozen Signal snapshot, and runtime limits. Restart
reuses it only when that hash and serialized trajectory remain exact; this
prevents a process interruption late in a validation batch from repeating
completed case work.

Unrepaired pre-prediction structured-output failures are stored as
`CaseEvaluationFailure` artifacts and stop that candidate without fabricating a
prediction. Post-hoc, critic, or round-reflection failures use explicit
deterministic failure records because they occur after the immutable prediction
boundary.

The Raw Info oracle is deliberately not frozen candidate state. Earlier
candidates may enrich it and later candidates may reuse the new facts; already
completed candidates are not replayed. API cost constrains acquisition and is
diagnostic only, never part of Binary F1 fitness.

Runtime engineering guards are fixed framework controls:

- maximum Signal rounds;
- maximum Signal calls;
- maximum LLM calls;
- maximum tokens; and
- maximum cost.

Each Signal round additionally admits at most four selected Signals and at most
two LLM Signals. Routing and adaptive research stop normally when the remaining
budget would invade the fixed 36,000-token terminal/Predictor reserve. Every
external request reserves canonical UTF-8 request bytes plus its frozen output
ceiling before any attempt or network action; post-call overflow is not a valid
budget boundary. Routing serializes the frozen available Signal cards before
case-dynamic needs/results so DeepSeek's automatic prefix cache can reuse the
largest semantically identical prefix without moving untrusted data into the
system role.

Inside a mixed deterministic/LLM selection, runtime executes the deterministic
subgroup first and the at-most-two soft Signals second, then merges successful
results back into the selector's order for one whole-batch reflection. This does
not change the selector caps or create another routing call. If the soft request
fails its conservative pre-send token reservation, already completed deterministic
results are persisted as the executed portion of the round and may update state. The
one whole-batch reflection receives `must_finalize=true` and
`termination_trigger=budget_exhausted`: it must author a `finalize` decision using
only the executed evidence, while retaining remaining uncertainty in open questions
or needs. The unexecuted soft selection remains visible in the exact routing
request/response and request-ready audit event. Local results must not disappear
merely because a later network request could not be reserved. If the reflection
ignores the terminal directive, one correction is allowed and the unchanged
`continue` state remains ineligible; runtime never rewrites it to `finalize`. If an
initial soft attempt completed but its sole correction cannot be reserved, its paid
usage remains counted even though no not-yet-valid soft result enters the partial batch.

They prevent infinite or unexpectedly expensive execution and are not Plan
research logic. Before reflecting on a batch that consumes the last permitted
Signal round/call or follows a pre-send soft-Signal budget refusal, runtime exposes
that exact boundary as a terminal reflection directive. H_reflect must author
`decision=finalize` from the evidence already available; finalization ends evidence
collection and does not require clearing unresolved needs or pretending uncertainty
was resolved. A `continue` response receives the normal single correction. Only that
model-authored `finalize` earns `stop_reason=finalized`; runtime never mutates the
decision or evidence itself, and the actual engineering boundary remains durable as
`termination_trigger`.

An empty selection or exhausted eligible Registry is a normal `no_signal_match`
closure: runtime makes only the deterministic control-field transition described
above and permits the fixed Predictor to evaluate the evidence already gathered.
When a cost/round/call guard is reached before any usable batch can be reflected, or
when terminal reflection fails its correction, runtime instead preserves the complete
last valid model-authored `continue` state, records the actual guard as stop reason and
termination trigger, and leaves the trajectory diagnostic-only under
`require_finalized`. The fixed Predictor may still produce a durable bounded forecast
so the failure remains auditable.

`require_finalized` is a fixed Fast-loop fitness gate, not an optional runtime
preference; a v5 evaluation contract that disables it is invalid. Once any case
for a candidate completes with an unfinalized trajectory, that candidate is
mathematically unable to enter fitness or parent selection. The evaluator must
first persist the exact diagnostic trajectory and prediction, then stop the
candidate immediately without evaluating its remaining cases. The resulting
attempt keeps the full expected case-id set, the completed trajectory subset,
no fabricated `CaseEvaluationFailure`, and therefore has no metrics plus the
explicit `incomplete_case_set` and `unfinalized_case` fitness reasons. Restart
applies the same fail-fast rule after reusing such a checkpoint; it must not
spend calls replaying or advancing beyond a known-unfit candidate.

## Dataset Ownership

`EvolutionDataset` has three issuer-disjoint sets:

- Discovery: label-visible only to Signal Mining/Update, preferably matched
  positive and control companies.
- Evolution Validation: labels hidden from plan runtime and Predictor; only the
  deterministic scorer and post-prediction self-reflection boundary may read
  them.
- Locked Test: absent from ordinary fast/slow-loop calls and opened only for a
  separate human-approved acceptance test.

All source reads remain point-in-time. Every observation has a stable `case_id`
distinct from `company_id`; prediction artifacts, label closures, tool access,
and statistics use `case_id`. Repeated as-of cases for one issuer must not cross
dataset ownership boundaries, and no two observations may share a `case_id`.

The full-market construction path includes every deduplicated issuer whose
security identity passes the normal-operating-common-stock gate and that has at
least one fixed-calendar case passing the price-window, listing-date, label,
minimum-liquidity, and adjusted-price-integrity gates. It must not first cap the
library or enrich it by outcome class. Eligibility is case-level: an issuer is
not discarded merely because an earlier shared date predates its IPO or lacks
enough liquidity, but that failing date never becomes a case. A case is admitted
only when the listing
is active common equity on NASDAQ/NYSE/NYSE MKT/AMEX, has a resolved CIK and a
valid listing date, is not an exchange-traded product, preferred/debt/security
variant, test symbol, SPAC/blank-check issuer, or other non-operating shell, has
at least `$1m` average pre-prediction daily dollar volume for every admitted
prediction date, and has no `>=4x` or `<=0.25x` consecutive adjusted-close jump
from the baseline lookback through the six-month label horizon. The last rule is
a conservative corporate-action/data-discontinuity gate; it may exclude a real
event rather than silently admit a split/relisting artifact.

The fixed Anchor issuers are assigned first and removed from all other ownership
sets. Remaining eligible issuers are then split into Discovery, Evolution
Validation, and Locked Test. A stratum with at least four eligible issuers gives
Evolution Validation at least two issuer identities while keeping Locked Test
non-empty; this is a rare-class rotation safeguard, not outcome enrichment.
The resulting Evolution Validation share is the
Fast-loop Random candidate pool. Its stored class prevalence is descriptive;
controlled balancing occurs only in the frozen Anchor and per-round Random
snapshots.

### Fast-loop evaluation sampling

Information Plan evolution uses one human-approved fixed Anchor split plus the
human-approved Evolution Validation pool. It does not use the Locked Test and
does not try to mirror the extreme class imbalance of the live market. Every
round evaluates exactly 24 cases:

- Anchor 16: `7 non_surge / 5 2_3x / 3 3_10x / 1 10x_plus`;
- Random 8: `3 non_surge / 2 2_3x / 2 3_10x / 1 10x_plus`; and
- Combined 24: `10 non_surge / 7 2_3x / 5 3_10x / 2 10x_plus`.

The nine positive Anchor cases are an explicitly reviewed symbol/date list.
The seven negative Anchor cases are selected once during proposal creation from
normal eligible non-surge cases by deterministic prediction-date and historical
dollar-liquidity matching, then written into the immutable Anchor artifact.
Changing any Anchor case creates a new dataset proposal/hash and a new run
contract; an active workspace never resamples it.

Every round deterministically pseudo-randomizes and rotates only the eight
Random cases; ordinary execution does not use process-global nondeterministic
randomness. Within each label the order prefers cases with the fewest prior
Random selections, then the least recent selection, then a
`base_seed + round_id + case_id` hash. A shortage in any exact label count or in
distinct issuers fails preflight before any external request. The sampler never
duplicates, silently backfills another label, emits fewer than 24 combined
cases, or selects an Anchor issuer into Random.

Before a new round snapshot is finalized or any Plan proposal/evaluation call
is made, the runtime applies one fixed, label-free shared-evidence readiness
gate. It resolves the mandatory 60-day `market_data` backbone locally first and
then through every authorized price adapter in catalog order. Fixed Anchor
cases cannot be substituted: an unavailable Anchor pauses before Plan work.
For a not-yet-frozen Random snapshot, the sampler skips an unavailable
case/company and continues through the same deterministic per-label rotation
order until the exact `3/2/2/1` quotas and cross-company constraint are met.
Only a readiness result produced under the invocation's frozen, explicitly
enabled acquisition policy can justify that substitution. Missing invocation
authorization pauses before sampling; `external_not_authorized` can never make
one candidate appear data-ineligible or change the Random cohort.
The acquisition request sees only routing identity and as-of time, never the
case label or split. An already persisted round snapshot remains immutable; it
is readiness-checked but never silently resampled.

Binary F1 is the parent-selection metric. Each Plan persists Anchor, Random, and
Combined metrics. Combined precision, recall, F1, magnitude macro-F1, and
accuracy are recomputed from all 24 saved predictions. In particular, Combined
F1 is not `w_anchor * anchor_f1 + w_random * random_f1`; it is calculated from
the combined TP/FP/FN counts. Anchor F1 is the stable cross-round reference,
Random F1 diagnoses generalization/noise, and Combined F1 determines Top-K.

Evaluation sampling is frozen below the evolution workspace:

```text
evaluation/
  anchor.json
  round_001/
    snapshot.json
```

`anchor.json` contains the exact approved 16 case ids, counts, and dataset-bound
hash. Round snapshots reference that Anchor hash and contain the exact eight
Random case ids, combined ordered case ids, seed, and target/actual counts for
all three cohorts. Existing snapshots are loaded before any sampling. A missing
or changed case referenced by a durable snapshot is an error, not a reason to
resample. Per-Plan diagnostic records persist all case attempts and failure
reasons. Fitness records additionally persist all 24 case ids, snapshot ids,
the three metric groups, evidence-coverage counts, predicted-positive count,
and eligibility decision.

Loading revalidates the same invariants as creation: exact round and seed,
Anchor `7/5/3/1`, Random `3/2/2/1`, Combined `10/7/5/2`, unique case ids, one
distinct company per case across both cohorts, and exact Anchor identity. A
self-consistent snapshot hash cannot weaken these evaluation rules.

### Fitness eligibility

Metrics are calculated only for a complete 24-case prediction set. Each case
must reach `finalize`, persist its prediction before label reveal, and contain at
least one exact Basic Info span or one non-unavailable Signal result backed by
validated source evidence. Incomplete or invalid candidates remain durable
diagnostic attempts.

A complete candidate is still `diagnostic_only` when it predicts zero positives
or has `TP=0`. Such records retain their confusion matrix and an explicit
`precision_defined` flag, but neither Top-K nor random exploration may select
them as parents. If every candidate in a round is ineligible, the workspace
writes `round_rejected` plus a capability-gap report and pauses without
advancing `state.json` or `cycle_state.json`.

Shared input readiness is not Plan fitness. If the pre-evaluation gate cannot
assemble an exact ready snapshot, or a defense-in-depth check finds the same
source-evidence-missing case across every candidate, the workspace writes a
replaceable shared-data pause diagnostic and leaves the round uncommitted. It
must not write `round_rejected`, blame every Plan, or make resume immediately
replay a permanent rejection. A transient provider failure propagates as the
dedicated retryable process status used by the bounded supervisor; a
deterministic Anchor/capacity failure remains an explicit operator-visible
pause.

## Two-Stage Prediction and Labels

Stage 1 predicts whether the fixed future horizon reaches at least 2x:

```text
is_surge = realized_max_multiple >= 2.0
```

For the historical six-month contract, the baseline is the arithmetic mean of
the last five complete trading-day adjusted closes strictly before the as-of
timestamp. The future numerator is the maximum arithmetic mean of any complete
five consecutive trading-day adjusted-close window after as-of and no later
than six calendar months after as-of. Fewer than five valid baseline or future
bars makes the case ineligible. This implements the user's “上涨至少 1 倍” as
price reaching at least `2x`; it does not classify `1x-<2x` as a surge and it
does not reward an isolated one-day spike.

The fixed Blind Predictor uses the product's opportunity-discovery decision
boundary, not a price-oracle or proof boundary. It returns `likely`, `possible`,
`unlikely`, or `insufficient_information`. The fixed adapter maps `likely` and
`possible` to `is_surge=true`, and maps the other two judgments to false.
The provider-facing schema and prompt request only `candidate_judgment`; they do
not request or permit a separate `is_surge` field.
`possible` means that anonymous as-of evidence supports a credible opportunity
candidate for the exact `2x` price outcome; it does not assert more than 50%
event probability. False positives and false negatives are penalized by the
same hidden-label precision, recall, and Binary F1; no class quota or case-level
label is disclosed.

For a negative judgment, Stage 2 is omitted. For a positive judgment, the
Predictor must choose one magnitude class:

```text
2-3x | 3-10x | 10x+
```

The saved output also contains qualitative confidence, key reasons, and
uncertainties. Numeric probability is not required, and the active Predictor
does not make a separate token-probability call. Continuous
`realized_max_multiple` remains the underlying truth.

`BlindPrediction` durably stores the provider's original `candidate_judgment`
alongside the derived `is_surge` value. The record is invalid unless `likely`
or `possible` is paired with true and `unlikely` or
`insufficient_information` is paired with false. Stage-2 gating and scoring
read only the derived binary value; the original category remains auditable
reflection evidence.

Prediction Stage 1 metrics are precision, recall, and binary F1. Prediction
Stage 2 metrics are magnitude accuracy and macro-F1 over true surge cases; a
Stage-1 false negative counts as a missed magnitude prediction. Binary F1 is the
only Plan-selection fitness. PR-AUC and weighted composite objectives are
deferred.

## Label-Revealed Reflection

After prediction persistence, the Predictor may see truth and return:

- whether the prediction was correct;
- failure causes;
- misleading Signals;
- ignored evidence;
- missing information; and
- Plan issues such as premature finalization.

This is usability feedback from the actual consumer of the Information Plan.
It is stored separately from prediction-time uncertainty and cannot alter the
already saved prediction. The framework, not the reflection model, computes the
saved `prediction_outcome.correct` bit from the immutable prediction and truth.

The same label-reveal boundary also derives an immutable
`candidate_judgment_feedback` object containing the saved four-way judgment,
predicted and true binary labels, binary correctness, a fixed assessment class,
and fixed explanatory text. Its eight cases are:

- surge + `likely`: strong correct positive;
- surge + `possible`: binary correct but conservative relative to the realized
  outcome, without claiming the realization proves ex-ante calibration;
- surge + `unlikely`: severe false negative;
- surge + `insufficient_information`: false negative with an evidence-coverage
  gap;
- non-surge + `unlikely`: strong correct negative;
- non-surge + `insufficient_information`: binary correct but still an evidence-
  coverage gap;
- non-surge + `possible`: false positive; and
- non-surge + `likely`: severe overconfident false positive.

This object is passed to case reflection and retained in the compact Plan-
critic trajectory so those roles can reason about conservatism, overconfidence,
and missing evidence. It is derived only after truth reveal, cannot mutate the
saved prediction, and never contributes an ordinal distance, weight, or other
term to Binary F1 or parent selection.

Plan-level reflection consumes a deterministic compact view of those saved
trajectories rather than their complete Raw Info and research contexts. Each
case row retains its prediction, post-hoc reflection, and compact Signal
results, but uses only an opaque batch index and
omits literal evidence spans, company/case identity, Basic Info, full research
states, prediction paths, and usage.
Before the critic request, the compact trajectory is value-masked and rescanned
against the full alias inventory of all 24 cases in the round.
Every full-inventory mask-and-scan boundary derives its exact case-sensitive and
case-insensitive alias matchers once per payload traversal and reuses them across
all nested string values. Reuse is a local execution requirement, not a relaxation
of the disclosure boundary: formal-name expansion, token boundaries, case-sensitive
short tickers, case-insensitive URL matching, recursive masking, and the independent
post-mask scan remain identical. The runtime must not recompile the same alias for
each leaf string; identity validation completes before request reservation or send
and consumes no LLM/provider budget.

The Plan critic and round reflector also receive deterministic parent
comparisons for the parents actually listed on each candidate Plan. Each
comparison contains the complete parent Plan, aggregate cohort metrics when
available, and a structured Plan diff: Basic Info requests added, removed, or
modified plus changed `H_init`, `H_reflect`, and `H_analyse` fields. It contains
no source trajectories, case ids, Raw Info, or per-case labels. The framework
marks whether the parent and child used the exact same evaluation snapshot and
computes metric/confusion deltas only in that case. When snapshots differ,
parent metrics are context only and the comparison must not claim a causal
improvement or regression. Parent comparison evidence can shape critic and FIFO
meta reflection, but cannot rewrite predictions, metrics, fitness, archive
membership, or parent selection.
The round reflector receives only compact PlanRecord summaries: Plan content,
aggregate metrics, Plan-critic output, Signal-usage counts, fitness, and compact
evaluation lineage. It does not receive trajectories, case ids, Raw Info,
research context, or per-case labels. With fewer than two newly completed Plan
records there is no horizontal comparison to perform: local code emits an empty
horizontal layer and makes no Round-reflector model call instead of restating the
single vertical reflection.

Reflection persistence is additive rather than summary-overwrite:

1. the original layer retains every Predictor-authored post-hoc reflection,
   keyed only by its opaque within-Plan case index and accompanied by the fixed
   four-way `candidate_judgment_feedback`, stop state, and no identity or source
   context;
2. the vertical Plan layer appends the exact Plan-critic output, Plan and
   aggregate cohort metrics, Signal-usage counts, fitness, and the deterministic
   comparisons against that child's actual parents; and
3. the horizontal Round layer appends cross-child patterns, prediction-error
   patterns, Signal observations, missing capabilities, and testable next
   actions produced by fixed `H_R`.

The runtime, not either reflection model, composes these layers. A Plan critic
cannot replace original case reflection, and a Round reflector cannot replace
either the original or vertical layer. The resulting complete layered object is
the one round entry appended to meta-info. It remains retrospective reflection
evidence only and cannot alter a saved prediction, truth, metric, fitness,
archive membership, or Signal Registry.

## Plan Archive

Each `PlanRecord` stores:

```text
P_i = (S_i, E_i, J_i, R_i, U_i, T_i)
```

- `S`: complete Information Plan;
- `E`: embedding of its canonicalized Plan;
- `J`: metrics;
- `R`: Plan-level critic reflection over the full validation batch;
- `U`: actual Signal selection/state usage;
- `T`: complete execution trajectories.

Canonicalization captures bootstrap, hypothesis, reflection, adaptive search,
and evidence-assembly behavior rather than raw whitespace. The default local
embedder is deterministic and replaceable by an external embedding adapter.
The committed round checkpoint also stores the Signal Registry version/hash
used to produce those trajectories. That identity is provenance only: it does
not change `J`, eligibility, or parent-selection weight.

## Parent Selection

Select quality plus diversity:

1. sort all committed Plan records by binary F1 descending;
2. accept a Plan only when its cosine similarity to every selected Plan is
   below the fixed threshold;
3. stop at Top-K; and
4. add up to two random non-selected archive records for exploration.

Selection ranges over the cumulative committed archive, including Plans scored
under earlier Signal Registry versions. Their saved blind-evaluation metrics
are immutable and are not recomputed after a Signal promotion. New candidates
are sampled with the newest Registry and may gradually displace old Plans only
by achieving higher Binary F1 under the normal diversity rule. This is
system-level co-evolution, not a claim that F1 values isolate intrinsic Plan
quality across changing research capabilities.

Random exploration is deterministic per `(frozen parent-selection seed,
round_id)`. A restart before the round commit therefore selects the same
parents, while different rounds still receive independent deterministic draws.

The proposer receives `[top1..topK, rand1, rand2]`, current FIFO meta-info, and
fixed `H_P`. It is called independently N times. Every call also receives a
non-evolvable proposal slot (`round_id` and candidate index/count). Runtime
assigns the Plan id deterministically from the slot and copies parent ids from
the selected parents actually sent to the prompt. Model-supplied structural ids
are ignored. The call explicitly requires a real four-field delta from every
selected parent and gives each bounded proposal attempt a deterministic change
focus. Runtime verifies that the named field group differs from every selected
parent; changing another field cannot satisfy that attempt's focus. Malformed
content, a placeholder/example echo, an incomplete `H_*` role instruction, an
exact parent copy, or an ignored focus receives one correction with the invalid
output and actionable validation reason before the outer attempt can reject it.
The correction must change each field named by the validation error; returning
the same rejected field is not a correction. Fixed-semantics scanning treats
explicit negative guardrails as compliant
and identifies the actual affirmative prohibited phrase when rejecting a redefinition.
The proposer uses frozen temperature `1.0` sampling; anonymous blind judging
stays at temperature `0.0`. The slot prevents exact-cache collapse and still
rejects repeated ids if sampling returns the same candidate. It participates in
request identity but never becomes part of the candidate Plan. This is
conditional sampling, not a claim of genetic crossover.

### Cross-workspace historical Seed Pool

Creating a new workspace automatically scans sibling evolution workspaces and
freezes `seed_pool/manifest.json` before the run contract. Discovery recognizes
only Plan records cross-linked from immutable checkpoints at or below each
source `state.json:last_completed_round`; staged attempts, rejected rounds, and
files beyond the pointer are never seed evidence. A source must keep Locked
Test sealed and use the same approved dataset hash, canonical 16-Anchor plus
8-Random evaluation contract, label definition, and binary fitness semantics.
Only committed Plans whose source contract has the exact v6 Predictor-semantics
hash, dataset hash, and evaluation-contract identity are eligible. All v1-v5
Plans and artifacts from the superseded token-probability threshold experiment
remain read-only audit evidence and are never active parents.
Malformed or incompatible source workspaces are skipped and counted in the
manifest rather than weakening the new run's preflight.

The framework canonicalizes only `(B,H_init,H_reflect,H_analyse)` to deduplicate
Plan content and assigns a content-addressed seed id, so repeated round-local
Plan ids cannot collide in the new workspace. The automatic policy is fixed:

- historical capacity is two;
- each source `run_id` is one independent run family until an explicit future
  branch-family record exists, and contributes at most its best eligible Plan;
- the first seed has the highest Combined Binary F1, with the weaker of Anchor
  and Random F1, Random-case coverage, and stable ids used as tie breakers;
- a second seed must come from another run family, reach at least 85% of the
  first seed's F1, and have cosine similarity below `0.90`; among qualifying
  Plans it prefers new Random case coverage, then lower similarity, then F1;
- the pool may contain zero or one entry rather than filling capacity with an
  incompatible, weak, same-run, or near-duplicate Plan.

Each entry retains source workspace/run/contract/checkpoint/record hashes,
source Plan id and round, cohort metrics, exact Random-case ids, embedding, the
opaque source evaluation snapshot hash, and the cloned four-field Plan. The
snapshot hash lets reflection determine metric comparability without exposing
cases. It does not copy source trajectories into the new
Plan Archive or expose company identities, Raw Info, or per-case labels to the
proposer. The pool manifest is immutable and its canonical hash is stored in
the new run contract. Resume loads and revalidates that exact snapshot; it does
not rescan newly completed workspaces.

Historical seeds fill only unoccupied quality-parent slots after the current
workspace's committed Top-K has been selected, and only when they remain below
the same similarity threshold against those current Plans. Random exploration
records remain current-workspace archive records. The manual Plan is used when
no current or historical parent exists. Historical seeds never receive current-
workspace fitness, become champions, or enter round checkpoints; they disappear
from parent input as current committed diverse Top-K Plans fill the slots.

Legacy Plans containing `BasicInfoPolicy.fields` remain readable through a
fixed compatibility mapping. New Plan artifacts write only `requests`.

## Plan Meta-Info and Fixed Priors

One FIFO window, default length 10, stores structured `RoundMetaEntry` values.
It remains a list-like append-only sliding window: round ids must increase,
append is the only mutation, and exceeding capacity removes the oldest whole
entry. No separate archive-derived summary view replaces this list.

Durable entries continue to retain the complete original, vertical, and
horizontal layers. Model-facing meta is a deterministic derived view capped at
48,000 characters across the FIFO: every round retains aggregate information;
the original layer becomes assessment counts plus bounded representative
samples; vertical/horizontal lists are bounded; and newer entries receive
representative detail first. For each assessment class, representative selection
chooses the most information-rich post-hoc reflection rather than the first case
encountered, retains its opaque case index, and admits up to six distinct classes
per Plan before the global 48,000-character bound is enforced. This prevents an
early blank or validation-fallback reflection from hiding a later analyst-authored
concrete root cause. Compact views never replace the durable entries.

Each entry contains:

- `plan_reflections`: one `PlanMetaReflection` per newly evaluated Plan, with
  exact anonymous original case reflections, exact vertical Plan reflection,
  deterministic parent comparisons, Plan content, cohort metrics, fitness, and
  Signal-usage aggregates; and
- the existing round-level successful/failed patterns, false-positive/false-
  negative patterns, useful/suspicious Signals, missing capabilities, search
  implications, and evidence refs, now explicitly defined as the horizontal
  layer.

The proposer receives the complete ordered FIFO entries. This is an explicitly
outcome-aware retrospective proposal input, but it contains no company id, case
id, Raw Info, literal evidence spans, or full research context. Older
pre-layered `RoundMetaEntry` artifacts remain readable as horizontal-only
entries so committed history stays auditable.

The only valid update is:

```text
H_R(new completed round experiments) -> new meta entry -> FIFO append
```

The system must not ask an LLM to improve old meta text without new experiment
evidence. Four priors are fixed framework inputs:

- `H_R`: reflect on one completed Plan round;
- `H_P`: propose a new Information Plan;
- `H_E`: mine a candidate Signal;
- `H_U`: repair an existing Signal into a candidate next version.

Changing a prior requires human review and a spec update.

## Fast Loop

For each bounded round under one frozen Signal Registry snapshot:

1. select Top-K diverse plus random parents;
2. call the proposer independently N times;
3. execute every candidate across evolution validation;
4. score saved predictions;
5. run the Plan-level critic and preserve its exact vertical layer beside the
   original anonymous case reflections;
6. embed and archive `S/E/J/R/U/T`;
7. reconcile version-bound Signal selection/result/outcome learning events and
   their bounded profiles from committed trajectories; and
8. derive the horizontal Round reflection, compose all three immutable layers
   into one grounded meta entry, append it to FIFO, and commit the round.

## Slow Loop

After a configured number of fast rounds, unfreeze definitions and run one
locally orchestrated Signal Mining pipeline plus one locally triggered Signal
Update pipeline. Neither is a free-form tool loop: each model call has one
bounded semantic job, and the controller owns sampling, label disclosure, Raw
Info retrieval, candidate staging, testing, and validation.

Cold-start recovery may instead run one explicitly frozen `slow_bootstrap`
single cycle with a zero Fast-round target. Freeze accepts one or more compatible
rejected workspaces and creates an immutable bootstrap manifest. A source is
compatible only when its approved dataset, fixed Predictor semantics,
evaluation contract, sealed Locked-Test posture, and stable input Registry
match the new workspace. The source rejection must be exactly the next round
above its authoritative committed pointer. Runtime never treats that rejection
as committed history.

The manifest extracts only `next_information_needs` from trajectories whose
pre-label terminal state is still `continue` and whose exact stop reason is
`no_signal_match`. It masks the source case's complete identity-alias inventory,
normalizes and aggregates duplicate needs, records counts rather than case ids,
and binds every source contract and rejected-artifact hash. It excludes
predictions, labels, post-hoc reflections, metrics, hypotheses, beliefs, literal
evidence, and Plan definitions. The resulting `signal_need_items` are merged
with ordinary data capability gaps and are supplied literally to H1 with their
diagnostic-only meaning. A bootstrap with no such need is invalid rather than a
generic label-aware mining shortcut.

Bootstrap then follows the ordinary H1/H2/H3, Update, fixture/contract checks,
paired effectiveness gate, durable validation, atomic Registry transition, and
cycle-result recovery. It neither advances `state.json:last_completed_round`
nor weakens any candidate gate. Its output can affect Plan research only when a
fresh later Fast workspace freezes that promoted Registry snapshot.

Mining alternates between two tracks. Hypothesis-driven cycles execute:

1. `H1 hypothesis portfolio`: from current meta-info, capability backlog,
   provisional/refined work, and stable Signal cards, propose at most three
   falsifiable hypotheses. Each hypothesis declares its applicability,
   expected winner/control difference in evidence available by the prediction
   date, required source types, bounded query, and falsifiers; it does not name
   companies. `lookback_days` bounds only pre-prediction evidence retrieval.
   `statement`, `expected_positive_pattern`, and falsifiers must test the fixed
   Discovery positive/control outcome; they cannot substitute a next-quarter
   earnings result, subsequent revenue growth, one-year return, event-study
   horizon, short-window price reaction, return, momentum, outperformance, or any
   other newly invented target. The expected pattern names both the positive and
   control groups, with case/group/cohort wording treated as equivalent, so H3's
   actual comparison is explicit. H1 never invents opaque case refs or bracketed
   case placeholders. Its statement describes the candidate feature and fixed-group
   contrast, not the availability, observability, or inferability of source data.
   Cross-issuer comparisons cannot treat higher/lower raw absolute revenue,
   earnings, cash, production, cost, or another size-dependent amount as the Signal;
   the feature is normalized to a case-local baseline such as consensus, guidance,
   a prior comparable period, or a ratio. The controller prepares the bounded,
   identity-masked H2 briefs before H1 and supplies a label-free inventory of only
   the optional fields and categorical values that actually exist in that pool.
   `applicability` is one canonical rule, never free prose or a conjunction:
   `all_ready_issuers`, bounded `business_description_topics:<term>|...`, or a
   single observed `industry_values`, `sector_values`, `exchange_values`,
   `market_cap_bucket_values`, `listing_age_bucket_values`, or
   `raw_info_source_type_values` rule. Non-description values must be copied from
   the supplied inventory. It therefore cannot hide analyst coverage, consensus
   data, disclosed quantitative guidance/actuals, revenue decomposition, market-data
   availability, classification metadata, or another absent field behind a visible
   clause; H3 tests document facts. At least one falsifier
   names both fixed groups and says that no separation, overlap, or reversal would
   refute the candidate relation, rather than listing only one-company edge cases.
   Positive/control labels are never redefined in parentheses as estimate-beat,
   price-performance, sustained-growth, or another candidate-specific outcome.
   The same boundary rejects membership-style clauses such as `positive cases are
   issuers that/with/as ...`: the feature is an expected difference between the
   already frozen groups, never a new definition of who belongs to either group.
   A parenthetical that merely repeats the same frozen label, such as `positive
   cases (the Discovery positive group)`, is an allowed alias rather than a
   redefinition. The label-bearing prefix may also use the label-free alias
   `(fixed Discovery group)`. An allowed alias cannot name a feature, result,
   issuer condition, punctuation payload, or different group.
   `query` contains only a concise two-to-eight-term retrieval topic; it is not a
   `Find companies where ...` instruction, numeric filter, or second time-window
   field. Applicability correction identifies the unsupported rule/value and
   replaces the entire field with one canonical rule from the supplied inventory.
   A stable card whose exact version
   has zero selection events and zero unique observations omits its otherwise
   repetitive all-zero `learned_profile` from the H1 model view. Once either
   count is nonzero, the complete anonymous learned profile is retained. The
   Registry artifact and frozen snapshot remain complete in both cases. The H1
   output contract describes keys and JSON types without a complete domain
   example that can be copied as an answer. When bootstrap `signal_need_items`
   are present, every returned hypothesis must directly ground itself in one
   item by sharing at least two non-generic normalized topic terms across its
   statement, applicability, expected pattern, and query. An ungrounded
   hypothesis receives the one bounded correction. When the supplied bootstrap
   backlog contains one or more `signal_need_items`, H1 must return at least one
   grounded hypothesis; a reasonless empty array is not evidence that demand is
   exhausted. Empty remains valid only when that demand list is empty. Stable Signal ids and registered deterministic
   function leaves are also a local exclusion boundary: a candidate whose own
   `hypothesis_id` or evidence `query` contains the complete non-generic semantic
   term set of an existing multi-term Signal is rejected into the bounded
   correction rather than sent onward as new Mining work. A stable metric named
   only as a comparison, control, or falsifier is not itself a renamed candidate.
   All locally decidable H1 semantic issues are returned together in the one
   correction, whose initial/correction requests retain one stable provider prefix.
   Semantic identity normalization preserves meaningful compact qualifiers such as
   `yoy`; it must not reduce `revenue_growth_yoy` to the generic pair
   `revenue growth` and reject a distinct revenue-composition hypothesis.
2. `H2 label-hidden canonical shortlist`: scan at most 96 issuer-distinct Discovery
   cases and locally filter controller-issued opaque `case_ref` values for every
   hypothesis from bounded point-in-time company briefs. Briefs may contain a business
   description or Item 1 business excerpt, industry, sector, exchange, coarse
   size/listing-age buckets, and Raw Info coverage, but never target
   company/ticker identity or outcome. An HTML filing excerpt must come from an
   actual non-navigation Item 1 block and begin at a substantive operating-
   profile paragraph; table-of-contents page numbers, cross-reference text,
   filing/website boilerplate, and other non-business fragments do not make a
   profile ready. A brief is ready only when at least one semantically usable
   business description/excerpt, industry, or sector exists. The target remains 32;
   H1 and the H2 shortlist are not run with fewer than 16 ready issuers or fewer than four
   locally hidden positive and four control issuers. Before the paid H1 call,
   the controller inspects the same deterministic case universe using only
   point-in-time local profiles. When the universe itself has enough positive
   and control cases to satisfy H2, but those local profiles cannot meet the H2
   minimum and no available authorized adapter can acquire the exact annual-filing
   profile request, the cycle pauses at `profile-preflight` without an H1 call,
   provider reservation, or data request. Its provider reason is the resolver's
   stable non-secret cause (for example `sec_user_agent_unconfigured`), not a
   generic adapter failure or any configured value. When acquisition is possible, H2
   scans only until the 32-case target and both hidden class minima are met;
   96 remains a ceiling, not a required acquisition count. H2 applies the single
   H1 canonical rule directly: all-ready matches every ready brief, observed
   categorical/coverage rules match exact visible values, and business-description
   topics require normalized literal term coverage. It preserves deterministic brief
   order and retains at most twelve refs per hypothesis. No model call, quote, reason,
   or correction exists at H2 because applicability is now locally decidable;
   retaining the former ranker would repeat the largest Slow context and allow a
   model to contradict the canonical rule. A valid empty shortlist therefore means
   no supplied brief matched, not that a model declined to choose one.
   Retryable provider failure
   creates a cycle-level control-plane pause with the opaque case ref and provider
   reason, preserves both pointers, and returns process exit 75 for exact-contract
   resume. It is not a hypothesis rejection or generic traceback. Deterministic shortage records
   `insufficient_h2_profile_readiness` without calling H1/H3 and is not a
   hypothesis failure.
3. `local feasibility`: reveal labels only inside the controller, require at
   least one issuer-distinct positive and one control, reserve later relevant
   cases for validation, and select at most two feasible hypotheses. An
   infeasible hypothesis becomes refined work rather than a model failure. For
   each feasible H2 shortlist, the controller walks the ranking in order and
   uses the next issuer of the same hidden class when an earlier case has no
   usable H3 evidence. The two-hypothesis contrast limit counts only evidence-
   ready comparisons; an evidence-unavailable early hypothesis must not prevent
   a later feasible hypothesis from using the bounded contrast budget.
4. `H3 contrast`: retrieve exact point-in-time Raw Info for the selected cases,
   then ask the model to support, refine, or reject each hypothesis and, when
   supported, return a complete candidate Signal plus fixtures. The controller
   stages and tests the candidate locally. Unique evidence packets live once at
   the top level, keyed by `(case, source_types, query, lookback)`; comparisons
   reference packet ids. News packets require a strong company-name or ticker
   match in title/body plus hypothesis-query relevance. Ticker-association
   metadata alone is filtered and audited. Every document must match the exact
   requested source semantics. Query relevance is evaluated over ordered normalized
   terms, not a two-word bag: a one-term query requires that term, a two-term query
   requires both, and a longer query requires at least two terms plus one consecutive
   query pair occurring in order within a short local term gap. Across the kept packet,
   every distinct non-generic query term must be covered. This admits
   complementary documents such as one `quarterly revenue` source plus one
   `analyst estimate` source, while excluding filing boilerplate that happens to say
   `quarterly`, `revenue`, and `estimates` in unrelated clauses. Substrings such as
   `ounce` in `announced` or `per` in `performance` are not matches. Directly issuer-routed
   SEC, market, and facts sources retain their
   issuer routing, but do not bypass this hypothesis-relevance check. The model
   excerpt is a deterministic normalized window centered on the strongest query
   match, with the complete immutable document hash retained as lineage; it must
   not substitute an XML header plus signature-page tail for substantive source
   text. Inline-XBRL `ix:header`/hidden resource bodies and script/style bodies are
   removed before query matching as well as projection, so taxonomy member names
   cannot manufacture evidence relevance. If any selected induction case has no usable document after these
   checks, that hypothesis is recorded separately as evidence-unavailable and
   is not sent to H3. Data absence is not learned as a hypothesis refinement.
   H3 must return exactly one decision per comparison. `refine` is reserved for an
   actual underspecification supported by visible evidence, `rejected` requires visible
   contradiction, and `inconclusive` records that the model-facing evidence is still
   semantically insufficient despite deterministic preflight. `inconclusive` is carried
   under evidence-unavailable, never as refinement or rejection; absence-language in a
   `refine`/`rejected` rationale receives the one bounded correction.

Exploration-driven cycles execute:

1. the controller selects a diverse issuer-distinct, label-stratified sample,
   reserves independent validation cases, and retrieves exact point-in-time Raw
   Info;
2. `E1 label-hidden extraction` describes recurring observable case signatures
   without outcomes; and
3. `E2 label-revealed discovery` contrasts those frozen signatures with their
   labels and may return supported candidates, refined patterns, or rejection.

Exploration is a bounded source of new hypotheses, not a separate promotion
path. The default cadence runs it periodically while hypothesis-driven cycles
exploit accumulated meta-memory. Both tracks use the same candidate contract
and stable promotion gate.

The Raw Info module remains an exact retrieval boundary. A model never emits a
free-form ticker for the controller to search: it ranks only allowed opaque
`case_ref` values from the supplied brief universe. The controller resolves
those refs to Discovery cases, checks point-in-time feasibility, and issues the
same bounded `RawInfoRequest` for every compared case. Model-facing evidence is
compact and immutable; complete documents remain the local lineage and final
Signal-execution boundary.

Cross-cycle H1 context preserves both the original H1 hypothesis and the exact
H3 refinement reasons. Evidence-unavailable work is carried with its distinct
status and data reasons. The next cycle must never receive a bare old hypothesis
under a `refined_hypotheses` label after discarding the reasoning that made it
refined.

Signal Update begins locally, not with `H_U`. The controller scans exact-version
learning profiles and selects at most three distinct actionable targets by
evidence priority, only after repeated distinct observations show an
explicit-attribution, directionality, or availability problem. If no target
crosses that floor, Update records `no_actionable_target` and makes zero model
calls. A fingerprint over each target version and supporting learning state
prevents an unchanged issue from being proposed repeatedly.

For a selected target, local code executes `vCurrent` on a deterministic,
issuer-distinct Discovery sample and partitions it before model invocation.
Induction contains both counterexamples and successful/neutral boundaries when
available; holdout issuers are reserved and never enter the Update request.
Point-in-time Raw Info is retrieved through the normal resolver, masked into
bounded anonymous evidence packets, and the local audit records the split.
Insufficient induction support yields a durable `defer` without calling the
model.

For each locally prepared target, one `H_U` call returns exactly one of
`no_change`, `defer`, or `update`; a Slow cycle therefore makes at most three
Update semantic calls. Only `update` carries a complete candidate `vNext` with
fixtures. Targets are audited and recovered independently, so one target's
invalid output, deferral, or insufficient evidence does not discard another
target's candidate. The controller preserves Signal identity, category,
execution type, evidence policy, description, and deterministic function;
stages the candidate; runs the normal contract/fixture checks; and evaluates it
only on the issuer-disjoint holdout. The model cannot see holdout results or
promote its own output. The durable `signal-update-audit-v2` portfolio records
the target limit, selected-target count, aggregate model usage, and ordered
per-target `signal-update-target-audit-v1` entries so retries can reconcile each
issue fingerprint independently.

Mining role calls receive literal structured-output contracts for hypotheses,
rankings, signatures, decisions, canonical `SignalSpec`, executable fixtures,
enums, and registered deterministic functions. Update has one literal decision
and candidate contract; it has no domain tools. A new deterministic formula is
a code-reviewed framework change; Mining or Update may use only functions
already registered by the runtime.

Discovery identity removal is owned by the controller at the boundary where one
case's source-derived brief, evidence packet, Signal-result view, or bootstrap
need is assembled. That boundary uses the complete local alias inventory and a
post-mask scan. An aggregate Slow role must not recursively substitute the full
Discovery-wide alias inventory through an already anonymous structured payload:
derived brands such as `Open`, `Match`, `Alpha`, or `News` can also be legitimate
source types, enum values, Signal identifiers, and ordinary analytical prose.
H1 therefore receives its producer-validated payload unchanged and applies only
a non-mutating fail-closed scan for strong identity terms: opaque case/company
ids, exact ticker-like aliases, and complete multi-word formal-name components.
The same strong-term rule applies to free-text Mining/Update outputs.
Because a bare two-character uppercase token can be both a ticker and common domain
vocabulary, it is not a sufficient leak by itself: two-character ticker aliases are
rejected only with explicit ticker syntax such as `$XX`, `ticker XX`, or
`NASDAQ: XX`; longer uppercase tickers remain exact case-sensitive guards.
An output leak is rejected into the one bounded correction without echoing the
leaking value; the adapter never silently edits an accepted schema, enum,
identifier, or candidate. H2/H3/E1 and Update retain their local per-case
mask-and-scan boundaries before request reservation. Their aggregate adapters
still reject outcome fields, but do not rescan request prose against every other
Discovery issuer: a named partner/customer in one case or a product code equal
to another issuer's short ticker is not the current target's identity. Their
free-text outputs retain the strong Discovery-wide leak guard because accepted
reusable Signal text must not name a sampled issuer.

All candidates are staged first. The orchestrator then executes each
candidate's non-empty point-in-time fixtures through the real candidate
executor and checks expected canonical state, schema, leakage (including
discovery-case aliases and fixture data), evidence traceability, semantic
duplication, and version progression. Ambiguous common-word ticker aliases do
not trigger identity leakage solely by ordinary prose use. Contract success
means only "well formed and executable".

Before automatic promotion, the orchestrator runs a separate paired
effectiveness gate over issuer-distinct, label-stratified Discovery cases from a
frozen local Raw Info snapshot. Cases used to induce or contrast the candidate
are excluded. For hypothesis-driven candidates, the gate first consumes later
unused relevant cases from the label-hidden ranking, then fills any remaining
slots deterministically from the Discovery pool. `vCurrent` and `vNext` receive
the same cases, prediction times, identity routing fields, model settings, and
Raw Info corpus. The audit records availability, decisive-state count,
directional correct count, and directional wrong count. An update must retain
availability, not reduce correct states, not increase wrong states, and strictly
improve at least one of those quantities. A new Signal must meet the minimum
availability and decisive-support floors and have more correct than wrong
decisive states.

A contract-valid candidate with directional induction support but too few
independent usable/decisive cases is `provisional`: it is persisted for later
re-ranking or evidence accumulation but is not promoted. A candidate with
enough independent evidence that fails directionality, regression, or strict
gain is `rejected`. Only a candidate satisfying the unchanged effectiveness
gate is `promoted`. Thus a sparse Raw Info sample does not erase a plausible
idea, while lack of evidence still fails closed at the stable Registry boundary.
This is a Signal-level safeguard, not a claim of downstream Plan-F1 causality;
downstream impact is observed only in later Fast rounds.

Passing candidates are recorded by exact candidate hash (spec + skill + tests)
together with the versioned contract and effectiveness audits. The complete
validation outcome is staged before stable mutation. The orchestrator then
automatically promotes all passing hashes as one cycle-identified, recoverable
batch and advances the Registry version once. Empty passing batches do not
advance it. The next Fast Loop sees the resulting snapshot; the just-completed
Fast Loop remains bound to its input snapshot.

Each Mining stage has its own explicit JSON contract and at most one structured
correction. H2 may reference only supplied hypothesis/case refs; H3/E2 may
reference only supplied hypotheses/signatures and may return only complete
candidate drafts. The controller records every stage request/usage, local
selection, Raw Info resolution summary, decision, staged candidate ref, and
provisional/refined/rejected disposition in the Slow-loop audit. Update records
the exact target fingerprint, local target/induction decision, single role
request/usage, returned disposition, staged ref if any, and later local
validation disposition.

Mining cannot stage an existing stable `signal_id`; existing identities belong
to Update and must use exact `vNext`. Diagnosis or a proposed Signal object is
not itself a valid candidate. Structured role errors may be repaired only by
the one frozen correction boundary; local staging/validation errors do not
become another model call.
Missing required candidate fields, invalid enums, and other `SignalSpec`
deserialization failures are exposed to the agent as domain validation feedback;
they never escape as raw parser exceptions and are never filled with defaults.
Malformed outer JSON is corrected with its exact parser message and bounded raw
output, not replaced by a generic "unknown action" message. Role output and
local validation failures remain in the durable Slow-loop audit.
External-approval pauses and other orchestration control-flow exceptions are not
domain validation feedback: every Fast evaluator, structured Slow role,
candidate fixture, and local controller propagates them unchanged to the CLI.

Every durable Plan evaluation attempt contains its complete serialized case
trajectories, including DataGaps and stop reasons. The derived capability
backlog is rebuilt from those durable trajectories while preserving the source
types available from the current resolver, so the Slow loop receives the real
Fast-loop capability gaps rather than an empty or accidentally reopened report.
For ordinary cycles it contains data capability gaps. For an explicitly frozen
bootstrap it additionally merges the manifest's identity-masked
`signal_need_items`; local refresh cannot erase them. The complete derived
backlog is part of each Slow agent workspace input; merely writing
`capability_backlog.json` without exposing it to the agents does not satisfy
this contract.

## Persistence and Completion

Fine-grained Plan, trajectory, candidate, and response artifacts may be written
as soon as available. A round becomes official only in this order:

Exact request payloads include only semantic model inputs. Runtime usage,
provider cost, cache-hit state, and other execution-accounting fields remain in
audit trajectories but never enter Predictor context; therefore a resume from
an exact cached response renders the same downstream request.

```text
all candidate records and trajectories
-> metrics and Plan reflections
-> archive selection state and round meta entry
-> immutable round checkpoint
-> atomic state.json:last_completed_round advance
```

Restore, reporting, and parent selection ignore artifacts above the pointer.
On restart, an already staged plan, meta record, or checkpoint is reused only
when its canonical JSON exactly matches the artifact currently being committed;
a mismatch fails closed. The pointer remains the last write. Exact external
responses are separately reusable only under their exact request hash.
Restore also verifies that every checkpoint Plan id resolves to a record with
the same Plan id and round id, that checkpoint Plan ids are non-empty and
unique, and that the state pointer's checkpoint reference resolves to its exact
last round independent of an absolute-versus-relative path spelling. The same
rule applies to checkpoint meta references. A self-consistent but cross-linked
record cannot enter parent selection.

One Fast/Slow cycle has a second atomic `cycle_state.json` marker. It records the
cycle id, starting committed round, fixed round target, current Fast/Slow phase,
input Signal Registry version/hash, current committed output Registry
version/hash, and last completed cycle under the frozen run-contract hash.
It also records `cycle_mode`. Normal cycles require a positive Fast target;
`slow_bootstrap` requires exactly zero and a contract-bound bootstrap manifest.
After `Ctrl+C`, the supervisor derives completed Fast work from
`last_completed_round`, runs only the remaining rounds, and reuses an exact
staged Slow validation/transition/result before advancing the completed-cycle
pointer. The validated-batch artifact is durable before Registry mutation; the
final Slow result is durable before the cycle pointer. It never infers
completion from individual candidate files or an event log.

`experiments/trajectory.jsonl` is the append-only debug stream for lifecycle,
request/cache, round, candidate, case, score, Top-K, Slow-loop, interruption,
and resume events. Each line carries a UTC timestamp and monotonic sequence
number; it is diagnostic evidence, not a completion authority. A
truncated/corrupt line is counted and ignored so it cannot block recovery or
impersonate a commit.

## CLI Visibility and Local Dashboard

The API runner accepts a structured progress callback. The CLI renders those
events immediately with flushing and includes cycle/round ids, candidate Plan
summaries, per-case progress, request/cache state, candidate metrics, current
quality-diverse Top-K scores, checkpoint commits, resume decisions, and Slow
Signal candidate status. It must never print prompts, credentials, raw packet
content, or identity-masked Predictor inputs.

`init`, local preflight, migration, freeze, `run-cycle`, and `run-loop` require
an explicit global `--raw-info-root`; none may infer a workspace-private Raw
Info directory. `run-cycle` executes or resumes one frozen Fast/Slow cycle.
`run-loop` is a thin supervisor that starts another bounded cycle only after the prior cycle commits;
zero `--max-cycles` means continue until `Ctrl+C`. `KeyboardInterrupt` leaves
committed pointers intact, records an interruption event at the CLI boundary,
refreshes reporting, and exits with the conventional interrupted status. This
does not widen the frozen attempt or cost ceilings.

`scripts/run_information_plan_evolution.sh` is the stable operator-facing
launcher. `new` requires an unused workspace, the global Raw Info oracle, and an
already human-approved feasible dataset; it initializes and freezes one v6
contract, then stops at the first exact LLM-request approval boundary without
LLM execution. When the operator explicitly supplies `--data-external`, the
initial bounded run uses that independently frozen Raw Info authorization while
preparing shared evaluation inputs; the flag must not be consumed only by
contract creation and silently dropped before readiness. `resume` requires the
same workspace/oracle/dataset and
derives progress only from committed pointers. External execution is available
only in `resume` mode with both `--external` and an acknowledgement equal to the
stored contract hash. The launcher composes the Python CLI rather than
implementing a second state machine. It never persists or prints a key, opens
Locked Test, promotes an unvalidated or changed Signal candidate, infers
completion from files, or bypasses request leakage, cost, attempt,
dataset-feasibility, and contract-hash gates. Validated Signal auto-promotion is
part of the bounded cycle state machine, not external-call authorization. The
former DeepSeek-named shell is only a compatibility forwarder to this entry and
carries no workspace, model, budget, or approval defaults.

The stable cold-start default is two Fast rounds with three independently
sampled candidates per round. A one-candidate round remains available as an
explicit low-cost diagnostic, but it is not the operator default because it
provides no within-round quality comparison and makes a first-round TP miss too
likely to halt the fitness-gated run.

Source-data acquisition remains a separate two-step authorization in the stable
launcher. `new --data-external` freezes the versioned broad-research Raw Info
profile: wildcard provider/capability/source-type authorization for every
historical adapter registered by the contract-bound code revision, plus
positive request ceilings. Operators may instead supply a complete restrictive
set of all three allowlists and both ceilings. `new` performs zero data calls
unless the operator supplied `--data-external`; `resume` must additionally
receive the data-external execution flag. Requesting
runtime data execution when the frozen contract disabled it is an explicit
pause/error, not a silently disabled resolver.
Provider/capability/source-type or ceiling options without `--data-external`
are rejected rather than frozen as dormant authorization.

The CLI classifies exhausted transient transport failures (timeouts, connection
errors, incomplete responses, HTTP 408/429, and HTTP 5xx) with a dedicated
temporary-failure exit status. During an invocation-specific fixed wall-clock
window, defaulting to ten hours, the launcher automatically restarts the same
exact `run-loop` only for that status, using exponential backoff capped at one
minute. Every restart uses the same frozen contract, exact cache, case
checkpoints, and durable attempt ledger, so the existing attempt/cost ceilings
still apply. The window and backoff are supervisor controls, not evolutionary
state and not permission to mutate a frozen contract. `Ctrl+C`, provider
rejections, invalid model content, contract conflicts, budget exhaustion, and
other deterministic failures remain terminal and are never converted into
unattended retry loops.

The single human-facing entry remains
`runs/cold_start/evolution/evolution_dashboard.html`. A read-only builder scans
direct child workspaces, trusts only committed round/cycle pointers, retains
legacy history compatibility, and rewrites the adjacent local data/index
artifacts. The page selects a run in-place and shows Binary F1 by round,
candidate scatter/median, committed best, current Top-K, cycle/resume status,
trajectory counts, stop reasons, and recent debug events. Locked Test metrics
are never included.

## Frozen Run and External-Call Contract

Before external execution, the runner writes a secret-free frozen manifest that
binds dataset/splits, Signal snapshot, fixed priors, role-model/provider routing,
code revision, runtime limits, maximum attempts, and cumulative cost. API-key
availability is recorded only as a boolean; secrets are never serialized.

Every newly rendered request is persisted and recursively checked for outcome
fields and future facts before network I/O. Predictor requests additionally
arrive through a current-case target-identity mask-and-scan boundary; they do not
scan the full dataset alias inventory because legitimate third-party evidence
can share names or short tickers with unrelated issuers. Structured roles
include the provider JSON-object response format in both
the persisted exact request and the provider call, so prompt compliance is not
the only JSON boundary and the format setting participates in the cache hash.
Every structured system message also explicitly requests one JSON object, as
required by providers that reject JSON-object mode without that input token.
The durable attempt ledger reserves an attempt and its conservative cost
ceiling before a call, then records completion or failure. An exact-response
cache is keyed by canonical request hash and is evidence of reuse, not evidence
of round completion. Dry-run and preflight perform no external calls. Locked
Test remains sealed from all ordinary commands.

Missing credentials, a missing/mismatched external acknowledgement, and
exhausted attempt/cost ceilings are control-plane pauses. They propagate across
case evaluation and both Slow agents, leave round/cycle pointers unchanged, and
must never be persisted as Plan failure, Signal-agent schema failure, or
`round_rejected`. The CLI returns a structured reason rather than a traceback.
Only content/schema failures attributable to a bounded candidate may become
candidate diagnostics.

## Local Point-in-Time Migration

Legacy cold-start cases, source documents, and adjusted-price artifacts are
inputs to an explicit migration step, not implicit runtime databases. Migration
must record source hashes, preserve `published_at/available_at`, recompute the
current six-month five-day-smoothed `realized_max_multiple` label from adjusted
prices, assign stable case ids, and materialize a reviewed issuer-disjoint split
manifest. Older terminal-return labels cannot be reused as if they were the
current label. Missing symbols/cases are reported and excluded, never silently
imputed.

## V1 Non-Goals

- Shapley credit or trajectory counterfactuals;
- autonomous Signal routing or stopping policies beyond the bounded learned
  profile supplied to the existing selector;
- Signal interaction graphs;
- automatic optimization of `H_R/H_P/H_E/H_U`;
- meta-meta evolution;
- complex multi-agent communication;
- automatic locked-test access or production promotion; and
- any order placement, brokerage, leverage, or position sizing.

## Implementation Order

1. Raw Info Store, Signal Registry/spec/result/executor, and 12 seed Signals.
2. Adaptive Information Plan runtime with one manual Plan.
3. Two-stage evaluation, label reveal, self-reflection, and trajectories.
4. Plan Archive, embedding, diverse Top-K, and random exploration parents.
5. Independent candidate sampling, fast-loop evaluation, `H_R`, and FIFO meta.
6. Version-bound Signal learning and observed-policy compatibility statistics.
7. Locally orchestrated dual-track Signal Mining into candidate storage.
8. Locally triggered one-call Signal Update, executable validation, recoverable
   automatic batch promotion, and versioned transition.

## Testing

Tests must prove point-in-time reads, dynamic Signal selection, whole-batch
reflection, mandatory prediction persistence before label access, two-stage
metric math, complete Plan records, quality-diverse selection, independent N
proposal calls with distinct slot identities, grounded FIFO updates,
observed-policy counts, candidate
isolation, executable candidate fixtures, exact-hash automatic promotion checks,
frozen fast-loop definitions, locked-test
isolation, runtime budgets, authoritative completion pointer behavior, and one
offline end-to-end dual-loop cycle. Recovery tests must additionally cover
legacy horizontal-only meta restoration, exact additive reflection round-trip,
original/vertical/horizontal layer preservation, FIFO eviction by whole entry,
identity-free proposer handoff of outcome-aware reflection memory,
independent case-trajectory reuse, interrupt-after-round recovery with no extra
Fast rounds, exact staged Slow-validation/transition/result recovery, a next
cycle that uses the promoted Registry without reevaluating historical Plans,
append-only debug events, CLI
progress flushing, and dashboard filtering to committed pointers. Dataset/data
recovery tests must prove that an unavailable Random case is replaced before
snapshot finalization, fixed Anchor identity is never substituted, a shared
source gap cannot create `round_rejected`, and a retryable shared-data pause
uses the supervisor's temporary-failure exit status.
