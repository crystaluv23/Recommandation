# Round 10 Report: V118 projected-revalidation feedback stall — diagnosed from real production evidence and fixed

Baseline: 63a2efb (875 tests / lint passed). V118 real joint acceptance FAILED:
77 attempts / $0.25796204, round/cycle 0/0, no Slow, no current executor.
Outcome: root cause diagnosed by deterministic replay of both actual failing
pairs, fix implemented spec-first, 877 tests + lint pass, replay acceptance
verified. No commit (per round brief); real successor run remains Codex's next
step.

## 1. Root cause (exact, per pair)

Both failing H_init pairs share one mechanism in
`_complete_parsed_role` (src/stock_opportunity_agent/research/evolution_output_validation.py,
lenient scoped-projection branch): when the model's correction drifts outside
`must_change_paths`, the runtime builds a safe projection (failed object +
authorized copies only). When that projection **fails revalidation with a new
real failure**, the extension loop cannot add new structured paths, so the code
discarded the projection, kept the original `failed_output` + original
`failure`, and re-sent correction feedback that was **byte-identical to
correction-1** → identical canonical request hash → the exact response cache
replayed the same rejected response → `CandidateExecutionRejected` after the
full budget.

### c01 — Life Time, case5 cik_0001869198:20250331 (attempts 74 → 75)

- Original error (attempt 74, request `03371e1d…`): plain ValidationError —
  `next_information_needs[0]` asks for the runtime-owned evaluation input
  (baseline/doubling definition). Obligation scope: `["next_information_needs[0]"]`.
- Correction (attempt 75, request `fea68b66…`): the model **reordered** the
  flagged need to index 5 instead of removing it → drift at
  `next_information_needs[1..5]`.
- Safe projection: copies corrected `[0]` onto the original — the offending
  baseline question is gone (needs become `[offering, offering, membership,
  centers, capital, catalysts]`, one duplicate).
- Projected revalidation error (new, real, previously **masked** by the
  need-error short-circuit): `claim_quantity_not_supported` on
  `supporting_evidence[0].claim` (dates/prices 02/14/32.34/02/19/33.23 absent
  from same-claim exact_text) and on the shared claim of
  `supporting_evidence[1..3]`, plus `assertion_without_support` on
  `current_beliefs[7]`. The model never edited evidence, so extension copies
  the same invalid claims → no new paths → projection discarded.
- Stall proof (pre-fix replay): correction-2 feedback hash == correction-1
  feedback hash (`eff859a9af510357…`), invalid_output identical → cached
  response replayed → rejected with the generic scope error.

### c02 — Kinross first case (attempts 76 → 77)

- Original error (attempt 76, request `3ef410c5…`): StructuredValidationError
  with 4 typed obligations — 3× `claim_quantity_not_supported`
  (`supporting_evidence[0]/[3]/[7].claim`) + `assertion_without_support`
  (`current_beliefs[0],[1],[4],[6],[7]`); scope = 8 must-change paths +
  permitted dependency `current_beliefs[2]`.
- Correction (attempt 77, request `e7aa7d73…`): the model repaired the 9
  authorized paths but also drifted unrelated content
  (`current_beliefs[3]`, `current_beliefs[5]`, `resolved_questions`) — drift
  detected, projection applied.
- Projected revalidation error (new, real): the model removed "Q2 2025" from
  `supporting_evidence[0].claim` but not from the linked assertion, so the
  projected object fails `assertion_without_support` on `current_beliefs[0]` —
  a path already in scope, hence zero extension paths → projection discarded.
- Stall proof (pre-fix replay): correction-2 feedback hash == correction-1
  (`dbf8515bc651fdc8…`) → cached replay → rejection.

Note: the original temporal-contradiction failure did not recur in V118; the
4 finished cases and the 3 reflect need-change flows are untouched by this fix.

## 2. Fix (spec-first)

Spec: `spec/src/stock_opportunity_agent/research/evolution_output_validation.md`
gained the rule: a projection that fails revalidation must be retained (safe
repairs preserved, unrelated drift discarded) as the next attempt's invalid
output together with its actual new diagnostics; no-projection rejection keeps
the original object/obligations unchanged.

Code: in `_complete_parsed_role`, the lenient projection branch now tracks
`projected_failure`; when the extension loop terminates with a real projected
object and a real revalidation failure, it sets
`failed_output = projected_value`, `failure = projected_failure`, emits
`structured_correction_projection_retained` progress, and continues. The next
correction request therefore has a new feedback hash and typed obligations
targeting the new failure. Strict scope is unchanged: no whole-object
fallback, no blanket belief permission, no inferred parent deletion; the
no-projection path (projection is None) still retains the original feedback
unchanged. New failures keep their structured issue types
(`claim_quantity_not_supported`, `assertion_without_support`, …), so the
follow-up obligations remain machine-readable and actionable.

## 3. Verification

- `round-10/replay.py` (no network; reads only immutable V118 artifacts;
  reconstructs the production initialize parser from the stored request's
  basic_info/evaluation_context/initial_research_skill; `replay.log`):
  - Pre-fix mechanism reproduced for both pairs (identical correction-2
    feedback/invalid_output → cached stall → `CandidateExecutionRejected`).
  - Post-fix, pass A (the **cached identical response**): both pairs now
    succeed through production validation; correction-2 feedback differs
    meaningfully (c01 `eff859a9…` → `c68424ac…`, targeting
    `claim_quantity_not_supported ['supporting_evidence[0].claim']`; c02
    `dbf8515b…` → `b2946e90…`, targeting
    `assertion_without_support ['current_beliefs[0]']`).
  - Post-fix, pass B (scripted meaningful final correction): both pairs pass
    production validation; c01 offending runtime-owned need absent from the
    final state and all five non-offending original needs preserved; c02
    unrelated drifted values (`current_beliefs[3]/[5]`, `resolved_questions`)
    preserved byte-for-byte from the safe projection. (The c02 "offending
    need absent: False" line is a c01-specific check that does not apply —
    c02's needs were never flagged.)
- Focused suite `tests/test_evolution_output_validation.py`: 23 tests OK,
  including two new regressions:
  - `test_projection_revalidation_failure_retains_projected_object_for_next_correction`
    (projection-failed-on-new-issue → next feedback carries the projected
    object with the sibling drift discarded and every otherwise-valid
    scalar/list value retained byte-for-byte, new obligation targets the new
    failure, second correction passes within the same budget);
  - `test_no_projection_scope_rejection_keeps_original_feedback_unchanged`
    (no-projection rejection baseline unchanged: identical feedback retained,
    rejection after budget).
- Full suite: **877 tests OK** (baseline 875 + 2 new), `full-tests.log`.
- `sh scripts/lint_repo.sh`: PASS, `lint.log`. `git diff --check`: clean.

## 4. Files changed (all within the round-10 allowed-writes list)

- `spec/src/stock_opportunity_agent/research/evolution_output_validation.md`
- `src/stock_opportunity_agent/research/evolution_output_validation.py`
- `tests/test_evolution_output_validation.py`
- `progress/status.md`, `progress/changelog.md`
- `.delegation/fast-slow-20260919/round-10/{report.md,replay.py,replay.log,focused.log,full-tests.log,lint.log}`

No changes to scoring/promotion/dataset/limits/record schemas or public
interfaces; V118 workspace untouched. Codex's pre-existing dirty
delegation/report files preserved; no commit made (per round brief — the
successor run needs a committed tree, so Codex should commit these changes as
part of its next step). Outstanding: real V118-successor live run after this
fix is accepted.
