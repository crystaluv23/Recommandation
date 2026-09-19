# Round 23 report

- round_id: fast-slow-20260919/round-23
- status: completed (ready for independent review; not accepted)
- baseline: 068ec23 (922 tests + lint accepted), round-21/22 drafts preserved and refined in place

## What changed

- `src/stock_opportunity_agent/research/evolution_research_validation.py`
  - Deleted `_residual_refs_beyond_symbolic_bound` (the rejected dateless
    year-window inference; both surrogates — `date.min` and parent-year
    inference — falsely rejected valid historical 2024 actuals at prediction
    date 2025-09-30). No date/year/present-day surrogate remains.
  - `_INHERITABLE_EXPECTATION_CONTEXT` now compiles with `re.IGNORECASE`,
    matching the temporal guard's `_FUTURE_EXPECTATION_OR_SCHEDULE` case
    handling (capitalized "Guidance" now lends framing).
  - Round-22's parent guard in `_bounded_residual_need` retained unchanged.
- `src/stock_opportunity_agent/research/evolution_plan_roles.py`
  - `LLMSignalRetrievalAgent` gains the controller-compatible optional
    `set_evaluation_context(prediction_time)` (timezone-aware validation,
    UTC normalization, prediction_time/horizon/horizon_end) and
    `self.evaluation_context`; the routing payload exposes
    `evaluation_context` when present, and the selector system prompt notes
    it is control data with the actual runtime cutoff.
  - The partial-residual producer check was rewritten: with an actual date it
    uses the shared `_bounded_residual_need` for explicit and symbolic
    parents alike — routing rejects exactly when the reflection temporal
    guard finds no bounded restatement (realized future facts, invalid
    parent, unbounded parent), with an actionable correction naming the
    actual prediction boundary, inherited cutoff clause, and framing marker.
    A representable literal is accepted and the consumer normalizes once via
    the same helper (selection intents, need-transition contract), so
    producer and consumer never demand contradictory exact strings. Without
    a date, only the sound dateless explicit-cutoff check remains.
- `src/stock_opportunity_agent/research/evolution_core.py`
  - `_set_evaluation_context(signal_agent, prediction_time)` injected beside
    the controller call (per case, so agent reuse cannot carry an old
    cutoff); helper docstring generalized. Old adapters without the setter
    still work (getattr-optional); no new cross-module import direction.
- Specs updated first: `evolution_plan_roles.md` (actual-date routing
  invariant, per-case reset, no fabricated dates, historical residuals stay
  accepted) and `evolution_research_validation.md` (case-insensitive marker
  vocabulary note).
- `tests/test_evolution_routing_plan_roles.py`: the wrong dateless symbolic
  draft test was replaced by seven real-date tests — payload context +
  representable-residual acceptance + intents/contract/next-routing
  consistency; realized-future correction before signal execution; round-22
  historical 2024 actuals accepted at 2025-09-30; capitalized Guidance
  marker; per-case evaluation-context reset (old cutoff not carried); naive
  prediction_time rejected; unrelated residual still removed by grounding
  with the established context-only fallback contract (the preserved draft
  expected a raise, which contradicts the fallback design — realigned).
  `tests/test_evolution_output_validation.py` is the preserved round-21/22
  draft (SymbolicCutoffResidualInheritanceTests incl. parent-guard
  boundaries) — unchanged this round, all 64 pass.

## Actual commands, counts, exits

- `PYTHONPATH=src .../python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v > .../round-23/focused.log 2>&1` — exit 0, 64 tests OK (before and after source changes).
- `PYTHONPATH=src .../python3 -m unittest discover -s tests -v > .../round-23/full-tests.log 2>&1` — exit 0, 936 tests OK (first run exit 1 with 1 failure: the preserved unrelated-residual draft test expecting a raise; realigned to the fallback contract, then OK).
- `sh scripts/lint_repo.sh > .../round-23/lint.log 2>&1` — exit 0, Lint result: PASS.
- `PYTHONPATH=src .../python3 .delegation/fast-slow-20260919/round-23/replay.py > .../round-23/replay.log 2>&1` — exit 0, REPLAY PASS.
- `git status --short`, `git diff --check` — clean diff check; only task files plus pre-existing delegation logs and launcher-owned state.md modified. No commit per round brief.

## Replay results (original V123 wire, actual date 2025-09-30)

- Wire file `../v123/c01-case1-rejection.json`: 6 entries, attempts 5-10;
  routing attempts 7 (`signal_retrieval_cards`) and 8 (correction) replayed
  with JSON-decoded payloads/responses.
- Attempt 7's original guidance partial residual triggers only the original
  non-temporal correction (selection_reason/residual overlap +
  financing_listing_action:v2 outside the replay registry); attempt 8 is
  accepted. The residual itself is no longer temporally rejected: routing
  payload carries `evaluation_context` and the shared bounded representation
  is "Specific disclosed production, cost, and capital expenditure figures
  for the remainder of 2025 and 2026 are not fully covered, by the
  prediction time, within the parent need's guidance."
- Pre-reflection admission `_reject_unrepresentable_partial_selections`
  passes — exactly where V123 originally failed before any reflection call.
- `_reflection_selection_intents` and `_reflection_need_transition_contract`
  carry that bounded residual as the exact `replace_with_exact_residual_need`
  action for need index 1 (duplicate index 2 stays preserve_exactly), and the
  next routing round over the bounded residual needs has no temporal
  rejection.

## Limitations

- The original raw reflection response never existed (V123 was rejected
  pre-call); everything after routing in the replay is a clearly labeled
  synthetic continuation (synthetic adoptable batch per selected ref), not a
  model replay.
- The replay registry is `configs/signals_v1.json`, which lacks
  `financing_listing_action:v2` present in V123's frozen registry, so that
  wire selection is corrected away in the replay; the guidance-residual flow
  under test is unaffected.
- Local verification only: no production model calls, no commit/push (per
  brief). Independent review pending; main Fast+Slow joint goal incomplete.
