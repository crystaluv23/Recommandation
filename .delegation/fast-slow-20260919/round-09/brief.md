# Round09: explicit member-deletion authority, no generic leaf escalation
Repository /Users/l/Project/Recommandation. Read AGENTS.md/owning specs. One executor, no nested agents, no deadline/live calls/commits/unrelated changes. Immediately write brief partial report before investigation. Focus ONLY on the small mechanism below; no full source rereads or V117 reinvestigation. Use targeted reads around named functions/test. Preserve prior task changes.

Read round-08/additional-review.md. Round08 now passes873tests but independent production replay proves unconditionally populated removal_allowances escalates replace-only leaf permission into parent-row deletion. Explicit counterexample is there. Fix: removal authorization must come from specific validator metadata, NOT from existence of an indexed leaf path or whole-object validity. Check allowed_repairs as necessary but do not interpret leaf "remove" as parent removal without an explicit whole-member target. Negative parser should check only invalid fix, not mirror scope preservation; rejected otherwise-valid outputs are the real proof. Add pure removal, replacement+addition, and same-length sibling mutation cases with only leaf replace authorized; explicit whole-member removal positive must pass.

IMPORTANT scope now includes evolution_signal_roles.py + own spec + test_evolution_signal_role_adapters.py. This is deliberate: legitimate H1 history-only unknown-alias row deletion should be explicitly authorized by its owning h1_unknown_need_refs validator around1935. Existing test_h1_aggregates_history_refs_in_ledger_and_terminal_reason around3561 expects exact diagnostic required_change_paths ["need_dispositions[0].need_refs","no_hypothesis"]. Keep those diagnostics while encoding exact parent-row deletion as trusted repair metadata/dependency if appropriate. Authorize removal only of the diagnosed row when its refs are invalid under actual runtime need set, with full output validation; don't globally exempt H1 or all leaf paths. Update H1 spec first. Shared correction machinery consumes explicit instruction generically; no new canonical research schema or cross-module dependency needed.

Also fix _authorized_equivalent's exact-path handling: if path is explicitly allowed, permit that subtree before recursing; currently same-length list-valued leaf edit is rejected during neighboring row removal. Add composed positive case: authorized rows[0].tags replacement (same length), explicit removal rows[1], preserve rows[0].keep. This is a small precise comparator correction, not whole-item scope widening.

Retain round08 successes: A leaf expansion rejected, B compaction extension exact removals only, no blanket current_beliefs permission, bounded append authorized explicitly, routing partial temporal boundary/round06 chain. Keep valid historical tests; no weakening assertions. Run focused/full/lint, independently check negative assertions actually depend on scope guard. Keep fix small; delete generic removal-inference workaround rather than layering more exceptions. Update audit/progress/report.
Final report /Users/l/Project/Recommandation/.delegation/fast-slow-20260919/round-09/report.md with status,changed files,testcodes/logs,outstanding. Real Fast+Slow still not run.

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
.delegation/fast-slow-20260919/round-09/report.md
.delegation/fast-slow-20260919/round-09/focused.log
.delegation/fast-slow-20260919/round-09/full-tests.log
.delegation/fast-slow-20260919/round-09/lint.log
tests/test_evolution_routing_plan_roles.py
tests/test_information_plan_engine.py
reports/fast-slow-joint-correctness-20260919.md
src/stock_opportunity_agent/research/evolution_signal_roles.py
spec/src/stock_opportunity_agent/research/evolution_signal_roles.md
tests/test_evolution_signal_role_adapters.py
Exact commands:
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v > .delegation/fast-slow-20260919/round-09/focused.log 2>&1
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -v > .delegation/fast-slow-20260919/round-09/full-tests.log 2>&1
sh scripts/lint_repo.sh > .delegation/fast-slow-20260919/round-09/lint.log 2>&1
git status --short
git diff --check
