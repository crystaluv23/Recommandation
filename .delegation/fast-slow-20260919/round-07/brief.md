# Round07: eliminate list-shaped scope escape
Repository /Users/l/Project/Recommandation. Read AGENTS.md and relevant specs. Preserve prior task changes. No nested agents; no time deadline. No production calls, commits, pushes or unrelated changes. Write report partial first and at test milestones. Narrow implementation task, no broad exploration.

Read round-06/additional-review.md. Confirmed independent production correction counterexample: invalid={"fix":0,"keep":["original"]}; corrected={"fix":1,"keep":["drift","extra"]}. Parser first raises StructuredValidationError with paths=("fix",) when fix==0; then plain ValidationError when keep==["original"]; otherwise returns value. _complete_parsed_role exact_compaction_scope=True/enforce_scoped_correction=True/stable_correction_prefix=True currently returns corrected, because _lenient_list_membership_edits_only permits full-object escape. Existing test_lenient_projection_fails_closed_on_prose_only_revalidation covers scalar but not list. Membership change cannot authorize unrelated deletion/rewrite. Even same-length list change can surface bare root if no allowed path reaches it; helper docstring length claim is unsupported.

Fix owning spec first, remove unsafe full-object fallback. Legitimate list corrections must be authorized by actual structured issue/compaction/dependency paths with protected siblings preserved, not by type/length or merely passing validation. If existing real-case regressions need authorizations, locate validators responsible and encode precise dependencies, don't weaken tests to keep green. Prefer minimal changes. Remove dead projected_failure variable in touched block. Add list regression alongside scalar (length-changing and same-length unauthorized cases); retain all existing legitimate compaction/member removal/dependency tests. Do not weaken PIT, scoring, promotion, correction guards or introduce new schemas/public interfaces.

Success: concrete escape fails closed or projects preserving unrelated list, original scalar counterexample stays protected, valid production repairs retain existing coverage; full tests/lint pass. Update audit/progress and final report with commands/codes/logs and distinguish local from real joint acceptance. Report /Users/l/Project/Recommandation/.delegation/fast-slow-20260919/round-07/report.md.

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
.delegation/fast-slow-20260919/round-07/report.md
.delegation/fast-slow-20260919/round-07/focused.log
.delegation/fast-slow-20260919/round-07/full-tests.log
.delegation/fast-slow-20260919/round-07/lint.log
tests/test_evolution_routing_plan_roles.py
tests/test_information_plan_engine.py
reports/fast-slow-joint-correctness-20260919.md
Exact commands:
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v > .delegation/fast-slow-20260919/round-07/focused.log 2>&1
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -v > .delegation/fast-slow-20260919/round-07/full-tests.log 2>&1
sh scripts/lint_repo.sh > .delegation/fast-slow-20260919/round-07/lint.log 2>&1
git status --short
git diff --check
