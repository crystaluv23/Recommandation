# Round 07 report: eliminate list-shaped scope escape

Status: COMPLETE (all local verification green). No production model calls, no
commit/push (explicitly prohibited by this round's brief).

## Confirmed input

- round-06/additional-review.md counterexample, verified by reading the code
  path: with `exact_compaction_scope=True`, `enforce_scoped_correction=True`,
  `stable_correction_prefix=True`, a correction for invalid
  `{"fix":0,"keep":["original"]}` returning `{"fix":1,"keep":["drift","extra"]}`
  was accepted wholesale. Parser contract: `StructuredValidationError`
  paths=("fix",) when fix==0, plain `ValidationError` when
  keep==["original"], else valid.
- Root cause: `_lenient_list_membership_edits_only` stood the model's complete
  corrected object in for the projection whenever every drift surfaced as a
  bare list root — pure type-based authorization. Same-length list rewrites
  surface the same bare root in `_scoped_correction_drift_paths` when no
  allowed path reaches the collection, so the helper's "length-changing"
  docstring claim was unsupported. `projected_failure` was initialized but
  never assigned.

## Changes (spec first)

1. `spec/src/stock_opportunity_agent/research/evolution_output_validation.md`:
   the complete corrected object never stands in for the projection; any
   remaining drift (scalar, nested-leaf, indexed-item, list membership
   including same-length rewrites) fails closed; legitimate list corrections
   must be authorized by structured issue/compaction/dependency paths; indexed
   obligation paths authorize membership edits only within their named slots
   (unauthorized members survive byte-for-byte in order, additions bounded by
   prior size plus authorized slots), with drift detection and projection
   enforcing the same rule.
2. `src/.../evolution_output_validation.py`:
   - deleted `_lenient_list_membership_edits_only` and its full-object
     acceptance block; removed the dead `projected_failure` variable;
   - added `_authorized_membership_edit` (slot authorization + member
     survival + bounded additions) used by both
     `_scoped_correction_drift_paths` (uncovered bare-root drift and the
     length-change branch, whose insertion cap changed from
     len(protected)+slots to len(old)+slots) and `_project_scoped_correction`
     (a final indexed path over a length-changed list now projects the
     authorized membership edit instead of returning None); projection also
     skips indexed child paths subsumed by a wholesale bare-root copy.
3. `src/.../evolution_research_validation.py` (validators responsible for the
   legitimate cross-field repairs that previously rode the escape — precise
   dependencies encoded, no test weakened to keep green):
   - initialize visible-answer issue is now structured
     (`visible_answer_need_retained`) with paths on the diagnosed need and
     `dependent_paths=('current_beliefs',)`; `_raw_initialize_need_issues` /
     `_raw_research_state_compaction_issues` return `str | ValidationIssue`
     and `_normalize_research_state_output` splits structured from prose
     (message texts preserved byte-for-byte);
   - `research_need_transition_invalid` issues declare
     `dependent_paths=('current_beliefs',)` for adopted-answer belief
     aggregation;
   - stale-resolved-need retention became structured
     (`stale_resolved_need_retained`) with exact
     `next_information_needs[i]` paths derived from the new-resolved-question
     ↔ retained-need phrase match;
   - open-question-duplicates-need became structured
     (`open_question_duplicates_need`) with exact `open_questions[i]` paths
     (this was the prose error collapsing v73's mixed failure and stripping
     the structured dependent paths).
4. `tests/test_evolution_output_validation.py`:
   - added `test_lenient_projection_fails_closed_on_list_membership_drift`
     (length-changing: exact confirmed counterexample) and
     `test_lenient_projection_fails_closed_on_same_length_list_drift`
     (same-length unauthorized rewrite), both asserting
     `CandidateExecutionRejected`; the scalar counterexample test is retained
     unchanged;
   - `test_exact_compaction_scope_still_rejects_drift_beside_indexed_removal`
     renamed to
     `test_exact_compaction_scope_projects_removal_discarding_beside_drift`:
     projection can now express the authorized indexed removal precisely, so
     the test asserts the stronger outcome — removal applied, unrelated need
     preserved byte-for-byte, drift discarded (the brief's sanctioned
     "projects preserving unrelated list" success mode). All existing
     legitimate compaction/member-removal/dependency tests retained.
5. Progress/audit: `progress/status.md`, `progress/changelog.md`, and a
   Round 07 section in `reports/fast-slow-joint-correctness-20260919.md`.

## Counterexample outcome

The exact confirmed counterexample now fails closed
(`CandidateExecutionRejected`: correction changed unrelated valid content
outside must_change_paths=['fix']) because `keep` has no authorized obligation
path — list type, length, or passing validation alone grants no scope. The
original scalar counterexample stays protected by the same mechanism.

## Commands, exit codes, logs

- `PYTHONPATH=src .../python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v`
  → exit 0, 16 tests OK → `.delegation/fast-slow-20260919/round-07/focused.log`
- `PYTHONPATH=src .../python3 -m unittest discover -s tests -v`
  → exit 0, 869 tests OK → `round-07/full-tests.log`
- `sh scripts/lint_repo.sh` → exit 0, `Lint result: PASS` → `round-07/lint.log`
- `git status --short` → only this task's files plus pre-existing uncommitted
  round-03..06 changes and delegation artifacts (nothing else touched);
  `git diff --check` → clean.

Interim full-suite runs during development (8 errors → 3 → 1 syntax-import
failure → 0) are described in the audit report; the final logs above are the
authoritative ones.

## Local verification vs real joint acceptance

All results above are LOCAL ONLY: scripted role callers, no production model
calls, no runtime workspaces touched, and no git commit (this round's brief
explicitly forbids commits/pushes, overriding the usual session checkpoint
discipline). Real Fast+Slow joint acceptance over a V117 successor workspace
remains outstanding and is unchanged by this round's claims.

## Files written this round

- src/stock_opportunity_agent/research/evolution_output_validation.py
- src/stock_opportunity_agent/research/evolution_research_validation.py
- spec/src/stock_opportunity_agent/research/evolution_output_validation.md
- tests/test_evolution_output_validation.py
- progress/status.md, progress/changelog.md
- reports/fast-slow-joint-correctness-20260919.md
- .delegation/fast-slow-20260919/round-07/{report.md,focused.log,full-tests.log,lint.log}
