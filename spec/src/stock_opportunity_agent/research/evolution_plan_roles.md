# Evolution Plan Roles

Source wording describes its own availability time. Initialize/Reflect must not
promote an expired dated event or an old source's “currently” into a claim that
it remains current at prediction_time. Predictor receives the cutoff explicitly
and retains per-card availability dates; posthoc uses that same cutoff.

The blind LLM Predictor exposes an optional exact initial-request token estimator.
Estimation and execution share one system prompt and payload, including transport
identity projection and reasoning headroom. It does not estimate research truth
or guarantee unlimited correction attempts fit the remaining budget.

Price-baseline distance is outcome-definition arithmetic, not independent
counter-evidence against a surge. Predictor instructions distinguish it from
source-backed contrary evidence and require computed price-change cards for
quantitative price-trend claims; an absent computed window remains uncertainty.
Computed returns must retain their own first/last observations and dates;
unrelated Basic Info prices cannot be attached to that return. Explicit prose
of the form "from X to Y, a Z% return/increase/decrease" is checked for arithmetic
consistency, with rounding tolerance and signed decrease handling. A contradiction
creates a typed issue for that single reason/uncertainty; shared incremental
correction preserves other valid fields and revalidates the complete prediction.
This bounded check does not claim to verify arbitrary prose or forecast quality.

## Purpose

Implement structured adapters for Plan proposal, criticism, adaptive research,
Signal retrieval, blind prediction, and Plan reflection.

## Invariants

- H_init describes the actual final Predictor visibility: the final assembly
  includes Basic Info cards, accepted state and later stage products. Its
  instructions must not claim that only the compact state is forwarded.
  Initialize still retains a bounded set of material sourced claims.

- Adapters translate model output into core protocols; they do not own engine
  state or commit pointers.
- Prediction-time roles never receive labels or target identity.
- Post-label Jev feedback includes deterministic proper-score and concentration
  diagnostics. Post-hoc reflection and the Plan critic must explain recurring
  low-support correct calls, high-confidence errors, and collapsed magnitude
  choices. Proposer-visible meta derives the same aggregate from immutable case
  feedback and requires a concrete Plan change or explicit defer/reject rationale;
  confidence itself remains excluded from fitness and is never maximized alone.
- Correction and fallback behavior delegates to the shared validators. Plan
  proposal corrections are checked with the same field/member granularity as
  controller corrections: a leaf path such as `B.requests[i].description`
  authorizes only that field, never sibling fields, whole-request
  replacement, or inserting another request.
- After bounded correction, typed answer-ownership failures may retain the same
  selected Signal as context only, with full revalidation and unresolved needs.
  This removes an unverified routing claim without inventing research evidence.
- Duplicate direct ownership is detected across the complete selection set.
  The validator authorizes context-only conversion per exact conflicting row
  and Signal identity. If exactly one full-answer claim exists, it is retained
  unchanged and partial claims become context only; otherwise every conflicting
  direct claim becomes context only. This preserves selected Signals and target
  indices, never chooses an ambiguous owner, and runs complete validation.
  Typed mechanical conflict repair precedes LLM correction; other ownership
  failures retain their existing bounded semantic correction policy.
- ResearchState summary counts, text lengths, and summary bytes are advisory
  compression targets. Transport token budgets remain hard limits; evidence,
  provenance, PIT boundaries, and need ownership remain validated.
- A terminal batch containing only unavailable Signals has no new evidence to
  reflect on. Return the previous state with only decision changed to finalize,
  without a model call or fabricated findings.
- Information Plan proposals express cross-issuer business/risk research through
  the generic `filing` capability unless an exact SEC form is itself material to
  the research question. They must not assume every U.S.-listed issuer files
  domestic `10-K`/`10-Q` forms; the resolver selects applicable domestic or
  foreign operating reports while preserving exact-form restrictions.
- Plan proposal retains the complete additive FIFO in storage but receives a
  bounded brief working view. Each brief keeps its source handle, applicability,
  limitations and verification state. The role can request registered original
  units with `read_refs` before returning a Plan; each disclosure is masked,
  validated, bounded and audited under the exact request preflight. Unknown,
  repeated, over-budget and cross-role reads fail closed; no arbitrary path is
  resolved. Unread/omitted history remains explicit and available in storage.
- Case, Plan and Round reflection author structured `reflection_items` with
  full detail and an actionable `brief` together. Higher layers may select
  lower items unchanged, or add their own explicitly sourced insight. Runtime
  supplies source catalogs, stable item IDs and deterministic outcome facts;
  model-authored success/failure claims cannot contradict them. Existing string
  categories remain derived compatibility projections, never a second authored
  output. Legacy archives load unchanged and are marked unreviewed in views.
- Critic and Round inputs also use bounded brief/catalog views; neither may
  conceal an unbounded full trajectory or source catalog beside a bounded
  brief. Complete anonymous original units remain available through the same
  finite read/browse exchange (three requests, 48,000 aggregate UTF-8 bytes).
  Case-level correctness and aggregate diagnostics remain runtime facts. Read
  usage is counted with the owning role and every transmitted request is
  persisted by the normal caller. Partial coverage is explicit, never an
  assertion that omitted evidence does not exist.
- Retrospective prose may discuss observed probability distributions and time
  horizons. The Plan-instruction semantics filter must not reject the very
  calibration diagnosis requested by a reflection prompt. Fixed semantics are
  immutable in runtime and validated when an actual Plan is proposed.
- H_reflect emits snapshot-bound state operations; runtime owns copying and
  retaining unchanged state. The same ordinary evidence, need-ownership,
  temporal and whole-state checks run after assembly. The first-answer
  prompt itself discloses the text-array field shapes (never an evidence
  object), the open_questions versus next_information_needs separation with
  exact-string deduplication, and the numeric-belief copy rule, so these
  validator obligations are visible before any correction is spent. Structured correction
  returns only authorized operations against the latest failed assembled state;
  a valid sibling is not rewritten to repair another sibling. A complete object
  is only necessary when no usable structured baseline exists.
- A `partial` answer's residual need must retain the targeted information
  need's temporal scope. Production injects the actual runtime prediction
  date into the Signal Retrieval Agent through the same optional
  `set_evaluation_context` setter the controller uses, resets it per case so
  reuse cannot carry an earlier cutoff, and exposes it in the routing payload
  as control data. Explicit dated and symbolic prediction-time cutoffs are
  validated alike against that actual date through the shared bounded-residual
  representation: routing rejects a residual exactly when the reflection
  temporal guard finds no bounded restatement (realized future facts, an
  invalid parent, or an unbounded parent that lends no cutoff or framing),
  and a representable literal is accepted while the consumer normalizes once
  through the same shared rule, so producer and consumer never demand
  contradictory exact strings. The producer correction names the actual
  prediction boundary, the inherited cutoff clause, and the framing marker,
  so a truly unrepresentable residual is repaired before any Signal executes
  instead of failing only at the pre-reflection boundary. Called without a
  runtime date, routing never fabricates a date, parent year, or present day:
  it keeps only the sound dateless explicit-cutoff check, and a symbolic
  cutoff alone triggers no dateless producer rejection. Historical residuals
  that reference only years at or before the actual prediction date stay
  accepted and are never reframed as forecasts.
- Reflection validates persisted legacy selections against the actual runtime
  prediction boundary before building the H_reflect prompt. A partial answer
  whose residual need cannot be represented within that boundary is rejected
  fail-closed without a model call; the unresolved demand is never silently
  deleted, finalized away, or handed an impossible prompt. Without a runtime
  evaluation context there is no boundary to enforce, so legacy no-scope
  behavior is unchanged.

## Shared stage boundary (2026-10-01)

Follow [stage contracts](stage_contracts.md) for dependency checks, omissions,
partial mechanical repair and immutable accepted units. A newly resolved
question conflicting with an unanswered retained need publishes both correction
paths. Exact runtime restoration of that need may remove only the explicitly
identified unsupported newly resolved question. The final Predictor input is
the typed assembled stage products, not only the final state or full raw prompts.

## Runtime price arithmetic

Research controller, blind Predictor and case posthoc adapters use the shared
checker at the exact authored text path. First requests disclose its arithmetic
contract. Posthoc full parsing and row salvage invoke the same role validator.
See the owning [shared arithmetic contract](evolution_output_validation.md#shared-runtime-price-arithmetic-2026-10-02).
First authoring requests distinguish required gain from a close and shortfall
relative to a target. Newly authored reflection actions expose independent
brief/detail policy violations together, using the shared fixed-semantics guard;
the scoped patch changes those fields and preserves other items and source data.

## Reflection statistics ownership (2026-10-02)

Plan Critic supplies the same runtime-owned statistic handles as the later
Round/archive index. Critic registers existing metrics, magnitude and completion
products after building the authoritative case index. Round derives its handles
from the approved per-Plan model projection, including available cohort metrics.
The shared initial reflection contract requires citing `runtime_plan_statistics`
for numeric evaluation claims and naming the owning Plan/cohort/population.
A case source never establishes aggregate statistics. Round compares per-Plan
values and cannot call one Plan's combined cohort the pooled round. Legacy
statistics-unchecked briefs are retrospective material to inspect, not verified
statistical evidence. Shared repair authority permits exact source/scope and
text changes; it never permits editing runtime statistics.

## Computed window visibility (2026-10-02)

Controller keeps the runtime typed compute cards separately from their readable
model view, for State period validation. Readable summaries include literal
endpoint dates when supplied, so the required distinction between trading-day
windows and the calendar-month outcome horizon is visible on the first call.
Prediction and Posthoc receive the unchanged typed cards. Exact window-label
repair uses the shared output validator and never changes the metric/window.
In-loop computed cards join validation before the returned state is parsed and
remain visible on subsequent reflections in the same case. Initial case setup
resets this context even when no market metric is available, so a reused
controller cannot carry another issuer's computed window into validation.
Initialization/reflection prompts use runtime anchors and cards to orient
qualitative judgments and evidence needs. They do not request numerical control
restatements in current_beliefs, contradictions or supporting_evidence. Literal
issuer facts still follow existing quote/claim rules. No source metadata/date or
filing-form identifier is invented inside a quote to justify a numerical claim.
State need not create a citation for a runtime control: the unchanged control
and Basic Info blocks are assembled separately for Predictor.
