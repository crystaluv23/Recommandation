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

## V119 running
Accepted changes checkpoint c0a5bc2d18899e0bb293dcab460ed7996e7018f1. Contract55def70ce36ed461cd572d56e8a9480d73170eb5ab0ab35107f966df61654b7f. Live exec49461/PID24736, log v119/cycle.log, process v119/process.json. Started2026-09-19T18:28:54UTC; shared data ready then Fast proposal at18:30:39UTC. Same dataset/registry/history/semantics/actual seeds verified, seed manifest change only scan_summary. Remaining run cap2661/$18.95184855. No active ZCode writer. Do not change source or HEAD during frozen live execution.

## V119 rejected; round14 running
V119 ended normally exit0 round_rejected/no_fitness_eligible_candidates:204attempts/$0.6521639600000000568, pointers0/0, no Slow. c01 completed10cases then Newmont case11 correction179 removed unauthorized belief5/reordered siblings; c02 completedKinross then Wynn case2 correction203/204 ignored retained old partial need because prose cites prior index2 while typed path correctly names returned index3. Exact wire snapshots v119/c01-case11-rejection.json and c02-case2-rejection.json. Prior V118 failures passed in V119. Actual LifeTime reflection->new needs->targeted liquidity/OCF signals executed successfully recorded v119/lifetime-causal-flow.json; other failed signals stay unavailable.
Round14 running exec29562/PID25827, brief/report/status under round-14; fix coordinate ambiguity and investigate uniquely safe list reconciliation without permission widening. No active production. Remaining cumulative2457attempts/$18.29968459. Latest accepted source checkpointc0a5bc2.

## Corrected V119 root cause and round15
Round14 interrupted intentionally (launcher SIGINT, exit130 after1013.2s), NOT timeout. New raw-context evidence: Wynn previous needs2/3 identical, only2 targeted; response202 correctly narrowed2 and preserveduntargeted3. Global text membership falsely rejects preserved duplicate, so diagnostic remapping alone insufficient. Round14 partial tests28focusedpass,893full1failure (routing tuple/list); code unaccepted. Independent-review.md also demonstrates no-remove-authority deletion plus ambiguous replacement assignment risk in new reconciler.
Round15 running exec92347/PID27134, brief/report/status under round15. Occurrence-aware need validation/contract/fallback review and safe reconciliation authorization fixes; preserve partialwork. No production active. Latest accepted checkpointc0a5bc2, remaining2457/$18.29968459. V120 prepared but NOT frozen.

## Round15 reported; round16 running
Round15 normal turn.completed after1146.3seconds:32focused/897full tests+lint, occurrence-aware need fix and fallback preserved. NOT fully accepted: pure whole-member replace-only deletion (all siblings preserved) still accepted through RAW drift guard and membership projection shortcut; +covered cardinality also permits implicit splitting. Independent production test saved in round15/independent-review.md. Raw V119 full signal-claim replay incomplete per report (batch reconstruction not attempted), required next.
Round16 running exec96145/PID32028, brief/report/status under round16. Unify explicit per-operation membership permission across raw/projection/extension/reconciliation and fully replay202/203 with Signal batch,177–179 initialize. No production active. Remaining2457/$18.29968459.

## Round16 accepted locally; V120 ready to freeze
Round16 normal API turn.completed1463.9seconds, no timeout.34focused/899full tests+lintPASS. Independent raw request177 replay preserves exactly baselinebeliefs0,1,3,5,6,7 (original request exists; overrides report reconstruction caveat). Production permissions negative/positive probes pass. Wynn202/203 parser replay is model-view-batch reconstruction; live successor required. No active external writer or production process. Commit accepted source then freezeV120 with2457attempts/$18.29968459. Main goal incomplete.
