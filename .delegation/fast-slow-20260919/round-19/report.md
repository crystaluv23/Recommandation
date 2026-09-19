# Round 19 report — consistent feedback and recovery for V121 failures

- round_id: round-19 (fast-slow-20260919)
- status: completed locally; NOT independently accepted; no commit (per brief)
- baseline: cdf644e (910 tests / lint accepted)

## What was diagnosed and repaired (spec-first; both owning specs updated)

A. Bumble reflect (raw 102/103) — occurrence-aware restoration authority.
  - `_targeted_answer_need_transition_errors` restore/replace obligations now
    carry `required_need_occurrences` (from the same per-obligation occurrence
    arithmetic that validates preservation); `_need_transition_validation_issue`
    passes it into the repair context/obligations.
  - `_research_need_transition_fallback` restores by issued count (appends
    the exact required text until multiplicity is met; never removes,
    deduplicates, or reorders returned rows). `replace_with_exact_residual`
    rewrites only at the returned coordinate the issue names; when the
    targeted occurrence is absent it appends the exact residual and never
    consumes a preserved duplicate of the prior text.
  - `_project_scoped_correction` performs no coordinate write for a
    `restore_exactly` whole-member path: the prior-state coordinate is not a
    returned write target, so no unrelated valid row is replaced and an
    out-of-range prior index no longer fails the whole projection;
    restoration stays with the gated membership machinery and the
    deterministic fallback.

B. Kinross initialize (raw 104–106) — aggregated initial feedback.
  - `_normalize_research_state_output` raises the future-information
    rejection together with the Basic quantity, quantitative assertion-link,
    and Basic literal-identity issues whenever the evidence shape makes them
    decidable (temporal issues first; ordering/contracts preserved; no
    future fact accepted, no grounding relaxed; temporal-only fallback for
    undecidable shapes).

C. Correction-drift pairing.
  - At budget exhaustion a scope-rejection no longer overwrites a
    StructuredValidationError with the generic drift message: the exact
    failed-object/semantic-failure pair is preserved, the drift diagnostic is
    retained separately and reported alongside the semantic failure; the raw
    model response never becomes the accepted baseline. Round-10
    projected-progress retention is untouched (covered by existing tests).

## Results

- focused: 52/52 pass (`round-19/focused.log`), including 7 new regressions
  (duplicate multiplicity restoration, drifted partial correction recovery
  without row replacement, semantic+drift paired rejection, missing-residual
  append, aggregated temporal+quantity feedback, compliant all-in-budget
  correction, empty-evidence removal still rejected).
- full: 917 tests OK (`round-19/full-tests.log`; 910 baseline + 7 new; two
  exact-dict assertions in test_evolution_reflection_roles.py updated for the
  new `required_need_occurrences` field, one pre-existing fallback unit
  fixture now states the returned coordinate the production validator
  actually issues).
- lint: PASS (`round-19/lint.log`).
- replay: exit 0 (`round-19/replay.log`), actual wire from
  v121/rejections-wire.json:
  - Bumble: raw 102 has exactly 2 transition errors (duplicate count 1 vs
    required 2; need5 0 vs 1); correction 103 alone stays invalid; the final
    state restores guidance×2 and Blackstone×1, preserves every prior need's
    multiplicity, and independently validates with 0 transition errors;
    initial feedback carries both restore_exactly obligations with
    occurrence counts.
  - Kinross (full original basic_info): raw 104's first feedback aggregates
    future_information_unavailable + every decidable claim-group quantity
    issue; attempt 105's output exposes all its quantity groups in one
    feedback; a compliant fixture corrects everything within the correction
    budget (2 llm calls); raw 106 is honestly classified still-invalid
    (empty/unsupported-evidence removal stays rejected).

## Commands (exact permitted forms)

- PYTHONPATH=src .../python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v > .delegation/fast-slow-20260919/round-19/focused.log 2>&1
- PYTHONPATH=src .../python3 -m unittest discover -s tests -v > .delegation/fast-slow-20260919/round-19/full-tests.log 2>&1
- sh scripts/lint_repo.sh > .delegation/fast-slow-20260919/round-19/lint.log 2>&1
- PYTHONPATH=src .../python3 .delegation/fast-slow-20260919/round-19/replay.py > .delegation/fast-slow-20260919/round-19/replay.log 2>&1
- git status --short / git diff --check (clean of whitespace issues; only task files modified)

## Limitations

- No production/paid calls, no commit, no frozen-run edits (per brief).
- The Bumble signal batch is reconstructed from the persisted H_reflect model
  view, not the canonical SignalBatchResult (round-17 limitation); only
  price_momentum_126d is adopted and its canonical interpretation is carried
  in the view, so the adopted-claim checks use the same literals.
- Kinross raw 104's eight production quantity obligations collapse into 2
  claim groups on the raw output (identical claims grouped); the replay
  verifies every decidable group surfaces in one feedback, and attempt 105's
  output (4 groups) does the same.
- Main goal still requires a real Fast+Slow successor run after independent
  acceptance of this round.
