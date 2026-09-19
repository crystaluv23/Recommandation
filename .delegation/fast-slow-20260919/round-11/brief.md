# Round 11: distinguish use of supplied evaluation anchors from retrieval
Repository: /Users/l/Project/Recommandation
Baseline: 63a2efb plus accepted uncommitted round10 projection feedback fix (877 tests). Preserve all existing changes. Read AGENTS.md. Single external writer, no subagents. No hard time limit. Do not run paid production, commit or push.

Goal: resolve semantic false positive in real V118 request74 before successor live acceptance. Read round-10/additional-review.md and v118-rejection-evidence.json. The literal issuer-guidance question uses the supplied baseline; it does not request the runtime baseline. Current proximity regex incorrectly rejects it. Investigate analogous current-price/definition mentions as appropriate to this same guard. Fix generic intent distinction, no company/case/string exception, no blanket bypass for words supplied/using (mixed questions can still request runtime facts). Preserve actual baseline/date/current-price/definition lookup rejection and all PIT future-fact rejection.

Order: inspect owning spec and guard/call sites and existing tests; update spec first; implement minimal semantic repair; paired regressions with actual V118 text, genuine runtime lookup negatives, mixed issuer+runtime lookup, reference-only use, temporal negatives. Review upstream prompts and downstream validator feedback for consistency. Do not change scoring/dataset/promotion/schema/correction budgets. Keep accepted round10 patch. Full suite and lint required.

Allowed implementation files: evolution_research_validation.py and owning spec, relevant existing evolution execution/reflection/routing tests; progress/status.md and changelog.md. Report/replay files under round11. If other files needed explain in report instead of modifying outside scope.

Acceptance: actual V118 question no longer produces runtime-owned lookup error (other actual numeric-evidence errors may remain); genuine runtime lookups still reject, mixed question not bypassed; all tests/lint pass. Inspect raw wire samples, not just simplified invented cases. Replay script can import round10 utilities and read immutable V118, never alter run artifacts. Do not claim live success.

Write short report immediately, update after diagnosis/implementation/testing. Final report /Users/l/Project/Recommandation/.delegation/fast-slow-20260919/round-11/report.md with round_id/status, files, tests commands/exit codes, logs, unresolved issues, concise summary. No secret reads/copies.

## Exact permitted commands (handoff clarification)
The hook accepts these exact strings, not git status without --short, pytest, pwd or echo. These commands were already allowed from process start; no permission expansion is needed.
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -p test_evolution_execution_roles.py -v > .delegation/fast-slow-20260919/round-11/focused.log 2>&1
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 -m unittest discover -s tests -v > .delegation/fast-slow-20260919/round-11/full-tests.log 2>&1
sh scripts/lint_repo.sh > .delegation/fast-slow-20260919/round-11/lint.log 2>&1
git status --short
git diff --check
PYTHONPATH=src /Users/l/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3 .delegation/fast-slow-20260919/round-11/replay.py > .delegation/fast-slow-20260919/round-11/replay.log 2>&1
