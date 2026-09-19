# Round 04: close whole-object fallback escape without breaking valid dependency repairs
Repository /Users/l/Project/Recommandation. Read AGENTS.md. Baseline ce518070 plus task-only d71ae85 and uncommitted round-03 implementation; preserve existing task changes. No internal subagents. No hard elapsed-time deadline. Advisory 20 turns, split/report if needed. Report partial immediately then update at implementation and test milestones so user can see progress.
Read .delegation/fast-slow-20260919/round-03/review.md FIRST. Previous repair now passes 856 tests + lint but is NOT accepted: when ordinary scoped projection cannot be built or fails validation, code accepts the raw model object after whole validation. This silently permits unrelated valid siblings to drift and violates the existing invariant. Fix must not merely reword spec to bless escape.
Concrete independent counterexample through real _complete_parsed_role: initial {fix:0,hidden:0,keep:"original"}; parser reports structured invalid_value for fix first, then hidden. Correction {fix:1,hidden:1,keep:"unrelated drift"}. Projected output fails hidden validation; raw object passes and changes keep. Need keep="original" or fail closed with specific feedback, not silent drift. Add regression for this and retain V117-like two-successive-correction regression.
Investigate 9 prior full-suite failures from round-03/full-tests.log if history has been overwritten use round-03 report and affected cases test_v107_initialize_stops_deep_checks_on_invalid_evidence_shape, test_v79_initialize_aggregates_visible_answers_before_compaction, test_v11_basic_claim_requires_all_quantities_across_literal_refs, test_v22_reflect_aggregates_quantity_and_stale_resolved_need, test_v23_answer_need_evidence_requires_real_need_progress, test_v70_reflect_changes_targeted_need_not_an_unrelated_need (continue/finalize), test_v73_reflect_receives_result_aware_need_transition_contract, test_v74_reflect_requires_exact_partial_answer_residual. Determine legitimate list deletions and necessary dependencies versus invalid fixture side effects. Prefer precise structured dependency/shape/transition paths and identity-preserving list projection. If newly discovered validator issues justify expanding authorized invalid-field paths, keep this deterministic, bounded and test preservation of unrelated valid siblings. Never infer authority from prose or waive full validation. Actual compaction behavior must remain protected.
Spec first or simultaneous, minimal generic code, tests, progress. Do not change scoring, research semantics, correction budget, temporal guarantees or canonical records; do not encode issuer-specific fixes. Do not modify expected tests merely to get green. No production model calls, no git commit/push/reset, no memory or private credential reads. V117 immutable raw evidence summary .delegation/fast-slow-20260919/v117-evidence.json.
Tests must use production correction entry point and observable outcome. Run focused, full and lint commands, fix in-scope failures. Report exact commands/exit codes and outstanding live acceptance. If proper repair needs scope beyond allowlist, report partial and exact dependency rather than weaken invariant.
Report /Users/l/Project/Recommandation/.delegation/fast-slow-20260919/round-04/report.md: round_id, status completed/partial/blocked, changes, tests/exit codes/log paths, unresolved items. Around 1200 Chinese chars final. Write/update report at milestones, not just at exit.
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
.delegation/fast-slow-20260919/round-04/report.md
.delegation/fast-slow-20260919/round-04/focused.log
.delegation/fast-slow-20260919/round-04/full-tests.log
.delegation/fast-slow-20260919/round-04/lint.log
Exact shell commands:
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v > .delegation/fast-slow-20260919/round-04/focused.log 2>&1
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -v > .delegation/fast-slow-20260919/round-04/full-tests.log 2>&1
sh scripts/lint_repo.sh > .delegation/fast-slow-20260919/round-04/lint.log 2>&1
git status --short
git diff --check
Use Read/Grep/Glob and Write/Edit; no unlisted shell commands.
