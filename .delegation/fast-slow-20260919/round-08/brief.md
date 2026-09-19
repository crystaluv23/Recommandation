# Round08: preserve scope across list shape changes and revalidation
Repository /Users/l/Project/Recommandation. Read AGENTS.md and owning specs. Preserve task changes. No nested agents, deadline, live model calls, commits or unrelated changes. Write partial report early, update at milestones. Round07 completed with869 tests/lint pass, but independent acceptance rejects2confirmed scope escapes. Read round-07/additional-review.md FIRST. This is one core issue: preserve field/member granularity at every path-expansion step. Fix mechanism, do not patch only concrete strings.

Required counterexamples (production _complete_parsed_role):
A. Leaf paths=("rows[0].fix",), invalid rows=[{fix:0,keep:"original"},{fix:2,keep:"protected"}], model corrected rows=[{fix:1,keep:"drift"},{fix:3,keep:"extra"},{fix:2,keep:"protected"}]. Parser otherwise returns object after fix. Currently accepted because changing cardinality cap to len(old)+slots lets a leaf permission rewrite siblings and insert arbitrary records. Leaf correction must not imply whole member replacement/addition. Preserve unrelated fields/members or reject. Also test a sibling drift with removal, not only addition; strict item/leaf scope must hold regardless length.
B. invalid={fix:0,rows:["original","second"]}, corrected={fix:1,rows:["drift"]}. Parser initially errors paths=("fix",); projected fixed object then raises structured research_state_item_over_limit with paths=("rows",), repair_context={minimum_removed_items:1,must_reduce_any_of_paths:["rows"],required_compaction_remove_paths:["rows[1]"]}. Current _structured_revalidation_paths flattens root paths and accepts drift. Extension must use actual compaction scope/removal metadata, preserving rows[0]. Reuse consistent scope interpretation for first error and discovered errors; no broad authority from container error root when narrower repair metadata exists.

Remove unjustified blanket current_beliefs dependencies on visible_answer_need_retained/research_need_transition_invalid. A need correction cannot authorize rewriting ALL unrelated beliefs. Any real dependency must arise from actual linked assertions or actual compaction issues, with precise scope. Add production-role negative coverage showing valid unrelated belief remains unchanged during need correction.

Helpful existing test evidence (not permission to weaken assertions): v79 initialize fixture has25 old beliefs and model replaces all with1 new belief while removing answered need; this is actual compaction, not generic need->allbeliefs permission. Preserve protected original beliefs, with exact runtime-authorized deletions, or apply correct structured compaction correction. v11 basic-claim fixture legitimately ADDS an evidence reference with SAME claim to cover missing quantity; it need not rewrite existing reference. Authorize genuine append from validator explicitly, not every leaf path. Existing full tests and meaningful assertions must remain, but incidental unrelated model edits may be projected away. No open-ended blanket root authorization for tests. Check redundant/unreachable helper branch mentioned in review and remove code made dead by your fix.

Spec first, smallest cohesive fix, tests coveringA/B plus existing scalar/list/compaction/dependency/actual V117/round06 chain; full suite/lint. No weakened PIT, validation, promotion, schemas or public APIs. If genuinely blocked on interface semantics, report concrete issue rather than fabricate a broader permission. Audit/progress/report updated; distinguish local readiness from still-not-run real Fast+Slow.
Report /Users/l/Project/Recommandation/.delegation/fast-slow-20260919/round-08/report.md with round_id,status,changed files,results,commands/codes/logs/outstanding (~1200Chinese chars).

Allowed writes:
src/stock_opportunity_agent/research/evolution_output_validation.py
src/stock_opportunity_agent/research/evolution_research_validation.py
src/stock_opportunity_agent/research/evolution_plan_roles.py
spec/src/stock_opportunity_agent/research/evolution_output_validation.md
spec/src/stock_opportunity_agent/research/evolution_research_validation.md
spec/src/stock_opportunity_agent/research/evolution_plan_roles.md
tests/test_evolution_output_validation.py
tests/test_evolution_execution_roles.py
tests/test_evolution_reflection_roles.py
progress/status.md
progress/changelog.md
.delegation/fast-slow-20260919/round-08/report.md
.delegation/fast-slow-20260919/round-08/focused.log
.delegation/fast-slow-20260919/round-08/full-tests.log
.delegation/fast-slow-20260919/round-08/lint.log
tests/test_evolution_routing_plan_roles.py
tests/test_information_plan_engine.py
reports/fast-slow-joint-correctness-20260919.md
Exact commands:
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v > .delegation/fast-slow-20260919/round-08/focused.log 2>&1
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -v > .delegation/fast-slow-20260919/round-08/full-tests.log 2>&1
sh scripts/lint_repo.sh > .delegation/fast-slow-20260919/round-08/lint.log 2>&1
git status --short
git diff --check
