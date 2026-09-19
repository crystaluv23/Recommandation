> 2026-09-20 final local acceptance: round09 passed875fulltests and lint; independent production-path scope replays passed. Original V117 contradiction corrected at producer and consumers, not merely sibling preservation. Code is ready for a fresh real joint run. No real successor completion is claimed by the local results below; later sections preserve the intermediate investigation/repair history.

# Fast+Slow joint correctness: corrected root-cause account for the V117 contradictory residual contract (2026-09-19, round 05)

This report corrects the initial audit/root-cause account recorded for the V117
Fast-loop death. The initial account treated the failure as a scoped-sibling
preservation problem in H_reflect correction. The raw immutable evidence shows
the deeper contradiction came first, upstream: routing itself produced and
authorized an exact partial residual that violates the prediction-time
boundary, and every downstream consumer then demanded that unsafe literal.

## Raw evidence (immutable artifacts, not modified this round)

- `.delegation/fast-slow-20260919/v117-required-residual.json` — the actual
  correction obligation sent in V117 request 12. It names
  `next_information_needs[0]` in `must_change_paths`,
  `required_action="replace_with_exact_residual"`, and
  `required_need = "Cost per ounce guidance for the remainder of 2025 and 2026 is not covered by this card."`
  This literal contains the post-cutoff scope "2026" with no as-of clause.
  Under `_future_source_date_refs` it is a fact request ("guidance") with a
  future source date ref ("2026") and no bounded-as-of exemption, so the
  temporal guard `future_information_unavailable` must reject exactly the
  string the transition guard demanded.
- `.delegation/fast-slow-20260919/v117-projection-replay.json` — helper replay
  over the real request: `authorized_paths` includes `next_information_needs[0]`,
  `corrected_need_preserved=false`, finding "Scope protection alone cannot
  repair V117; contradictory temporal and residual contracts."
- Prior need (V117 c01): "What forward guidance or production outlook had
  Kinross Gold disclosed by 2025-09-30 regarding gold equivalent production and
  cost per ounce for the remainder of 2025 and 2026?" — bounded by the explicit
  clause "by 2025-09-30". The earlier corrected output 11 ("What cost per ounce
  guidance had Kinross Gold disclosed by 2025-09-30 for the remainder of
  2025?") was a bounded, genuinely narrower residual and was rejected only for
  not matching the unsafe literal.
- Byte hashes of the raw request artifacts could not be recomputed inside this
  round's permitted command allowlist; the artifacts above are untouched and
  remain the verbatim evidence (hashing is left as a mechanical follow-up).

## Corrected code-level root cause

1. Producer (routing, `LLMSignalRetrievalAgent.select` in
   `evolution_plan_roles.py`): the partial-`residual_need` checks verified
   grounding and non-cosmetic narrowing but never required the residual to
   retain the targeted need's as-of cutoff. V117's residual dropped
   "disclosed by 2025-09-30" while keeping "2026", so routing persisted a
   temporally unbounded `SignalSelectionDecision`. The raw residual came from
   this routing decision, not from Signal execution.
2. Consumers (`evolution_research_validation.py`):
   `_reflection_need_transition_contract` and
   `_reflection_selection_intents` replayed the raw residual into the H_reflect
   prompt, and `_targeted_answer_need_transition_errors` required that exact
   literal in `next_information_needs`. Any bounded narrowing (output 11)
   failed the transition guard; the demanded literal itself failed the
   temporal guard. The instructions were contradictory, not merely strict.
3. `_restore_inherited_need_cutoffs` restored the full parent need when a
   literal residual dropped its cutoff, which re-retains the already answered
   facets and lands on the "remained byte-for-byte" transition error — the
   oscillation loop the model was trapped in (round-03's scope fixes could not
   break it because the reverted field was itself authorized).

## Fixes (smallest generic change at the producer boundary + consistent consumers)

- New shared rule `_bounded_residual_need(residual, prior_need,
  prediction_date)` in `evolution_research_validation.py`: a residual that
  already respects the boundary is returned unchanged; a residual that dropped
  the parent's cutoff is returned with the inherited as-of clause restored
  (parent clause verbatim, literal quantities preserved); a residual that
  cannot be made bounded returns None and downstream degrades to
  remove-or-genuinely-narrow instead of demanding an unavailable literal.
- Producer: `select` validation now rejects a partial residual whose calendar
  scope exceeds the targeted need's earliest explicit as-of bound
  (`_need_as_of_bound_clause` + `_future_source_date_refs` anchored at the
  parent's own bound, so no prediction-time input is needed at routing time).
  Producer-accepted residuals are therefore always acceptable to the
  prediction-time-anchored consumer guard.
- Consumers: the transition contract, executed-selection intents, and the
  transition validator all derive the required exact residual through the same
  shared rule; `_validate_research_state_refs` now threads `evaluation_context`.
  `_restore_inherited_need_cutoffs` restores the cutoff clause onto the
  residual (bounded, genuinely narrower) instead of re-retaining the answered
  parent, keeping the old whole-need restore only as the fail-safe when no
  bounded restatement exists.
- Round-03 whole-object fallback (`evolution_output_validation.py`): the
  "revalidate the model's complete object" escape is removed. In compaction
  lenient mode the projected copy is extended only with paths named by
  structured revalidation issues raised against the projected object itself;
  the complete object may stand in only when every remaining drift is a
  length-changing membership edit of a list collection under full
  revalidation; scalar, nested-leaf, and indexed-item drift fails closed with
  actionable feedback. This keeps legitimate dependency/shape/list repairs
  (v11/v22/v23/v70/v73/v74/v79 flows) working while the review's
  unrelated-drift counterexample is rejected.

## Verification (this round, no production model calls)

- Regression mirroring the real contradiction through production
  role/validator paths (`tests/test_evolution_reflection_roles.py`,
  `PartialResidualTemporalScopeTests`): original bounded need → persisted
  routing residual that lost the cutoff → contract/intents carry the
  cutoff-restored bounded residual → H_reflect writing that exact string is
  accepted by both the transition and temporal guards in one call; writing the
  raw unbounded residual is corrected, not oscillated.
- Producer regression (`tests/test_evolution_routing_plan_roles.py`): the
  cutoff-dropping residual is rejected at selection time with the clause named
  in feedback, the corrected bounded residual passes, and the accepted
  bounded residual is consumable as the next routing target without false
  positives.
- Unrelated-drift counterexample and prose-only fail-closed
  (`tests/test_evolution_output_validation.py`): the drifted sibling is
  preserved through structured-issue extension; scalar drift with no
  structured justification fails closed.
- Full suite: 862 tests OK; focused file: 14 tests OK; `scripts/lint_repo.sh`
  PASS. Logs: `.delegation/fast-slow-20260919/round-05/{focused,full-tests,lint}.log`.

## Scope boundary

All verification is local (ScriptedRoleCaller replays through the real
`_complete_parsed_role`/controller/routing paths). The real Fast+Slow dual
loop has NOT been re-run against a live model this round; live acceptance of
the repaired contract is outstanding.

---

# Round 06: unrepresentable partial residuals fail closed (2026-09-19)

Round-05 passed its 862-test suite and lint but independent review
(`round-05/review.md`) rejected one semantic hole: when
`_bounded_residual_need` returns None for a legacy partial residual — e.g.
"What were the realized revenue results for Q1 2026?" under a 2025-09-30
cutoff, where restoring any cutoff still leaves realized post-cutoff facts —
the need-transition contract degraded the obligation to
remove_or_genuinely_narrow while `available_answer_actions` still exposed the
unsafe literal, and `_targeted_answer_need_transition_errors` silently
accepted deletion of the targeted need. One production reflect call could
therefore remove unresolved demand and finalize (or hide the removal behind an
unrelated continue need).

## Fixes (fail-closed admission, no research-semantics change)

- New shared admission check `_reject_unrepresentable_partial_selections`
  (`evolution_research_validation.py`): when a runtime evaluation context
  supplies the prediction boundary and a persisted answer_need/partial
  selection's residual has no bounded representation for its targeted need,
  reflection rejects the routing state with a ValidationError before any
  prompt is constructed — zero model calls. Without a runtime context there
  is no boundary to enforce, so legacy no-scope behavior is unchanged.
  `LLMResearchController.reflect` calls it at entry, and the contract builder
  calls it directly so no caller can obtain a contradictory contract.
- The contract builder no longer embeds the unsafe literal residual in
  `available_answer_actions` and no longer emits a remove_or_genuinely_narrow
  degradation for partial actions: a partial action carries its exact bounded
  residual (replace_with_exact_residual_need) or, in the legacy multi-target
  corner, preserves the need exactly.
- `_targeted_answer_need_transition_errors` treats an unrepresentable partial
  selection as void for deletion purposes: removing the targeted need must be
  restored exactly; byte-for-byte retention is compliant. No cutoff is
  fabricated for realized future facts.
- V117 bounded-residual behavior (cutoff restoration,
  replace_with_exact_residual, one-call acceptance) and the round-03/05
  scoped-drift guards are unchanged; the producer-side select guard from
  round 05 still rejects new cutoff-dropping residuals upstream.

## Verification (local, no production model calls)

- The review's exact counterexample (finalize with emptied
  next_information_needs) and the continue-with-unrelated-need variant both
  now raise ValidationError in `reflect` with zero role calls
  (`tests/test_evolution_reflection_roles.py`,
  `PartialResidualTemporalScopeTests`).
- Composed production-path regression: real `select` (raw residual rejected
  and corrected) → `reflect` accepts the exact bounded residual in one call
  and its contract demanded exactly that string → the next `select` call's
  transmitted payload carries the bounded residual as the sole
  information need. This pins the routing → reflection → routing flow the
  original test plan asked for, not just helper equality.
- Defense-in-depth units: the contract builder fails closed directly, and
  transition validation demands restore_exactly on removal while accepting
  byte-for-byte retention.
- Full suite: 867 tests OK (862 + 5 new); focused file: 14 tests OK;
  `scripts/lint_repo.sh` PASS. Logs:
  `.delegation/fast-slow-20260919/round-06/{focused,full-tests,lint}.log`.

## Remaining

The real Fast+Slow joint run over a V117 successor workspace is still the
outstanding acceptance step; nothing in this round claims runtime success from
local tests.

## Round 07 (2026-09-20): list-shaped scope escape eliminated

Round-06's additional independent review found a second, independent escape in
the round-05 fallback: with `exact_compaction_scope=True` and an ordinary
structured issue authorizing only `fix`, a correction that also rewrote the
unrelated list `keep` from `["original"]` to `["drift","extra"]` was accepted
wholesale, because `_lenient_list_membership_edits_only` stood the model's
complete object in for the projection whenever every drift surfaced as a bare
list root. The helper's "length-changing" docstring claim was unsupported: with
no authorized path reaching a collection, a same-length membership rewrite
surfaces the same bare root.

Changes (spec updated first in
`spec/src/stock_opportunity_agent/research/evolution_output_validation.md`):

- Removed `_lenient_list_membership_edits_only` and its full-object acceptance
  block; removed the dead `projected_failure` variable. The model's complete
  corrected object never stands in for the projection.
- `_authorized_membership_edit` now defines the only list-membership leniency:
  an obligation path must authorize indexed slots of that collection; members
  outside authorized slots must survive byte-for-byte in order; additions are
  bounded by prior collection size plus authorized slot count. Drift detection
  (`_scoped_correction_drift_paths`) and projection
  (`_project_scoped_correction`) enforce the identical rule, so a drift that is
  excused is exactly a drift projection can apply; projection additionally
  skips indexed child paths subsumed by a wholesale bare-root copy.
- Legitimate cross-field list repairs that previously rode the escape are now
  validator-issued structured dependencies: the initialize visible-answer issue
  carries `dependent_paths=('current_beliefs',)` (aggregating a visible answer
  into beliefs is part of that repair); `research_need_transition_invalid`
  declares the same belief dependency for adopted-answer transitions; the
  stale-resolved-need retention check and the open-question-duplicates-need
  check were converted from prose to structured issues with exact
  `next_information_needs[i]` / `open_questions[i]` paths, so their repairs no
  longer depend on prose scope inference.
- Tests: two new counterexample regressions
  (`test_lenient_projection_fails_closed_on_list_membership_drift`,
  `test_lenient_projection_fails_closed_on_same_length_list_drift`) mirror the
  confirmed production counterexample beside the existing scalar one;
  `test_exact_compaction_scope_still_rejects_drift_beside_indexed_removal`
  became `test_exact_compaction_scope_projects_removal_discarding_beside_drift`
  because projection can now express the authorized removal precisely — it
  asserts the unrelated need survives byte-for-byte instead of asserting
  rejection. All legitimate compaction/member-removal/dependency tests are
  retained unchanged.

Verification (local only, no production model calls, no commit per round
brief): 869 tests OK, focused file 16 OK, `scripts/lint_repo.sh` PASS,
`git diff --check` clean. Logs:
`.delegation/fast-slow-20260919/round-07/{focused,full-tests,lint}.log`.
The real Fast+Slow joint rerun remains outstanding.

## Round 08 (2026-09-20): field/member granularity preserved at every
path-expansion step

Round-07's independent acceptance rejected two confirmed scope escapes that
were one mechanism bug, not two string bugs:

- Counterexample A: an issue authorizing only the leaf `rows[0].fix` let a
  correction rewrite the sibling `keep` field and insert an unrelated record,
  because the changed-length membership branch counted leaf paths as
  authorized member slots (round-07 had widened the cardinality bound from
  `len(protected)+slots` to `len(old)+slots`).
- Counterexample B: after projecting an authorized `fix` repair, a discovered
  `research_state_item_over_limit` issue with paths `("rows",)` and
  repair_context `{minimum_removed_items: 1, must_reduce_any_of_paths:
  ["rows"], required_compaction_remove_paths: ["rows[1]"]}` had its container
  root flattened into wholesale copy authority, accepting a `rows[0]` drift
  the metadata explicitly scoped to removing `rows[1]`.
- Plus an unjustified blanket authority: round-07 had added unconditional
  `dependent_paths=("current_beliefs",)` to every visible-answer and
  need-transition issue, licensing rewrites of all valid beliefs during any
  need correction.

Changes (specs updated first in all three owning module files):

- Member granularity is now structural in
  `evolution_output_validation.py`: only exact member paths `root[i]` grant
  whole-member replace/split authority; leaf paths `root[i].field` never
  rewrite siblings or insert records; a member named by an obligation path
  (exact or leaf) may be removed — mirroring the correction contract's
  "change to valid content or be removed when the contract permits omission"
  (this is what keeps the h1 ledger repair, which deletes an unfixable
  disposition row under a leaf obligation, legitimate) — while unmentioned
  members must survive in order, unchanged except for their own authorized
  leaf edits (new recursive `_authorized_equivalent`, used identically by
  drift detection and the projection membership guard).
- Insertions are authorized only explicitly: an obligation whose
  allowed_repairs contains `add` grants a bounded append budget on the
  collection its paths name (one new member per named missing-quantity
  literal, at least one). The v11 same-claim evidence append remains
  legitimate through this budget; appending beyond it fails closed.
- `_structured_revalidation_paths` now returns copy paths and exact removal
  paths: a discovered compaction issue contributes only its
  `required_compaction_remove_paths` (validated against the projected
  object) and never its container root; without removal metadata it
  contributes nothing. `_project_scoped_correction` applies deterministic
  whole-member removals after copies. `_authorized_correction_paths` no
  longer adds a compaction issue's container-root path once exact removal
  paths enumerate that root, closing the same hole in first-error compaction
  mode.
- Removed both unconditional `current_beliefs` dependent_paths in
  `evolution_research_validation.py`; belief edits during a need correction
  must now be justified by an actual linked-assertion dependency (exact
  same-claim text, which the claim issues already emit) or an actual
  compaction obligation. Added production-role negative coverage
  (`NeedCorrectionBeliefScopeTests`): a valid unrelated belief survives a
  need-transition correction byte-for-byte while the model's belief rewrite
  is projected away.
- Dead code removed: the `_authorized_membership_edit` call inside drift
  `visit`'s `if not paths` branch was unreachable (any allowed path under the
  root would have made `relevant()` non-empty), and the
  `preserve_descendant_list_shape` flag became redundant once exact-member
  matching is the only rule (the plan proposer now uses the shared strict
  behavior unchanged).

Tests: counterexample A (insertion and removal variants, production reflect
flags), counterexample B (exact-removal extension preserving `rows[0]`
byte-for-byte in two calls), bounded-append positive and negative cases, and
the belief-preservation negative coverage. All v6/v11/v15/v62/v70/v74/v77/
v79/v102–v107 live-shape fixtures, the compaction/dependency/lenient chains,
and the round-06 routing→reflect→routing chain pass unchanged.

Verification (local only, no production model calls, no commit per round
brief): 873 tests OK (869 + 4 new), focused file 19 OK,
`scripts/lint_repo.sh` PASS, `git diff --check` clean. Logs:
`.delegation/fast-slow-20260919/round-08/{focused,full-tests,lint}.log`.
Local readiness is not live acceptance: the real Fast+Slow joint rerun over
a V117 successor workspace remains outstanding.

## Round 09 (2026-09-20): explicit member-deletion authority, no generic leaf escalation

Independent production replay after round-08 proved the `removal_allowances`
builder unconditionally authorized parent-row deletion for any indexed leaf
obligation: with `invalid={rows:[{fix:0,keep:"original"},{fix:2,keep:"protected"}]}`
and a correction that purely deletes `rows[0]`, a parser rejecting only
`rows[0].fix` (allowed_repairs `("replace",)`) let the whole object stand under
the production reflect flags (`exact_compaction_scope=True,
enforce_scoped_correction=True, stable_correction_prefix=True`). Round-08's
"member named by an obligation path — by an exact member path or a leaf beneath
it — may be removed" rule replaced one permission escalation with another.

Fix (deleting the generic inference, not layering exceptions):

- Whole-member deletion authority now comes only from specific validator
  metadata: the owning issue's `authorized_member_removals` repair context
  naming exact member paths, or an obligation that itself names the whole
  member `root[i]` while its allowed_repairs permit `remove`. An indexed leaf
  path, a leaf `remove` repair, and whole-object validity never authorize
  parent removal.
- The legitimate H1 history-only unknown-alias ledger-row deletion is now
  explicitly issued by its owning `h1_unknown_need_refs` validator
  (`evolution_signal_roles.py`): the leaf diagnostics are unchanged
  (`required_change_paths ["need_dispositions[0].need_refs","no_hypothesis"]`
  asserted unchanged) and the issue additionally carries
  `allowed_repairs=("replace","remove")` plus
  `authorized_member_removals=["need_dispositions[<i>]"]` for exactly the
  diagnosed row. Authorization is limited to rows whose refs are invalid under
  the actual runtime need set; the corrected object still passes the complete
  H1 parser. No H1-global or all-leaf-path exemption exists.
- `_authorized_equivalent` now permits an exactly authorized path's complete
  subtree before recursing. Previously an authorized same-length list-valued
  leaf (`root[i].tags`) was rejected during a neighboring authorized row
  removal because same-shape lists recursed into the unlisted `tags[0]`.

Test evidence (negative parsers reject only the invalid fix, so rejection and
drift-discard provably depend on the scope guard, not on a parser mirroring
scope preservation):

- Pure removal and replacement+addition with only leaf replace authorized are
  rejected by the guard alone after two calls (the replay counterexample is now
  the pure-removal regression); the same-length sibling mutation is discarded
  by projection with the sibling preserved byte-for-byte; insertion stays
  rejected.
- Explicit whole-member `remove` obligations and `authorized_member_removals`
  metadata positives pass; the composed positive (authorized `rows[0].tags`
  same-length replacement, explicit `rows[1]` removal, `rows[0].keep`
  preserved) passes.
- Round-08 gains retained: leaf-expansion rejection, compaction extension via
  exact removals only, no blanket `current_beliefs` permission, bounded
  explicit append, the round-06 routing chain, and all historical fixtures.

Spec-first updates: `evolution_signal_roles.md` (H1 need-ledger aggregation
invariant now records the explicit member-removal metadata) and
`evolution_output_validation.md` (member-deletion authority and the
exact-path comparator rule). H1 diagnostics are byte-identical.

Verification (local only, no production model calls, no commit per round
brief): 875 tests OK (873 + 2 new), focused file 21 OK,
`scripts/lint_repo.sh` PASS, `git diff --check` clean. Logs:
`.delegation/fast-slow-20260919/round-09/{focused,full-tests,lint}.log`.
The real Fast+Slow joint rerun remains outstanding.

## V118 real acceptance and round10 repair
V118 (checkpoint63a2efb) actually executed:77attempts/$0.25796204, rejected both Fast candidates, round/cycle0/0, no Slow. Original temporal contradiction did not recur in observed cases. Three changed reflection needs were carried exactly into subsequent routing payloads; this proves state continuity, not yet downstream action on those changed indices. Actual wire evidence: `.delegation/fast-slow-20260919/v118-changed-flows.json`.

Failures74/75 and76/77 exposed safe projection feedback stall: projected objects surfaced real new validation errors, but code discarded them and repeated original correction context, replaying identical cache requests. Round10 retains last safely projected invalid object and its actual diagnostics; unrelated drift remains discarded.877tests/lint passed; Codex reran actual-wire replay independently and confirmed feedback changed, both scripted repairs validated and unrelated values preserved. See round-10/report.md, review.md and independent-replay.log.

Independent semantic review also found original V118 issuer-guidance question merely used supplied baseline, while guard proximity regex classified any price/baseline mention as retrieval. Round11 addresses this separately before next real run. No joint success claimed.

## Runtime-input reference versus retrieval repair (rounds11–13)
V118 original issuer-guidance question used supplied baseline; old proximity-only guard falsely demanded rewriting it. Round11 left-governor classifier was rejected for default-permission on unknown wording. Round12 conservative reference-only exceptions fixed those examples (886tests), but Codex found bare-with and repeated-anchor holes. Round13 removes bare-with exemption and enumerates all nominated occurrences, including repeated same-anchor mentions;888tests/lint and actual V118 replay passed. Codex independently checked both demonstrated failures, inverse clause order, legitimate compared-with and literal V118 question. Executor report's inherited `Retrieve the share price from the supplied baseline` bypass claim was independently disproved on final code (returns True/reject).

Accepted locally; code does not purport to solve universal English intent. Unrecognized reference forms conservatively require correction. Actual joint successor still required, preserving failed V117/V118 and cumulative budgets.
