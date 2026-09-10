# V18 actual Fast/Slow and follow-up acceptance

V18 workspace: `runs/cold_start/evolution/information-evolution-mvp-20260911-v18`.
Frozen code `74a7206`, contract
`bee52599f6e8fb9e61a05c0a5c1b3b75a67ac138432288cf9735a1443925d839`.
The ordinary authorized Fast-then-Slow path completed at authoritative pointers
round 1 / cycle 1 with no active cycle. No bootstrap architecture extension was
used. The process exited successfully. Registry version remains 1; no promotion.

Candidate 2 completed all 24 cases, eligible, binary F1 0.7407407407, precision
0.7692307692, recall 0.7142857143. Candidate 1 completed 12 cases but initialization
of case 13 was falsely rejected by the temporal-intent gate. It remains diagnostic
only. This run does not demonstrate a performance improvement over a baseline.

## Confirmed handoffs

- All 36 completed-case Predictor and compact post-hoc contexts match actual
  persisted requests. Request byte counts and body hashes match.
- All 24 original reflections of the committed candidate survive exactly in
  meta-memory, alongside its vertical Plan Critic output. V18 has only one eligible
  Plan, so horizontal reflection was not exercised here; V17 exercised it with
  two complete 24-case Plans and preserved all 48 originals.
- H1 request `960fb51d419036f31bbb8d6d1cad4ece275205f7007f92553cb388d9a727101f`
  and both corrections contain the exact 18,588-character masked meta view.
  H1 discussed prior Plan performance and failed retrieval needs, then returned
  no new testable hypothesis. Input delivery is proven; this does not establish
  that the model used every reflection insight optimally.
- The formal learning ledger has exactly 232 expected events derived from the
  committed Plan: no missing, extra, different, or duplicate events. The incomplete
  candidate contributes none to the committed ledger or meta history.
- Exploration E1 preserved grounded observations for all eight source-ready cases.
  Two invalid observations were explicitly quarantined in the second microbatch;
  valid siblings survived, fixed-group coverage held, and E2 actually ran. E2
  returned no new candidates. This is a substantive no-proposal outcome after
  evidence processing, not the former whole-batch technical failure.
- Update's immutable-description and missing LLM skill defects were caught inside
  bounded correction and repaired in the actual responses. A customer-concentration
  v2 candidate was staged. It was then incorrectly rejected before fixture execution
  because ordinary lowercase `five` matched the upper-case ticker `FIVE` after the
  validator case-folded the entire candidate. Another Update failed the deterministic
  skill-null contract. Neither result is a validated-but-not-promoted candidate.

## General recovery evidence and limits

There were 649 successful model attempts and four failed attempts: two SSL
transport failures and two JSON decode errors. Both transport failures recovered
under the same contract with cached successful requests; both parse failures
recovered through correction. Their paid usage remains in the ledger. Total
recorded model cost is $1.78973032.
Six terminal reflection requests were transmitted (three budget, three round-limit).
Completed cases all finalized; incomplete case sets remain ineligible.

Structured fallbacks record removed paths and source substitutions rather than
inventing evidence. Technical Signal failures are excluded from learning and are
rendered downstream as unknown, not absent conditions. Such guards prevent silent
contamination; correction/fallback frequency still represents research-quality
and latency overhead, and is not claimed to be negligible.

## Repairs after the immutable run

1. Reuse the existing strict identity matchers in candidate validation, preserving
   ticker case instead of rejecting ordinary lowercase words. No issuer-specific
   exception was added. Uppercase ticker matches remain rejected.
2. Recognize conditional future implications (could/might/would) only under the
   existing explicit historical as-of bound; actual future results remain rejected.
   Exact V18 failure replay passes after this grammar-level change.
3. Queryless long JSON previews select a recent dated leaf-record window bounded
   by document availability instead of always exposing the earliest prefix.
   Existing query-driven selection and undated-text fallback remain. Source text
   is not rewritten or summarized. Actual E1 source replay now exposes 2024–2025
   records previously hidden behind 2009–2011 prefixes. A bounded preview remains
   partial evidence and does not establish exhaustive field coverage.

All 649 unit tests and repository lint pass. The targeted verification below
completes the MVP execution and information-flow audit; it does not claim that
this particular search produced a promotable Signal.


## Targeted acceptance after the repairs

Frozen code `fed00ec`; isolated workspace
`runs/cold_start/evolution/information-evolution-mvp-20260911-v19-validation-b`;
contract `048e91262418fe33fcff026236e51c951d3dfaa1b22da04ab3e3253119462268`.
This is a bounded diagnostic validation, not another completed evolution cycle.
Its six real calls all succeeded, costing $0.006265; request bytes and hashes
match, and repeat fixture reporting used cache without new paid calls.

- The unchanged V18 customer-concentration candidate now passes the identity gate
  and executes all four fixtures through the real Signal executor and DeepSeek.
  Three meet their expected states; fixture 3 returns neutral instead of the
  candidate's expected negative. It is therefore rejected on actual behavior.
  The validator's `executed_tests=3` counts successful fixtures, while the request
  ledger confirms all four were executed. No thresholds or expected states were
  changed to make it pass; no paired holdout or promotion was warranted.
- The same eight E1 cases and document hashes were re-extracted with repaired
  previews. Both real microbatches succeeded, yielding 22 validated observations
  with empty quarantine metadata. This establishes that the corrected source
  windows actually reach the model, beyond local text-selection tests.
- A next-Fast proposer request preview contains the exact masked committed meta
  view. Registry freeze at learning cutoff 1 includes all 232 events and changes
  the learning hash versus cutoff 0 while preserving the definition hash. The
  preview was not transmitted and is not represented as a second Fast round.
- V17's interrupted learning publication was replayed in an isolated Registry
  copy: 200 missing events were appended, all 529 originals match, seven disputed
  observations are excluded from effectiveness counts, and a second reconciliation
  appends zero events. V17 itself remains immutable at round 1 / cycle 0.
- The final V18 invariant audit covers all 36 trajectories and 1,926 resolved
  document references with no detected future-document leakage, repeated Signal
  execution within a case, or forbidden outcome/reflection fields in Predictor
  input. Both V18 and diagnostic wire audits pass.

Artifacts in the diagnostic workspace: `targeted_validation.json`,
`targeted_e1_replay.json`, `next_fast_input_audit.json`, `attempts.json`, and
`requests/`. V18's canonical meta, Plan records, learning ledger and staged Slow
validation remain the authoritative original-cycle evidence.

No Signal was promoted in this run. The promotion/next-version state machine is
covered by the repository tests; a changed production Registry was not observed
live here. The actual candidate failed a legitimate fixture after its false
identity rejection was repaired. This is a valid rejection outcome, not evidence
of a predictive improvement or a successfully promoted new Signal.
