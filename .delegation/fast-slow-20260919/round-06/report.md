# Round 06 Report

- round_id: fast-slow-20260919/round-06
- status: completed (local verification: 867 tests + lint pass; real Fast+Slow
  joint rerun NOT performed — see outstanding)

## changed files (this round)

- src/stock_opportunity_agent/research/evolution_research_validation.py
  - new shared admission check `_reject_unrepresentable_partial_selections`:
    when a runtime evaluation context supplies the prediction boundary and a
    persisted answer_need/partial selection's residual has no bounded
    representation for its targeted need (e.g. realized facts after the
    cutoff), raise ValidationError naming the selection, residual, and
    boundary. No-op without a runtime context (legacy no-scope unchanged).
  - `_reflection_need_transition_contract`: calls the check at entry (fails
    closed for direct callers too); a partial action now carries only its
    bounded residual — the unsafe literal is never embedded in
    available_answer_actions; the remove_or_genuinely_narrow degradation for
    partial actions is removed (bounded → replace_with_exact_residual_need;
    legacy no-bounded-residual corner → preserve_exactly).
  - `_targeted_answer_need_transition_errors`: an unrepresentable partial
    residual no longer licenses deletion — removal must be restored exactly
    (`restore_exactly`), byte-for-byte retention is compliant; no fabricated
    cutoff.
- src/stock_opportunity_agent/research/evolution_plan_roles.py
  - `LLMResearchController.reflect` runs the admission check at entry, before
    the terminal short-circuit and before any prompt/payload construction:
    the review's repro now raises ValidationError with zero model calls.
- spec/src/stock_opportunity_agent/research/evolution_research_validation.md,
  spec/src/stock_opportunity_agent/research/evolution_plan_roles.md
  (spec-first: replace the round-05 remove-or-narrow degradation rule with
  fail-closed admission + preservation semantics; document the reflect-side
  boundary check)
- tests/test_evolution_reflection_roles.py (+5 tests, all in
  `PartialResidualTemporalScopeTests`)
- reports/fast-slow-joint-correctness-20260919.md (round-06 section),
  progress/status.md, progress/changelog.md, this report

Not touched this round (round-03/05 changes preserved as-is):
evolution_output_validation.{py,md}, tests/test_evolution_output_validation.py,
tests/test_evolution_execution_roles.py, tests/test_evolution_routing_plan_roles.py.

## actual changed behavior

- Review repro (legacy residual "What were the realized revenue results for
  Q1 2026?", cutoff 2025-09-30, adopting output, needs=[], decision=finalize):
  was accepted in 1 reflect call → now raises ValidationError in reflect with
  0 role calls (asserted). Continue-with-unrelated-need variant: same
  rejection (asserted).
- The contradictory prompt can no longer be constructed anywhere: the
  contract builder fails closed on the same condition, and partial actions
  never carry an unrepresentable residual nor a remove-or-narrow instruction.
- Defense in depth: even if an invalid selection reached transition
  validation, deleting the targeted need is an error (restore_exactly);
  retaining it is compliant.
- Preserved unchanged: V117 bounded-residual repair (cutoff restoration,
  one-call acceptance of the exact bounded residual), producer-side select
  guard, all temporal/scoring/promotion/schema semantics, and the round-03/05
  scoped-drift protections (focused file 14/14 still pass, including the
  unrelated scalar-drift counterexample).

## new tests

1. test_unrepresentable_residual_cannot_remove_need_and_finalize — the brief's
   exact production repro via LLMResearchController.reflect; asserts
   ValidationError + 0 model calls.
2. test_unrepresentable_residual_cannot_hide_removal_behind_continue —
   continue decision with an unrelated replacement need; same rejection.
3. test_contract_builder_fails_closed_for_unrepresentable_residual — direct
   builder call raises.
4. test_unrepresentable_residual_requires_exact_restoration_not_deletion —
   transition validation: removal → restore_exactly error; retention → no
   error.
5. test_corrected_routing_selection_flows_into_next_routing_prompt — composed
   production path: real select (raw residual rejected + corrected bounded
   residual accepted, 2 calls) → reflect accepts the exact bounded residual in
   1 call and its contract demanded exactly that string → the subsequent real
   select call's transmitted payload carries the bounded residual as the sole
   `information_needs` entry (not just helper equality).

## commands / exit codes (exact brief commands)

- focused: `PYTHONPATH=src …/python3 -m unittest discover -s tests -p
  test_evolution_output_validation.py -v` → exit 0, Ran 14 tests, OK
- full: `PYTHONPATH=src …/python3 -m unittest discover -s tests -v` → exit 0,
  Ran 867 tests in 39.298s, OK (862 round-05 baseline + 5 new)
- lint: `sh scripts/lint_repo.sh` → exit 0, Lint result: PASS
- `git status --short` → task files as listed above (round-03/05 uncommitted
  changes preserved; round-06 edits layered on top; no commits/pushes this
  round per brief)
- `git diff --check` → empty (no whitespace errors)

## logs

- .delegation/fast-slow-20260919/round-06/focused.log
- .delegation/fast-slow-20260919/round-06/full-tests.log
- .delegation/fast-slow-20260919/round-06/lint.log

## outstanding

- Real Fast+Slow joint run over a V117 successor workspace to verify the
  repaired contract closes under a live model — explicitly not claimed from
  local tests; zero production model calls this round.
- No interface-contract decision needs user arbitration: all changes are
  module-internal guards tightening existing semantics, specs synced first.
