# Round 06: reject unrepresentable partial residual and verify composed need flow
Repository /Users/l/Project/Recommandation. Read AGENTS.md and owning specs. Preserve existing round03/05 changes. One executor, no nested agents, no time deadline. No live production calls, commits, pushes, credentials reads or unrelated changes. Immediately write partial report and update at implementation/testing milestones.

Round05's 862 tests and lint pass but independent acceptance FAILED. Read round-05/review.md. Narrow fix only: _bounded_residual_need returning None currently degrades partial obligation to remove_or_genuinely_narrow. This allows silent deletion of unresolved demand and finalize, while available_answer_actions still exposes unsafe exact residual. Reject invalid legacy selection before constructing an impossible reflection prompt (preferred fail-closed), or justify a consistent preservation approach without changing research semantics. Do not retain deletion fallback or fabricate cutoff for realized future facts. Preserve valid bounded partial guidance and actual V117 repair.

Concrete production repro uses PartialResidualTemporalScopeTests._v117_reflect_inputs(); dataclasses.replace(selection,residual_need="What were the realized revenue results for Q1 2026?"); output=case._adopting_output("placeholder"); output["next_information_needs"]=[]; output["decision"]="finalize"; ScriptedRoleCaller([output,output]); LLMResearchController.set_evaluation_context(datetime(2025,9,30,tzinfo=timezone.utc)); set_reflection_runtime_context(selections=(selection,),must_finalize=False,termination_trigger=None); reflect(default_information_plan(),previous,batch) currently accepts empty needs in one call. Reject this, preserving evidence and existing failure handling. Also verify continue with unrelated need cannot hide unresolved partial demand.

Success criteria:
1. Spec aligned first, minimal guard/consumer fix; invalid unrepresentable residual cannot silently remove need/finalize or produce contradictory prompt; regression via production role path.
2. Add one composed scripted production-path test: corrected routing selection -> reflection -> subsequent routing. Assert actual transmitted next routing prompt consumes exact accepted narrower bounded need, not only helper equality. Existing routing/reflection tests separately are insufficient.
3. Original unrelated scalar drift repro stays protected; no weakened temporal, scoring, promotion or schema semantics. Full suite and lint pass.
4. Update audit/progress and report with actual changed behavior/test counts/remaining real joint run. No broad reinvestigation of V117. Do not claim runtime success from local tests.

Report: /Users/l/Project/Recommandation/.delegation/fast-slow-20260919/round-06/report.md. Include round_id,status,changed files,commands/exit codes,log paths,outstanding; keep concise.

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
.delegation/fast-slow-20260919/round-06/report.md
.delegation/fast-slow-20260919/round-06/focused.log
.delegation/fast-slow-20260919/round-06/full-tests.log
.delegation/fast-slow-20260919/round-06/lint.log
tests/test_evolution_routing_plan_roles.py
tests/test_information_plan_engine.py
reports/fast-slow-joint-correctness-20260919.md
Exact commands:
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v > .delegation/fast-slow-20260919/round-06/focused.log 2>&1
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -v > .delegation/fast-slow-20260919/round-06/full-tests.log 2>&1
sh scripts/lint_repo.sh > .delegation/fast-slow-20260919/round-06/lint.log 2>&1
git status --short
git diff --check
