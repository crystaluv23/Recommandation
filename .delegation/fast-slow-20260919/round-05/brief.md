# Round 05: real V117 contradictory temporal/residual contract + safe scoped repair
Repository /Users/l/Project/Recommandation. Read AGENTS.md. No internal subagents; no hard time deadline. Baseline ce518070 plus d71ae85 and uncommitted round-03 changes. Round 04 was intentionally interrupted on discovery below, no new source changes. Preserve task changes while correcting them. Write report partial immediately after reading this brief, BEFORE more source investigation; update at implementation/test milestones.

CRITICAL: the user's initial audit/root-cause hypothesis was incomplete. Read .delegation/fast-slow-20260919/v117-required-residual.json and v117-projection-replay.json FIRST. Raw V117 request 12 explicitly names next_information_needs[0] and instructs replace_with_exact_residual with required_need="Cost per ounce guidance for the remainder of 2025 and 2026 is not covered by this card." That exact residual violates temporal boundary. Earlier corrected output 11 says "What cost per ounce guidance had Kinross Gold disclosed by 2025-09-30 for the remainder of 2025?" but gets research_need_transition_invalid for not matching the exact unsafe residual. Thus model is following contradictory instructions. Scoped sibling preservation CANNOT fix it because the reverted field is itself authorized! Need fix upstream residual production/validation and downstream exact-consumer alignment. Do not blindly follow prior audit.

Inspect owning specs first, then routing LLMSignalRetrievalAgent.select partial residual contract (evolution_plan_roles.py around 850-1100), _reflection_need_transition_contract and transition validator (evolution_research_validation.py around 1400 and 2350), _restore_inherited_need_cutoffs around 905, and actual V117 request/output chain under immutable workspace. The raw residual comes from SignalSelectionDecision in routing, NOT necessarily Signal execution. Preserve point-in-time guarantees and genuine need narrowing; do not mask later realized data as available or simply retain an already answered parent need. A narrowed partial need must retain its original temporal scope so its exact required representation is satisfiable by H_reflect. Prefer the smallest generic fix at producer boundary and consistent consumers; avoid new public interfaces if existing context/parent need scope suffices. If an interface contract change is truly needed, report exact necessity before implementing it.

Separately, current round-03 whole-object fallback violates preservation; read round-03/review.md. Do not retain this loophole just because 856 tests pass. Resolve legitimate explicit dependency/shape/list repairs, or remove unsafe experimental behavior while keeping specs honest. Scope inference must come from structured issues, not prose. Full validation alone does not authorize unrelated sibling drift. Do not weaken existing invariant or adjust tests just to force green.

Acceptance: (1) regression mirrors actual contradiction: original bounded future-guidance need -> partial routing residual loses cutoff -> correction/normalization yields a bounded genuinely narrower residual -> H_reflect exact residual accepted by BOTH transition and temporal guards -> same accepted need consumed by subsequent routing. Use production role/validator paths. (2) no contradictory corrective obligations; preserve literal quantities and point-in-time guarantees. (3) keep V117-like correction regression and unrelated drift counterexample; explicit legitimate dependency edits/list removal work. (4) focused/full tests and lint pass. (5) report distinguishes local fix from not-yet-run real Fast+Slow. No production model calls this round.

Spec first/simultaneous, minimal implementation, tests, progress/status + changelog, and new audit reports/fast-slow-joint-correctness-20260919.md correcting initial root-cause account with raw request hashes and evidence. Do not overwrite the old V117 audit or immutable artifacts. No commits/push/reset, memory writes, credentials/private configuration reads, altered budgets/scoring/record schemas.

Final report /Users/l/Project/Recommandation/.delegation/fast-slow-20260919/round-05/report.md (~1200 Chinese chars): round_id, status, changed files, findings, actual test commands/exit codes/log paths, outstanding decisions/live acceptance. Do not bury failure or skip report when blocked. Use Read/Grep/Glob and Write/Edit; exact permitted shell commands below.

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
.delegation/fast-slow-20260919/round-05/report.md
.delegation/fast-slow-20260919/round-05/focused.log
.delegation/fast-slow-20260919/round-05/full-tests.log
.delegation/fast-slow-20260919/round-05/lint.log
tests/test_evolution_routing_plan_roles.py
tests/test_information_plan_engine.py
reports/fast-slow-joint-correctness-20260919.md
Exact commands:
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -p test_evolution_output_validation.py -v > .delegation/fast-slow-20260919/round-05/focused.log 2>&1
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -v > .delegation/fast-slow-20260919/round-05/full-tests.log 2>&1
sh scripts/lint_repo.sh > .delegation/fast-slow-20260919/round-05/lint.log 2>&1
git status --short
git diff --check
