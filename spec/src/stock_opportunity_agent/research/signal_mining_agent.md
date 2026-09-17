# Signal Mining Agent (LabelAwareMiningController)

## Purpose

Define the controlled, label-aware Signal-mining controller and its shared PIT
Evidence Graph that replace the production H1/H2/H3 and E1/E2 mining chain.
The shadow-acceptance gate defined in the owning action plan passed on
2026-09-17 (six additional live shadow rounds, all terminal candidate with
invariants clean, plus two committed production cycles): the production
mining entry is now the controller, dispatched whenever a frozen v8 sampling
manifest is active and the mining model exposes a JSON role caller. The
legacy H/E chain remains callable for read-only history replay and for
H/E role-protocol mining models; archiving the legacy production path
follows the repository removal discipline after the post-cutover
observation cycle.

## Invariants

### Shared Evidence Graph

- The graph is virtual and lazy. Facts project only from documents already
  selected through the authorized resolver and loaded under the point-in-time
  rule `available_at <= prediction_time`, reusing the shared SEC structured
  fact selector and the unchanged-file parse cache. No full-corpus
  materialization exists in any phase.
- Every Fact node binds concept, unit, period, value, an opaque document ref,
  a verbatim exact span, the content hash, and availability time as one
  indivisible unit. A character window may never present a number detached
  from its concept/unit/period binding.
- Relation nodes are constructed only by deterministic code within three
  bounded scopes: same-concept record pairs under the existing
  comparable-period rule; numerator/denominator pairs computed only when
  `compute_statistic` is explicitly requested under its frozen rule
  vocabulary; and co-occurrence among facts inside documents of one case that
  were already fetched. There is no cross-case fact enumeration, no
  all-pairs relation construction, and no precomputation of unrequested
  combinations. Graph extent therefore equals requested extent and inherits
  the frozen budgets.
- Narrative evidence enters as bounded event views with exact spans and
  source lineage; it never synthesizes numeric facts. Narrative events
  project only from the narrative source families (`filing`, `transcript`,
  `news`): structured families that project no facts — price series, raw
  provider envelopes — remain fetched documents with ledger coverage and are
  never laundered into narrative events. Event excerpts reuse the production
  visible-text projection with its substantive anchors, so SEC SGML/HTML
  boilerplate never occupies an event slot.

### Tool surface

- Exactly three runtime-owned tools exist in the first version:
  `fetch_evidence`, `compute_statistic`, and `read_span`. General search,
  arbitrary code execution, arbitrary file reads, and candidate mutation are
  not tools and must not be added without a spec change.
- Every tool call is executed by the runtime, enforces point-in-time and
  identity masking on outputs, charges the shared attempt/cost ledger, and
  appends one mining-ledger entry whose input and output hashes are recorded.
- `fetch_evidence` returns, together with its bounded results, the requested
  source family, query, window and case refs, the selected documents/facts/
  relations, the documents or concepts excluded by limits, query coverage,
  whether unread same-source evidence exists, and per-item content hashes and
  PIT verdicts. A bounded view never proves absence: insufficient coverage
  may support only `evidence_unavailable`, never a domain claim that a fact
  does not exist.

### Controller discipline

- The controller is a fixed state machine, not a general agent framework.
  Each model step returns exactly one action from the closed enum
  `inspect_manifest`, `inspect_catalog`, `fetch_evidence`,
  `compute_statistic`, `read_span`, `compare_groups`, `propose_candidate`,
  `record_deferred`, `record_no_pattern`. The runtime alone decides
  admissibility, executes the action, writes the ledger, enforces
  termination, and admits a candidate into validation.
- Seed states move only along `ready -> exploring -> evidence_ready ->
  candidate_proposed -> locally_validated -> terminal`. The disjoint
  non-domain terminal states `technical_failure`, `evidence_unavailable`,
  `deferred_budget`, `no_pattern_with_coverage` may never be conflated with
  one another, and a technical failure may never be counted as a domain
  no-pattern.
- Budgets are dual-dimension and frozen in the run contract: heavy actions
  (`fetch_evidence`, `compute_statistic`, `read_span`, `compare_groups`,
  `propose_candidate`) share a per-seed cap, initially 12; light actions
  (`inspect_manifest`, `inspect_catalog`) draw from a separate small cap,
  initially 4, so enumeration is not starved by evidence work. All actions
  remain under the existing attempt/cost and token ceilings. Numbers are
  finalized from offline replay; the model can never adjust them.
- A heavy action requested after the heavy budget is exhausted is a
  runtime-owned state inadmissibility, not a model contract fault. The model
  receives one bounded chance to switch to an admissible action (including
  `record_no_pattern` with ledger-backed coverage); a repeated inadmissible
  heavy action ends the seed deterministically as `deferred_budget` with a
  resumable ledger, never as a technical failure.
- Every model view carries runtime-owned progress surfaces so the model can
  observe its own tool results: an `evidence_digest` (fetch count, families,
  fact/event/relation counts, per-concept positive/control case coverage) and
  the `last_action_result` of the previous executed action. A view that hides
  what fetches already collected invites redundant sweeps and is a defect.
- A candidate's measurement observable must be a genuinely new measurement:
  it may not reuse or version the base name of any Signal in the stable
  catalog, because changing an existing Signal belongs to the unchanged
  Update path. The runtime rejects catalog-duplicating observables at
  proposal time.
- Candidate evidence is semantically grounded, not merely present: every
  known concept named by the observable or normalization must be backed by
  at least one cited fact of that concept, and `compare_groups` results
  carry the fact_ref behind each value so the model can cite the evidence
  its measurement actually consumes. Ledger-existence alone never proves
  grounding.
- Free-form thoughts are not persisted. Auditable reasons exist only as
  structured action rationales, evidence refs, and terminal dispositions.

### Seed A: hypothesis validation

- Seed inputs are the trajectory and Slow feedback, meta-memory, Signal
  statistics and failure types, the value-free `measurable_evidence_manifest`,
  the stable Signal catalog, and the dev positive/control case index.
- A hypothesis is admissible only when it maps to a manifest evidence family,
  has an actually reachable evidence path confirmed after tool execution, is
  not a duplicate of an existing Signal, states its measurement and the fixed
  positive/control comparison, uses no future data or invented target, and
  carries at least one executable falsifier. Manifest membership is necessary,
  never sufficient.
- The Seed A terminal must attach a need-disposition ledger assigning every
  backlog need ref exactly one disposition from `new_measurement`,
  `deferred_measurement`, `update_existing`, `repair_dependency`,
  `not_testable`, `fast_plan_action`, validated by the existing H1 v7
  disposition checks. The capability-backlog loop keeps exactly one owner.

### Seed B: open-ended label-aware discovery

- Seed B uses the same Evidence Graph without a prior hypothesis and searches
  for recurring Fact/Relation combinations across the labeled dev groups. It
  is supervised mining and is named accordingly; the term "unsupervised" is
  invalid for it.
- Dev labels reach the model only through the runtime-owned structured label
  map over opaque case refs, identical in authority to the existing contrast
  label mechanism. Any model-authored label assignment, rewrite, or expansion
  in free text is invalid and triggers structured correction.
- Check/holdout labels and their evidence never enter either seed's context.
  Identity, ticker, file ordering, and fetch-status features are not
  acceptable Signal inputs unless the Signal definition explicitly studies
  them and they pass independent validation. A discovered candidate must be
  recomputed and evidence-checked by local code before validation.

### Label, PIT, and overfitting boundaries

- Dev labels may be used for discovery and candidate proposal; holdout labels
  only for final validation; the Fast Predictor never receives posterior
  labels or mining rationale.
- Post-outcome documents and realized results are not discovery inputs.
  Source-coverage differences are not business features. Holdout failure may
  not be answered by editing the candidate and re-counting the same attempt
  as one validation.
- Candidates originate only on the frozen dev cohort; check/holdout issuers
  stay disjoint; every candidate enters the unchanged fixture,
  issuer-disjoint holdout, paired-effectiveness, and atomic-promotion gates.

### Mining ledger

- The ledger is runtime-owned and append-only within a cycle. Model-authored
  content is limited to structured rationales. Recovery replays from the
  committed checkpoint without re-consuming completed actions.
- Terminal consistency requires: every candidate evidence ref exists in the
  ledger; every promising branch either becomes a candidate or carries an
  explicit abandonment reason; `no_pattern` cites the actually explored
  evidence families, concept/relation counts, and uncovered scope; Seed A's
  need-disposition ledger covers all backlog need refs; and technical
  failures, quota pauses, and evidence unavailability never enter domain
  no-pattern statistics.
- Ledger feedback units enter the next cycle's reflection and may change only
  future search strategy, never frozen samples or historical validation
  results.

## Interfaces

- Module input: frozen `slow_input.json` cycle artifacts (sampling manifest,
  feedback rows), the resolver-backed raw-info store, the Signal registry,
  the measurable-evidence manifest builder, and the shared transport/cost
  ledgers.
- Module output: candidate Signal proposals with complete evidence grounding
  that feed the existing candidate-validation pipeline unchanged, plus the
  cycle's mining ledger and terminal dispositions.
- The controlled closure harness (`mining_closure.py`) provides eight fixed
  scenario fixtures — single fact, multi-period, ratio, cross-document,
  narrative event, insufficient evidence, technical failure, and no-pattern
  with coverage — over synthetic issuer-disjoint dev/check cohorts, and
  drives at least one candidate through the complete local loop
  discovery -> candidate -> fixture -> holdout simulation -> promotion
  decision with zero model calls, proving the candidate path is structurally
  reachable before any live shadow cycle. Its promotion decision keeps a
  strict absolute floor (minimum availability and strictly positive
  directional evidence) as the controlled fixture; the production paired
  gate additionally applies tiered admission for new Signals (directional
  ties become provisional residents under the pooled three-zone rule owned
  by `signal_evolution.md`).
- Legacy H/E code remains callable as the read-only contrast path; the
  production switch is a separate gated change that also archives the legacy
  specs per repository removal discipline.
