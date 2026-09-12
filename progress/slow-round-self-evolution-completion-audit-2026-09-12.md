# Slow Round Self-Evolution Completion Audit

Audit date: 2026-09-12

This audit evaluates the implementation and live evidence against
`slow-round-self-evolution-implementation-plan-2026-09-12.md`. A green local
test suite is supporting evidence only; it does not replace persisted runtime,
semantic, Signal-output, or independent-benefit evidence.

## Authoritative boundary

- Latest executed workspace:
  `runs/cold_start/evolution/information-evolution-slow-self-evolution-20260912-v57`.
- Frozen contract hash:
  `3b7f85ca89fee868f570cc2037a61a13afe012f513228e11ebbc85b2a36587af`.
- Authoritative pointers are Fast round 0 / Slow cycle 2. Both cycles committed;
  no staged file is used as completion evidence.
- The run used 18 successful model attempts with
  `$0.14368368000000004` settled cost, preserved source-read/reflection and role
  request traces, kept Locked Test closed, and left Registry v1 unchanged.
- Each cycle reports zero new candidates, zero validated Signals, zero promoted
  Signals, zero updated Signals, and `signal_goal_status=unmet`.
- Cycle 1 reflection processed 28 units into 28 episodes and four lessons and
  persisted 23 canonicalized nested refs. Cycle 2 received five cycle-1 units
  but processed nine older imported-history units instead, while 101 units
  remained pending. This proves transmission across the cycle boundary but not
  learning consumption.
- Cycle-2 E2 received disjoint runtime labels but its rationale described
  `case-006` as both positive and control. The successor keeps exact label
  membership runtime-owned, forbids free-text case/label reassignment, and
  persists the runtime positive/control ref arrays.
- The successor also reserves immediately prior locally committed complete
  feedback units ahead of old backlog and makes that in-budget recent frontier
  non-evictable by optional model source selection.
- The user explicitly authorized the described DeepSeek transmission, up to 200
  attempts and $5 total cost, and the plan's data external calls.

## Requirement-by-requirement result

| Plan area | Result | Current authoritative evidence | Missing proof or work |
| --- | --- | --- | --- |
| P0 contract and design | Implemented locally | v8 ancestor/module specs define append-only memory, neutral sampling, `slow_only`, output accounting, semantic gates, and bounded history reads | Keep specs synchronized with live findings |
| P1 facts and persistence | Implemented and live verified | V57 has two committed hash-linked input/memory/experiment/validation/result chains and persisted canonicalized nested-ref mappings | Signal Registry did not change because no candidate was produced |
| P2 neutral sampling | Implemented and locally verified | V50 froze one issuer-disjoint 32-dev/8-check manifest with deterministic population/seed/order; scripted restart, issuer separation, strict missing-input and shared-corpus tests pass | Live candidate/check execution has not yet exercised this v8 manifest |
| P3 entry reflection | Implemented and live exercised; cross-cycle scheduling repaired locally | V57 persisted its canonicalization maps and retained all unprocessed refs, but cycle 2 processed old backlog instead of its five cycle-1 units; the recent-frontier regression now proves a model replacement cannot evict prior-cycle units | Requires a fresh live cycle 2 to prove actual prior-cycle consumption |
| P4 search/application closure | Implemented and live exercised; E2 semantics repaired locally | V57 retained H1, two E1 microbatches, E2 and zero-action Update work with ordered request refs; runtime now owns exact E2 group mappings and rejects prose label reassignment | No candidate reached validation or promotion; repaired E2 requires fresh live evidence |
| P5 independent mode and migration | Implemented and live exercised | V57 committed two `slow_only` cycles with Fast fixed at 0 and respected cumulative attempt/cost limits; scripted tests now assert cycle-2 processing, not just input presence | Fresh live proof of actual cycle-1 feedback consumption remains required |
| P6 semantic and independent acceptance | Semantic gates implemented; ablation scaffold only | Candidate semantic consistency, independent support/counter/unavailable fixtures, behavior-duplicate checks, manifest validation, and issuer-level group reservation have deterministic tests | No production path generates the three memory conditions or freezes their generation outcomes; no protocol-confirmed external comparison exists. Therefore method benefit, harm, or generalization cannot be claimed |
| P7 runtime audit | In progress | V57's two cycles, 18 settled attempts, `$0.14368368000000004` cost, exact source cutoffs, role outputs, zero Signal counts, unchanged Registry and sealed Locked Test were inspected | Requires a repaired successor plus Signal transition/use evidence and final independent confirmation |

## Acceptance dimensions

| Dimension | Status | Reason |
| --- | --- | --- |
| Execution completion | Achieved for V57 | Both cycles committed at `last_completed_cycle=2`, with consistent usage, cost and Registry state |
| Content correctness | Not achieved for V57 | Cycle-2 E2 rewrote a runtime label in prose, and reflection did not consume the supplied prior-cycle frontier |
| Signal output | Not achieved | No v8 cycle has committed a new validated and promoted Signal |
| Cross-cycle learning | Input live-proven; consumption not achieved | V57 cycle 2 contains five cycle-1 refs but processed none; repaired deterministic tests require those in-budget units to be consumed |
| Method-learning benefit | Not proven | No independent, equal-budget three-condition confirmation has run |

## Next valid sequence

1. Commit runtime-owned E2 labels and the non-evictable recent reflection
   frontier, then freeze a successor importing V57 history.
2. Re-audit the successor's exact body and execute it under the recorded
   DeepSeek/data authorization while preserving the 200-attempt/$5 ceiling.
3. Execute and semantically inspect two committed `slow_only` cycles, including
   proof that cycle 2 processes cycle-1 feedback. Report new
   candidate, validated, promoted, and updated counts separately for each cycle.
4. Implement and verify a frozen generation path for the equal-budget no-memory /
   episodes-only / episodes-plus-lessons conditions, including candidate,
   validation, promotion, unavailability and cost outcomes. Then freeze and
   approve the explicit confirmation protocol and run the comparison.
   Report insufficient or harmful results honestly and do not reuse revealed
   confirmation cases.

The action plan is therefore still active. Local readiness, permission, actual
transmission, committed cycles, Signal production, and independent method benefit
remain separate states.
