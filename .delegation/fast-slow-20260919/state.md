# Fast/Slow correctness repair — active goal

Repository: /Users/l/Project/Recommandation, branch main. Initial clean HEAD ce518070; preparation checkpoint d71ae85. User-authorized goal remains one logically correct real Fast+Slow joint execution with actual prompt/response/context/causal-flow audit.

## Current state
- Code checkpoint63a2efb contains repairs through round09. V118 real run ended rejected, pointers0/0; no active production executor.
- Round10 reported and locally accepted: safe projected state plus actual revalidation diagnostics retained across correction, 877tests/lintpass. Independent actual-wire replay confirms changed feedback and preserved siblings. Changes await checkpoint with round11.
- Round11 ended actual turn.completed after891seconds; NOT accepted. Guard now fails open on ordinary runtime lookups (independent-review.md), tests not executed due missing exact-command handoff. Launcher now automatically passes permitted commands;10offline tests/skill validator pass.
- Round12 normal completion after809seconds,886tests/lint passed. NOT accepted: bare with misclassified and repeated same-anchor lookup missed; independent-review.md records probes.
- Round13 completed normally538.9seconds; accepted locally with888tests/lint and independent raw-wire/probe verification. No active external writer. Combined round10–13 changes ready for checkpoint then V119 freeze/run; prepared argv/plan under v119. Main goal incomplete.
- Remaining cumulative budget2661attempts/$18.95184855. Verified input pointers in live-inputs.json. Preserve V117/V118 immutable. Next freeze fresh successor only after semantic review, tests and checkpoint.

## Confirmed diagnosis and repair
Raw V117 requests12/262 explicitly demanded temporal-invalid exact partial residuals; routing lost parent cutoff, while downstream exact-transition and temporal guards contradicted each other. Evidence: v117-required-residual.json, v117-second-candidate-feedback.json, v117-bounded-replay.json. Producer temporal validation + consistent bounded consumer obligations; reject impossible legacy residual before reflection. Scoped correction preserves valid fields/members, honors exact compaction deletions, and permits member removal only through explicit owning-validator authority. No whole-object bypass or blanket belief rewrite permission.

## Delegation/evidence
Every round brief/report is in round-NN; execution logs and test logs remain local. Rounds03,05,07,08 passed their suites but were independently rejected on concrete counterexamples; reviews retained. Round06 temporal fallback and round09 final scope repairs accepted. Latest joint acceptance requirements: acceptance.md; audit: reports/fast-slow-joint-correctness-20260919.md.

## Skill side task
Installed /Users/l/.codex/skills/plan-and-delegate updated: no default total/idle deadline; verified app-server API intermediate feedback and runtime completion; plans/reports persisted and linked; default user key path remembered without key content.10offline tests and skill-format validation pass; real API Write integration passed. Audit/hashes in skill-update.md. Early round01 did hit old300s cutoff; two early API pilots misclassified completion and were fixed; later rounds complete on actual runtime event. Skill is outside repo git tracking.

## V118 real acceptance failed
run-cycle exited normally round_rejected/no_fitness_eligible_candidates after77attempts/$0.25796204; round/cycle0/0. c01 failed H_init case5 cik_0001869198:20250331, c02 failed H_init first Kinross case. Raw pairs74/75 and76/77, correction2 reused identical cached request after projection-scope rejection. Evidence v118-rejection-evidence.json; actual flow changes verified in v118-changed-flows.json but no joint completion. Next: round10 diagnose projected revalidation failure and provide safe updated correction feedback; never widen unrelated scope. Remaining cumulative2661attempts/~$18.95184856. No active production process.
