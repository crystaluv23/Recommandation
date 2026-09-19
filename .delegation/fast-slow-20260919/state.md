# Fast/Slow correctness repair — active goal

Repository: /Users/l/Project/Recommandation, branch main. Initial clean HEAD ce518070; preparation checkpoint d71ae85. User-authorized goal remains one logically correct real Fast+Slow joint execution with actual prompt/response/context/causal-flow audit.

## Current state
- Local repair accepted through round09:875fulltests,21focusedtests,lintpass; independent replay in round-09/independent-replay.json and review.md.
- Last external execution: round09, exec61236/PID13929/session sess_d71caf78-9b95-45a8-93d4-a41ba10b0878, normal turn.completed after686.9seconds. No active writer.
- Next: code checkpoint, freeze/execute V118 per live-plan.md and live-freeze-args.json. Success not yet claimed; no successor production calls yet.
- Budget after V117:2738attempts/$19.20981059 remaining from original3000/$20. Track successors cumulatively. Verified dataset/raw-info/history inputs in live-inputs.json. Preserve V117 immutable, round/cycle pointers0/0.

## Confirmed diagnosis and repair
Raw V117 requests12/262 explicitly demanded temporal-invalid exact partial residuals; routing lost parent cutoff, while downstream exact-transition and temporal guards contradicted each other. Evidence: v117-required-residual.json, v117-second-candidate-feedback.json, v117-bounded-replay.json. Producer temporal validation + consistent bounded consumer obligations; reject impossible legacy residual before reflection. Scoped correction preserves valid fields/members, honors exact compaction deletions, and permits member removal only through explicit owning-validator authority. No whole-object bypass or blanket belief rewrite permission.

## Delegation/evidence
Every round brief/report is in round-NN; execution logs and test logs remain local. Rounds03,05,07,08 passed their suites but were independently rejected on concrete counterexamples; reviews retained. Round06 temporal fallback and round09 final scope repairs accepted. Latest joint acceptance requirements: acceptance.md; audit: reports/fast-slow-joint-correctness-20260919.md.

## Skill side task
Installed /Users/l/.codex/skills/plan-and-delegate updated: no default total/idle deadline; verified app-server API intermediate feedback and runtime completion; plans/reports persisted and linked; default user key path remembered without key content.10offline tests and skill-format validation pass; real API Write integration passed. Audit/hashes in skill-update.md. Early round01 did hit old300s cutoff; two early API pilots misclassified completion and were fixed; later rounds complete on actual runtime event. Skill is outside repo git tracking.
